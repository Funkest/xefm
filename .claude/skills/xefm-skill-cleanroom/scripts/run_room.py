"""Clean-room test the XeFM agent skill against real-world scenarios.

    python .claude/skills/xefm-skill-cleanroom/scripts/run_room.py            # every scenario, in order
    python .claude/skills/xefm-skill-cleanroom/scripts/run_room.py --scenario reload_on_f12
    python .claude/skills/xefm-skill-cleanroom/scripts/run_room.py --list

or `make cleanroom` (`SCENARIO=name` for one).

Each scenario gets a room of its own under `cleanroom/` (gitignored): the
skill exactly as `xefm skill --zip` ships it, RULES.md, TASK.md and an empty
QUESTIONS.md. A non-interactive Claude Code session is started in it with
`--restricted` and told only "Read RULES.md, then do TASK.md." For the
length of that session the user's real `~/.xefm/config.py` is moved aside and
a fixture stands in for it — the template plus the edits a real user makes —
and it is put back afterwards, whatever happens.

The run is then audited (did it reach outside the room?) and checked (did the
edit do what was asked, and leave the user's own lines alone?). The checks
are mechanical; QUESTIONS.md, which the room writes wherever the skill left
it guessing, is the finding a person reads. Modelled on Keyhac's
keyhac-skill-cleanroom, which worked out most of what is load-bearing here.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import friction  # noqa: E402
from outcome import (ROOT, SKILL, Outcome, common_failures,  # noqa: E402
                     fixture_config, load_scenarios)

ROOMS = ROOT / "cleanroom"
XEFM_HOME = pathlib.Path.home() / ".xefm"
CONFIG = XEFM_HOME / "config.py"
#: Where the user's own config waits while a fixture stands in for it. Its
#: existence at start-up means a run died before putting it back.
BACKUP = XEFM_HOME / "config.py.cleanroom-backup"
INSTALLED_SET = XEFM_HOME / "extensions.toml"

#: The whole of what the room is told. Anything said here is something the
#: skill then did not have to carry.
PROMPT = "Read RULES.md, then do TASK.md."

#: Tools the session has. `--restricted` removes Bash unless it is named, and
#: the extension scenario cannot be done without `xefm ext …` — so Bash is
#: named, and narrowed by ALLOW below instead.
TOOLS = "Read,Write,Edit,Glob,Grep,Bash,TodoWrite"

#: What the room may run without asking — and, in a `-p` session under
#: dontAsk, everything else is refused. A shell can reach past the file tools'
#: confinement, so it gets the commands the skill tells an agent to run and no
#: more; a refusal is a finding (the skill named a command the room could not
#: run), and it is reported.
ALLOW = [
    "Read", "Glob", "Grep", "Write", "Edit", "TodoWrite",
    "Bash(xefm ext *)", "Bash(xefm skill *)", "Bash(xefm --version)",
    "Bash(python3 -c \"import ast*)", "Bash(python -c \"import ast*)",
    "Bash(python3 -m pytest*)", "Bash(python -m pytest*)",
    "Bash(cd *)", "Bash(ls *)", "Bash(mkdir *)",
    # The skill says to copy config.py before a larger edit.
    "Bash(cp *)",
]

#: A room's CLAUDE.md, which a correctly started session never sees: under
#: `--restricted` nothing loads it. A session that has it in context was
#: started without the flag, has this repository's CLAUDE.md too, and is told
#: to stop.
CANARY = """\
# If this arrived on its own, stop

**Did you open this file yourself?** Then nothing is wrong — carry on with
TASK.md.

If this text reached you *without* being asked for, the session was started
without `--restricted`, and the CLAUDE.md of the repository above this
directory is in your context too. Do not do the task: say "opened without
--restricted" and stop.
"""

#: Skills of this checkout that a clean room must not be able to see.
CHECKOUT_SKILLS = ("xefm-release", "xefm-skill-cleanroom", "puikit-release")

_SHIM = """\
#!/bin/sh
# The room's `xefm`: the subcommands the skill may run, nothing that opens a
# window. Every call is logged, which is how "never launch XeFM" is checked.
printf '%s\\n' "$*" >> {log}
case "$1" in
  ext|skill|--version|-v)
    PYTHONPATH={root} exec {python} -c 'import sys; sys.argv[0] = "xefm"; from xefm.app import main; main()' "$@" ;;
  *)
    echo "xefm: refused in the clean room - this would open the file manager" >&2
    exit 64 ;;
esac
"""


def find_claude() -> str:
    """The `claude` binary, which is routinely not on PATH (it lives in the
    VS Code extension on this author's machine)."""
    if override := os.environ.get("CLAUDE_BIN"):
        return override
    if found := shutil.which("claude"):
        return found
    binary = "claude.exe" if os.name == "nt" else "claude"
    candidates = list(pathlib.Path.home().glob(
        f".vscode/extensions/anthropic.claude-code-*/resources/native-binary/{binary}"))
    local = pathlib.Path.home() / ".claude" / "local" / binary
    if local.exists():
        candidates.append(local)
    if not candidates:
        raise SystemExit("no `claude` binary - put it on PATH or set CLAUDE_BIN")
    return str(max(candidates, key=lambda p: p.stat().st_mtime))


# --- the room ------------------------------------------------------------------

def build_room(scenario, parent: pathlib.Path) -> pathlib.Path:
    """The skill as shipped, the rules, the task, and nothing else."""
    from xefm import extensions as ext
    room = parent / scenario.NAME
    room.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        bundle = ext.write_skill_zip(pathlib.Path(tmp) / ext.skill_zip_name())
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(room / "skills")
    (room / "CLAUDE.md").write_text(CANARY, encoding="utf-8")
    shutil.copy2(SKILL / "room" / "RULES.md", room / "RULES.md")
    (room / "TASK.md").write_text(f"# The task\n\n{scenario.PROMPT.strip()}\n",
                                  encoding="utf-8")
    (room / "QUESTIONS.md").write_text(
        "# What the skill did not tell me\n\n"
        "One section per thing you had to guess. Empty means the run measured "
        "nothing - see RULES.md.\n", encoding="utf-8")
    return room


def make_shim(log: pathlib.Path) -> pathlib.Path:
    """A bin directory, outside the checkout, holding the room's `xefm`."""
    bin_dir = pathlib.Path(tempfile.mkdtemp(prefix="xefm-cleanroom-bin-"))
    shim = bin_dir / "xefm"
    shim.write_text(_SHIM.format(log=shlex.quote(str(log)), root=shlex.quote(str(ROOT)),
                                 python=shlex.quote(sys.executable)), encoding="utf-8")
    shim.chmod(0o755)
    # The extension scenario runs its package's tests, which need pytest; the
    # system python3 may not have it. This interpreter does, and it cannot
    # import xefm on its own (no PYTHONPATH), so it gives nothing away. A
    # wrapper, not a symlink: a venv is found next to the path a Python was
    # *started* by, so a symlinked venv python elsewhere is the bare base one.
    for name in ("python3", "python"):
        wrapper = bin_dir / name
        wrapper.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n",
                           encoding="utf-8")
        wrapper.chmod(0o755)
    return bin_dir


def session_command(model: str | None = None, max_turns: int = 80,
                    interactive: bool = False) -> list[str]:
    """The flags that make a room inside the checkout a clean room."""
    command = [
        find_claude(),
        "--restricted", "--tools", TOOLS,
        "--add-dir", str(XEFM_HOME),
        "--strict-mcp-config",
        "--settings", json.dumps({"permissions": {"allow": ALLOW}}),
        "--permission-mode", "dontAsk",
    ]
    if interactive:
        return command
    command += ["-p", PROMPT, "--max-turns", str(max_turns),
                "--output-format", "stream-json", "--verbose",
                "--no-session-persistence"]
    if model:
        command += ["--model", model]
    return command


# --- standing in for the user's config ----------------------------------------

class FixtureInPlace:
    """The user's ``~/.xefm/config.py`` moved aside and the fixture in its
    place, for the length of a ``with`` block — and put back on the way out,
    by exception, Ctrl-C or SIGTERM alike. Extensions the room installs are
    copied into the room as evidence and then removed."""

    def __init__(self, room: pathlib.Path, keep_extensions: bool = False,
                 fixture: str = "template"):
        self.room = room
        self.keep = keep_extensions
        self.fixture = fixture_config(fixture)
        self.after: str | None = None
        self.installed: list[pathlib.Path] = []

    def __enter__(self):
        refuse_stale_backup()
        XEFM_HOME.mkdir(exist_ok=True)
        self._had_config = CONFIG.exists()
        if self._had_config:
            os.replace(CONFIG, BACKUP)
        self._set = INSTALLED_SET.read_bytes() if INSTALLED_SET.exists() else None
        self._before = {d: _entries(XEFM_HOME / d) for d in ("extensions", "extension-data")}
        self._top = _entries(XEFM_HOME) | {BACKUP.name, CONFIG.name}
        CONFIG.write_text(self.fixture, encoding="utf-8")
        return self

    def __exit__(self, *exc):
        try:
            self.after = CONFIG.read_text(encoding="utf-8") if CONFIG.exists() else None
            if self.after is not None:
                (self.room / "config.after.py").write_text(self.after, encoding="utf-8")
            (self.room / "config.before.py").write_text(self.fixture, encoding="utf-8")
            self._collect_extensions()
            self._collect_leftovers()
        finally:
            if self._had_config:
                os.replace(BACKUP, CONFIG)
            elif CONFIG.exists():
                CONFIG.unlink()
        return False

    def _collect_extensions(self) -> None:
        for name in ("extensions", "extension-data"):
            for entry in sorted(_entries(XEFM_HOME / name) - self._before[name]):
                source = XEFM_HOME / name / entry
                kept = self.room / "installed" / name / entry
                if source.is_dir():
                    shutil.copytree(source, kept)
                    if name == "extensions":
                        self.installed.append(kept)
                    if not self.keep:
                        shutil.rmtree(source)
        if not self.keep:
            if self._set is None:
                INSTALLED_SET.unlink(missing_ok=True)
            else:
                INSTALLED_SET.write_bytes(self._set)


    def _collect_leftovers(self) -> None:
        """Anything else the room created in ~/.xefm — the config.py.bak the
        skill tells it to make — moves into the room: it is evidence, and it
        must not be left beside the user's real config."""
        for entry in sorted(_entries(XEFM_HOME) - self._top):
            if entry in ("extensions", "extension-data", INSTALLED_SET.name):
                continue
            target = self.room / "xefm-leftovers" / entry
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(XEFM_HOME / entry), target)


def _xefm_running() -> bool:
    try:
        found = subprocess.run(["pgrep", "-f", r"XeFM\.app/|-m xefm( |$)"],
                               capture_output=True, text=True, check=False)
    except OSError:
        return False
    return bool(found.stdout.strip())


def _entries(directory: pathlib.Path) -> set[str]:
    return {p.name for p in directory.iterdir()} if directory.is_dir() else set()


def refuse_stale_backup() -> None:
    if BACKUP.exists():
        raise SystemExit(
            f"{BACKUP} exists: a clean-room run ended without putting your config "
            f"back. Check it is yours, then run this script with --restore.")


def restore() -> int:
    if not BACKUP.exists():
        print("nothing to restore")
        return 0
    if CONFIG.exists():
        aside = CONFIG.with_name("config.py.cleanroom-fixture")
        os.replace(CONFIG, aside)
        print(f"moved the fixture aside to {aside}")
    os.replace(BACKUP, CONFIG)
    print(f"restored {CONFIG}")
    return 0


# --- running and reading a session -------------------------------------------

def run_session(room: pathlib.Path, bin_dir: pathlib.Path, model: str | None,
                max_turns: int) -> pathlib.Path:
    """Drive the room; the transcript is kept outside it while it runs (a room
    that can read its own log can reconstruct what it was not told)."""
    transcript = pathlib.Path(tempfile.gettempdir()) / f"xefm-cleanroom-{room.parent.name}-{room.name}.jsonl"
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    if os.name != "nt":
        # The operator's login shell is nobody's skill: under zsh, `echo =====`
        # fails as an `=cmd` expansion, and a room paid a step for it.
        env["SHELL"] = env["CLAUDE_CODE_SHELL"] = "/bin/bash"
    # The room sits inside the checkout, and `git log` there is read-only, so
    # nothing refuses it - and the history says what every skill change was
    # for. Git stops looking for a repository at the room.
    env["GIT_CEILING_DIRECTORIES"] = str(room.parent)
    started = time.monotonic()
    try:
        # stdin closed: `claude -p` otherwise waits 3s for piped input, and
        # says so into the transcript.
        with subprocess.Popen(session_command(model, max_turns), cwd=room, env=env,
                              stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", bufsize=1) as session, \
                transcript.open("w", encoding="utf-8") as log:
            try:
                for line in session.stdout:
                    log.write(line)
                    _report(line, room, started)
            except BaseException:
                # Ctrl-C or SIGTERM: the session goes with the run, so nothing
                # is still writing into ~/.xefm while it is being put back.
                session.terminate()
                raise
            session.wait()
    finally:
        # Moved in on the way out whatever ended the run: an interrupted
        # run's transcript is the record of what it got as far as.
        if transcript.exists():
            shutil.move(transcript, room / "transcript.jsonl")
    return room / "transcript.jsonl"


def _report(line: str, room: pathlib.Path, started: float) -> None:
    """One line per thing the room did, so a long run is watchable."""
    try:
        event = json.loads(line)
    except ValueError:
        return
    clock = int(time.monotonic() - started)
    stamp = f"  [{clock // 60:>2}:{clock % 60:02d}]"
    if event.get("type") == "assistant":
        for part in event.get("message", {}).get("content", []):
            if part.get("type") == "tool_use":
                given = part.get("input", {})
                hint = next((str(given[k]) for k in ("file_path", "path", "command", "pattern")
                             if k in given), "")
                print(f"{stamp} · {part['name']} {hint.replace(str(room) + '/', '')[:90]}")
    elif event.get("type") == "user":
        for part in event.get("message", {}).get("content", []):
            if part.get("type") == "tool_result" and part.get("is_error"):
                said = str(part.get("content", "")).replace("\n", " ")
                print(f"{stamp} ! refused - {said[:110]}")
    elif event.get("type") == "result":
        print(f"  turns: {event.get('num_turns', '?')}, "
              f"{event.get('duration_ms', 0) / 1000:.0f}s, "
              f"${event.get('total_cost_usd', 0):.2f}")


def _events(transcript: pathlib.Path):
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            yield json.loads(line)
        except ValueError:
            continue


def final_reply(transcript: pathlib.Path) -> str:
    replies = [e.get("result", "") for e in _events(transcript) if e.get("type") == "result"]
    return replies[-1] if replies else ""


def audit(room: pathlib.Path, transcript: pathlib.Path,
          foreign: set[str]) -> tuple[list[str], list[str]]:
    """``(breaches, refused)``: what disqualifies the run, and what it reached
    for and was turned down (the confinement working, reported not punished)."""
    room = room.resolve()
    breaches, refused = [], []
    events = list(_events(transcript))
    init = next((e for e in events if e.get("type") == "system"
                 and e.get("subtype") == "init"), None)
    if init is None:
        breaches.append("the session produced no init event")
    else:
        leaked = [c for c in init.get("slash_commands", [])
                  if any(s in str(c) for s in CHECKOUT_SKILLS)]
        if leaked:
            breaches.append(f"the checkout's own skills were visible: {leaked}")
    if "without --restricted" in final_reply(transcript):
        breaches.append("the room read its canary: started without --restricted")
    results = {part.get("tool_use_id"): part for e in events if e.get("type") == "user"
               and isinstance(e.get("message"), dict)
               for part in e["message"].get("content") or []
               if isinstance(part, dict) and part.get("type") == "tool_result"}
    refused_ids = {i for i, part in results.items() if part.get("is_error")}
    # Compared in one spelling (see _norm): on Windows the room's tools are
    # pointed at C:\Users\..., and a check written for /Users/... found none
    # of it - a read of the checkout went unflagged.
    forbidden = {_norm(path): what for path, what in (
        ("site-packages/xefm", "the installed xefm package"),
        ("/Applications/XeFM.app", "the installed app"),
        (str(BACKUP), "the user's real config"),
        (str(ROOT.parent / "puikit"), "the PuiKit checkout"))}
    checkout, inside = _norm(str(ROOT)), _norm(str(room))
    for e in events:
        if e.get("type") != "assistant":
            continue
        for part in e.get("message", {}).get("content", []):
            if part.get("type") != "tool_use":
                continue
            landed = refused if part.get("id") in refused_ids else breaches
            given = part.get("input", {})
            if part.get("name") == "Bash" and _GIT.search(str(given.get("command", ""))):
                answer = str(results.get(part.get("id"), {}).get("content", ""))
                (refused if "not a git repository" in answer else landed).append(
                    f"Bash ran git, whose history is the checkout's: {given['command'][:80]}")
            for key in ("file_path", "path", "pattern", "command", "glob"):
                value = given.get(key)
                if not isinstance(value, str):
                    continue
                for aimed in _absolute_paths(value):
                    spelled = _norm(aimed)
                    for path, what in forbidden.items():
                        if path in spelled:
                            landed.append(f"{part['name']} reached into {what}: {aimed}")
                    if spelled.startswith(checkout) and not spelled.startswith(inside):
                        landed.append(f"{part['name']} reached into the checkout: {aimed}")
                    if any(_norm(f"/.xefm/extensions/{name}") in spelled for name in foreign):
                        landed.append(f"{part['name']} read another extension: {aimed}")
    return sorted(set(breaches)), sorted(set(refused))


#: A git command anywhere in a shell line.
_GIT = re.compile(r"(?:^|[;&|(`]|\$\()\s*git\s")


#: An absolute path in either spelling: /Users/..., C:\Users\... or C:/Users/...
_ABSOLUTE = re.compile(r"(?:[A-Za-z]:[\\/]|/)[^\s\"'`;|&)]+")


def _absolute_paths(text: str) -> list[str]:
    home = str(pathlib.Path.home())
    text = text.replace("~/", home + "/")
    return _ABSOLUTE.findall(text)


def _norm(path: str) -> str:
    """A path in one spelling for comparison: forward slashes, and lowercase
    on Windows, where C:\\Users and c:/users are the same place."""
    path = path.replace("\\", "/")
    return path.lower() if os.name == "nt" else path


# --- one scenario, and all of them --------------------------------------------

def run_scenario(scenario, parent: pathlib.Path, args) -> dict:
    print(f"== {scenario.NAME}: {scenario.TITLE}")
    room = build_room(scenario, parent)
    calls_log = pathlib.Path(tempfile.mkdtemp(prefix="xefm-cleanroom-calls-")) / "xefm-calls.log"
    bin_dir = make_shim(calls_log)
    foreign = _entries(XEFM_HOME / "extensions")
    try:
        with FixtureInPlace(room, args.keep_extensions,
                            getattr(scenario, "FIXTURE", "template")) as stand_in:
            transcript = run_session(room, bin_dir, args.model, args.max_turns)
    finally:
        shutil.rmtree(bin_dir, ignore_errors=True)
    calls = calls_log.read_text(encoding="utf-8").splitlines() if calls_log.exists() else []
    if calls_log.exists():
        shutil.move(calls_log, room / "xefm-calls.log")

    outcome = Outcome(before=stand_in.fixture, after=stand_in.after,
                      reply=final_reply(transcript), xefm_calls=calls, room=room,
                      installed=stand_in.installed)
    breaches, refused = audit(room, transcript, foreign)
    failures = common_failures(outcome, scenario.KIND) + scenario.check(outcome)
    questions = (room / "QUESTIONS.md").read_text(encoding="utf-8")
    stumbles = friction.incidents(transcript)
    (room / "FRICTION.md").write_text(friction.report(room, failures), encoding="utf-8")
    result = {"name": scenario.NAME, "title": scenario.TITLE, "room": room,
              "breaches": breaches, "refused": refused, "failures": failures,
              "friction": stumbles, "questions": questions.count("\n## ")}

    for line in refused:
        print(f"  refused (the confinement held): {line}")
    for line in breaches:
        print(f"  DISQUALIFIED: {line}")
    for line in failures:
        print(f"  FAIL: {line}")
    if not breaches and not failures:
        print("  checks: pass")
    print(f"  friction:  {len(stumbles)} (in {room / 'FRICTION.md'})")
    for incident in stumbles:
        print(f"    {incident.kind}: {incident.detail}"
              + (f" - {incident.evidence}" if incident.evidence else ""))
    print(f"  questions: {result['questions']} (in {room / 'QUESTIONS.md'})")
    print("  must (read against the transcript and the reply):")
    for line in scenario.MUST.strip().splitlines():
        print(f"    {line}")
    print()
    return result


def _verdict(r: dict) -> str:
    if r["breaches"]:
        return "DISQUALIFIED"
    return "FAIL" if r["failures"] else "pass"


def write_findings(parent: pathlib.Path, results: list[dict]) -> pathlib.Path:
    """FINDINGS.md: every improvement point of the run, one section per
    scenario - the checks' failures, the friction read off the transcript,
    and the questions the room wrote - so they are triaged in one pass rather
    than collected from a terminal log and a QUESTIONS.md per room. `git add
    -f` it when it is worth keeping."""
    lines = [f"# Clean-room findings: {parent.name}", "",
             "Each scenario's check failures, the friction read off its "
             "transcript, and the questions it wrote. Triage every item as a "
             "skill gap, out of scope, or tooling (SKILL.md, Score); only skill "
             "gaps change the skill. Friction no question mentions is the gap "
             "nobody noticed.", ""]
    for r in results:
        room = r["room"]
        lines += [f"## {r['name']} - {_verdict(r)}", "", f"{r['title']}. Room: `{room}`", ""]
        lines += [f"- **disqualified** - {b}" for b in r["breaches"]]
        lines += [f"- **check** - {f}" for f in r["failures"]]
        lines += [incident.line() for incident in r["friction"]]
        questions = room / "QUESTIONS.md"
        asked = [line[3:].strip() for line in
                 (questions.read_text(encoding="utf-8") if questions.exists() else "")
                 .splitlines() if line.startswith("## ")]
        lines += [f"- **question** - {q}" for q in asked]
        if not (r["breaches"] or r["failures"] or r["friction"] or asked):
            lines.append("- nothing recorded - zero is not a pass; read the transcript")
        lines.append("")
    findings = parent / "FINDINGS.md"
    findings.write_text("\n".join(lines), encoding="utf-8")
    return findings


def summary(results: list[dict]) -> int:
    print("== summary")
    worst = 0
    for r in results:
        verdict = _verdict(r)
        if verdict == "DISQUALIFIED":
            worst = 2
        elif verdict == "FAIL":
            worst = max(worst, 1)
        print(f"  {verdict:<12} {r['name']:<30} {len(r['friction']):>2} friction "
              f"{r['questions']:>2} question(s)  {r['room']}")
    print()
    print("  FINDINGS.md beside the rooms gathers every scenario's failures,")
    print("  friction and questions: zero questions is not a pass, and a miss of")
    print("  the 'must' list is a skill defect, not a model one.")
    return worst


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", action="append",
                        help="run only this one (file stem or name; repeatable)")
    parser.add_argument("--list", action="store_true", help="list the scenarios")
    parser.add_argument("--dry-run", action="store_true",
                        help="build the rooms and print the command, run nothing")
    parser.add_argument("--model", help="model for the room sessions")
    parser.add_argument("--max-turns", type=int, default=80)
    parser.add_argument("--keep-extensions", action="store_true",
                        help="leave what a room installs in ~/.xefm/extensions")
    parser.add_argument("--restore", action="store_true",
                        help="put back a config a crashed run left aside")
    args = parser.parse_args(argv)

    if args.restore:
        return restore()
    scenarios = load_scenarios(args.scenario)
    if args.list:
        for s in scenarios:
            print(f"{s.NAME:<30} {s.TITLE}")
        return 0

    import xefm
    parent = ROOMS / f"{xefm.__version__}-{datetime.datetime.now():%Y%m%d-%H%M%S}"
    if args.dry_run:
        for s in scenarios:
            print(f"room: {build_room(s, parent)}")
        print()
        print("Open one, in a session of its own, and say only: " + PROMPT)
        print("    cd <room> && PATH=<a bin dir with the xefm shim>:$PATH \\")
        print("        " + " ".join(shlex.quote(p) for p in session_command(interactive=True)))
        print("Your ~/.xefm/config.py is NOT swapped for the fixture in a dry run.")
        return 0

    refuse_stale_backup()
    find_claude()
    # SIGTERM unwinds like Ctrl-C, so FixtureInPlace puts the config back.
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    print(f"rooms: {parent}")
    print(f"your {CONFIG} is moved to {BACKUP.name} during each run and put back after.")
    if _xefm_running():
        print("XeFM is running: it reads config.py only at start and on Reload "
              "Configuration, so leave both alone until this finishes.")
    print()
    results = []
    try:
        for s in scenarios:
            results.append(run_scenario(s, parent, args))
    except KeyboardInterrupt:
        # FixtureInPlace has already put the config back on the way out.
        print("\n  interrupted - the scenario in progress was collected and your "
              "config.py put back")
    if not results:
        return 130
    print(f"  findings: {write_findings(parent, results)}")
    return summary(results)


if __name__ == "__main__":
    raise SystemExit(main())
