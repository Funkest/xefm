"""``xefm try`` — XeFM in a throwaway home, by hand or from a script (#682).

Two jobs need XeFM running where nothing of the user's is: an automated test
that drives the real app and reads what it shows, and a demo recorded for a
README or a release note. An extension's author needs it too: ``xefm ext
check`` is static and the unit tests run against a fake ``ctx``, so menus,
dialogs, task progress and cancel go untested until a person tries them
(running the TUI like this caught #679, which both had missed). One command
serves all three:

- **A throwaway home.** ``HOME`` (and ``USERPROFILE``) point at a temporary
  directory, so the user's ``~/.xefm`` is never read or written. It holds
  XeFM's template config (or the one given), the packages given with
  ``--ext`` installed the way ``xefm ext install`` installs them, and nothing
  else. The keymap preset is chosen and the Tip of the Day is off, so no
  first-run dialog takes the first keys; the home is removed at exit.
- **Interactive** (no ``--keys``): the TUI in this terminal, for a person.
- **Scripted** (``--keys steps.json``): the TUI in a pseudo-terminal of a fixed
  size, read as text through a terminal emulator. Each step's keys go in, the
  screen settles, and its text is saved; the whole session can be recorded as
  an asciicast v2 file a player can replay. It exits when the script ends, so
  it can never block the shell that ran it — the one way an agent may launch
  XeFM.

Scripted mode needs ``pyte`` (the emulator) and quality-loop's key notation:
``pip install 'quality-loop[tui]'`` brings both. POSIX only for now: Windows
has ConPTY, which this does not drive yet.
"""

from __future__ import annotations

import codecs
import json
import os
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from xefm import event_log
from xefm import extensions as ext
from xefm.external_programs import xefm_python


#: The fixture the left pane opens on when no ``--left`` is given: a few
#: files and a folder, enough for selection and navigation.
_FIXTURE = {"a.txt": "alpha\n", "b.txt": "bravo\n", "c.md": "# charlie\n",
            "folder/d.txt": "delta\n"}

#: Seconds after a lone Esc before the next key. A terminal app cannot tell
#: Esc followed quickly by a key from Alt+that key, so it waits a moment
#: (PuiKit 0.1s) for the rest of a sequence.
ESC_SETTLE = 0.3


class TryError(Exception):
    """A try that could not start, and why."""


# --- the home -----------------------------------------------------------------

class TryHome:
    """A temporary ``~`` holding the given packages and nothing of the
    user's."""

    def __init__(self, packages: list[str] = (), *, keymap: str = "afx",
                 config: Path | None = None):
        from xefm import keymap_presets
        from xefm.state_manager import StateManager
        if keymap_presets.canonical(keymap) not in keymap_presets.PRESETS:
            raise TryError(f"no keymap preset {keymap!r} "
                           f"({', '.join(sorted(keymap_presets.PRESETS))})")
        self.root = Path(tempfile.mkdtemp(prefix="xefm-try-")).resolve()
        try:
            self.xefm = self.root / ".xefm"
            self.xefm.mkdir()
            self.work = self.root / "work"
            for name, text in _FIXTURE.items():
                (self.work / name).parent.mkdir(parents=True, exist_ok=True)
                (self.work / name).write_text(text, encoding="utf-8")
            if config is not None:
                shutil.copyfile(config, self.xefm / "config.py")
            # The two dialogs a fresh home opens: each would take the first
            # keys a script sends (an Esc meant for something else picked a
            # keymap preset, and the rest of the script ran against it).
            state = StateManager(self.xefm / "state.db")
            state.set_state("tips.enabled", False)
            state.set_state("keymap.preset", keymap_presets.canonical(keymap))
            layout = ext.Layout(self.xefm)
            #: The installed packages' manifests, in the order given.
            self.manifests = [ext.install(str(source), layout) for source in packages]
            if any(m.requires.get("python_packages") for m in self.manifests):
                from xefm import python_packages as pp
                pp.sync(pp.Layout(layout.home), log=print)
        except BaseException:
            self.remove()
            raise

    def environment(self) -> dict:
        """For the XeFM that runs here: this home as ``~``, and this XeFM's
        own package first on the path, so the copy that runs is this one (the
        one that installed the packages)."""
        package_parent = str(Path(ext.__file__).resolve().parent.parent)
        path = os.pathsep.join(p for p in (package_parent, os.environ.get("PYTHONPATH"))
                               if p)
        return {"HOME": str(self.root), "USERPROFILE": str(self.root),
                "PYTHONPATH": path}

    def remove(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def xefm_argv(left: Path, right: Path) -> list[str]:
    """The terminal XeFM, started by the interpreter that runs this one (not a
    bundle's launcher, which would open the desktop app)."""
    return [xefm_python, "-c",
            "import sys; sys.argv[0] = 'xefm'; from xefm.app import main; main()",
            "--backend", "tui", "--left", str(left), "--right", str(right)]


def run_interactive(home: TryHome, argv: list[str]) -> int:
    """The TUI in this terminal, until the person quits it."""
    return subprocess.call(argv, cwd=str(home.root),
                           env={**os.environ, **home.environment()})


# --- the script ---------------------------------------------------------------

@dataclass
class Step:
    """One step of a script: keys sent, then a wait for the screen to settle.

    ``keys`` is in quality-loop's notation: ``"Ctrl-Shift-P"``, ``"Enter"``,
    ``"a"``, ``{"text": "..."}``, ``{"pause": 0.5}``. A timed sequence (keys
    while a task runs) goes in one step with pauses inside it: between steps
    the runner waits for quiet, which a progress dialog that keeps repainting
    never gives."""
    keys: list
    intent: str = ""
    quiet: float = 0.4
    patience: float = 10.0


def read_script(path: Path) -> list[Step]:
    """A JSON list of steps; each an object with ``keys`` and optionally
    ``intent``, ``quiet`` and ``patience`` (seconds)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise TryError(f"cannot read the script {path}: {e}") from None
    if not isinstance(data, list):
        raise TryError(f"{path}: a script is a JSON list of steps")
    keys = _keys_module()
    steps = []
    for n, item in enumerate(data, 1):
        if not isinstance(item, dict) or "keys" not in item:
            raise TryError(f"{path}: step {n} is not an object with \"keys\"")
        unknown = set(item) - {"keys", "intent", "quiet", "patience"}
        if unknown:
            raise TryError(f"{path}: step {n} has unknown fields: {', '.join(sorted(unknown))}")
        try:
            sequence = keys.sequence(item["keys"])
            for key in sequence:
                if isinstance(key, keys.Key):
                    keys.terminal_bytes(key)   # refuse what a terminal cannot send
        except keys.KeysError as e:
            raise TryError(f"{path}: step {n}: {e}") from None
        steps.append(Step(keys=sequence, intent=str(item.get("intent", "")),
                          quiet=float(item.get("quiet", 0.4)),
                          patience=float(item.get("patience", 10.0))))
    return steps


def _keys_module():
    try:
        from quality_loop.drive import keys
    except ImportError:
        raise TryError("--keys needs quality-loop's key notation and pyte: "
                       "pip install 'quality-loop[tui]'") from None
    return keys


def _pyte():
    try:
        import pyte
    except ImportError:
        raise TryError("--keys needs the pyte terminal emulator: "
                       "pip install 'quality-loop[tui]'") from None
    return pyte


# --- the recording ------------------------------------------------------------

class Recording:
    """An asciicast v2 file: a header, then ``[t, "o", text]`` for everything
    the app wrote and ``[t, "m", label]`` for each step, so a player shows the
    steps as chapters. The header carries the size the app draws at for the
    whole session (it is never resized), so a player lays every row where the
    app did."""

    def __init__(self, path: Path, rows: int, cols: int):
        self._file = open(path, "w", encoding="utf-8")
        self._start = time.monotonic()
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._lock = threading.Lock()
        self._line({"version": 2, "width": cols, "height": rows,
                    "timestamp": int(time.time()),
                    "env": {"TERM": "xterm-256color"}})

    def _line(self, value) -> None:
        with self._lock:
            self._file.write(json.dumps(value, ensure_ascii=False) + "\n")

    def _now(self) -> float:
        return round(time.monotonic() - self._start, 6)

    def output(self, data: bytes) -> None:
        # Incremental: a read can end inside a multi-byte character.
        text = self._decoder.decode(data)
        if text:
            self._line([self._now(), "o", text])

    def marker(self, label: str) -> None:
        self._line([self._now(), "m", label])

    def close(self) -> None:
        self._file.close()


# --- the terminal -------------------------------------------------------------

class PtyApp:
    """One terminal app under a pseudo-terminal of a fixed size, its screen
    kept as text by a terminal emulator kept in step with everything it
    writes."""

    def __init__(self, argv: list[str], *, rows: int, cols: int, env: dict,
                 cwd: str, recording: Recording | None = None):
        if os.name == "nt":
            raise TryError("--keys drives XeFM in a pseudo-terminal, which this "
                           "does not do on Windows yet; run `xefm try` without "
                           "--keys to try it by hand")
        import fcntl
        import struct
        import termios
        pyte = _pyte()
        self.rows, self.cols = rows, cols
        self.screen = pyte.Screen(cols, rows)
        self._stream = pyte.ByteStream(self.screen)
        self._recording = recording
        master, slave = os.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self._master = master
        # The app's answers to queries (cursor position, device attributes)
        # go back down the pty, or an app that asks waits forever.
        self.screen.write_process_input = lambda data: self._write(data.encode("utf-8"))
        self.process = subprocess.Popen(
            argv, stdin=slave, stdout=slave, stderr=slave, cwd=cwd,
            env={**os.environ, **env, "TERM": "xterm-256color",
                 "LINES": str(rows), "COLUMNS": str(cols)},
            start_new_session=True, close_fds=True)
        os.close(slave)
        self._lock = threading.Lock()
        self._changed = self._sent = time.monotonic()
        self._closed = False
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        while not self._closed:
            try:
                ready, _w, _x = select.select([self._master], [], [], 0.1)
                if not ready:
                    continue
                data = os.read(self._master, 65536)
            except OSError:
                break
            if not data:
                break
            with self._lock:
                if self._recording is not None:
                    self._recording.output(data)
                self._stream.feed(data)
                self._changed = time.monotonic()

    def _write(self, data: bytes) -> None:
        if not self._closed:
            os.write(self._master, data)

    def send(self, items: list) -> None:
        keys = _keys_module()
        for item in items:
            if isinstance(item, keys.Pause):
                time.sleep(item.seconds)
            elif isinstance(item, keys.Text):
                self._write(item.text.encode("utf-8"))
            else:
                self._write(keys.terminal_bytes(item))
                if item.name == "Esc" and not item.mods:
                    time.sleep(ESC_SETTLE)
            time.sleep(0.02)
        self._sent = time.monotonic()

    def text(self) -> str:
        """The screen, one line per row, trailing blanks trimmed."""
        with self._lock:
            lines = [line.rstrip() for line in self.screen.display]
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)

    def wait_quiet(self, quiet: float, patience: float) -> bool:
        """Wait until the app has written nothing for ``quiet`` seconds, counted
        from the last key as well as the last output (a key answered with
        nothing would otherwise be "settled" on the silence before it). False
        if it was still writing when ``patience`` ran out."""
        deadline = time.monotonic() + patience
        while time.monotonic() < deadline:
            with self._lock:
                since = time.monotonic() - max(self._changed, self._sent)
            if since >= quiet or self.process.poll() is not None:
                return True
            time.sleep(min(quiet / 4, 0.1))
        return False

    def stop(self, grace: float = 3.0) -> int | None:
        """End the app: its process group, politely and then not."""
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                self.process.wait(grace)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except OSError:
                    pass
                self.process.wait()
        self._closed = True
        self._reader.join(1.0)
        try:
            os.close(self._master)
        except OSError:
            pass
        return self.process.returncode


@dataclass
class ScriptResult:
    steps: int = 0
    unsettled: list = field(default_factory=list)
    exited: int | None = None


def run_script(home: TryHome, argv: list[str], steps: list[Step], *, screens: Path,
               record: Path | None = None, rows: int = 40, cols: int = 120,
               startup: float = 20.0) -> ScriptResult:
    """Drive the TUI through ``steps``. ``screens`` gets ``00.txt`` (the screen
    once XeFM has started), ``NN.txt`` after each step, and ``steps.jsonl``:
    per step its intent, the keys as sent, whether the screen settled, and the
    event-log lines (messages, exceptions) XeFM wrote during it."""
    keys = _keys_module()
    screens.mkdir(parents=True, exist_ok=True)
    events_path = home.root / "events.jsonl"
    events_path.touch()
    recording = Recording(record, rows, cols) if record else None
    result = ScriptResult()
    app = PtyApp(argv, rows=rows, cols=cols, cwd=str(home.root), recording=recording,
                 env={**home.environment(), event_log.EVENTS_ENV: str(events_path)})
    seen = 0

    def new_events() -> list:
        nonlocal seen
        try:
            with open(events_path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return []
        fresh, seen = lines[seen:], len(lines)
        out = []
        for line in fresh:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out

    try:
        with open(screens / "steps.jsonl", "w", encoding="utf-8") as log:
            settled = app.wait_quiet(quiet=1.0, patience=startup)
            (screens / "00.txt").write_text(app.text() + "\n", encoding="utf-8")
            log.write(json.dumps({"step": 0, "intent": "start", "settled": settled,
                                  "screen": "00.txt", "events": new_events()},
                                 ensure_ascii=False) + "\n")
            for n, step in enumerate(steps, 1):
                if app.process.poll() is not None:
                    break
                label = step.intent or " ".join(map(str, keys.describe(step.keys)))
                if recording:
                    recording.marker(f"{n}: {label}")
                started = time.monotonic()
                app.send(step.keys)
                settled = app.wait_quiet(quiet=step.quiet, patience=step.patience)
                name = f"{n:02d}.txt"
                (screens / name).write_text(app.text() + "\n", encoding="utf-8")
                log.write(json.dumps({
                    "step": n, "intent": step.intent, "keys": keys.describe(step.keys),
                    "settled": settled, "waited": round(time.monotonic() - started, 2),
                    "screen": name, "events": new_events()}, ensure_ascii=False) + "\n")
                log.flush()
                result.steps = n
                if not settled:
                    result.unsettled.append(n)
            result.exited = app.process.poll()
    finally:
        app.stop()
        if recording:
            recording.close()
    return result
