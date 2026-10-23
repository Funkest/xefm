"""Run the demo scenes against vncd.py: ``still`` saves a still after each
scene, ``record`` also records raw.mp4. See README.md.

    $VENV/bin/python tools/gui_demo/drive.py still|record OUT
    SCENES=my_scenes ... drive.py still OUT       # another scene module
"""
import importlib, json, os, socket, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOCKET = "/tmp/xefm-demo-vnc.sock"
SCALE = 2          # framebuffer pixels per point

KEYSYMS = {
    "Enter": 0xff0d, "Esc": 0xff1b, "Tab": 0xff09, "Backspace": 0xff08,
    "Left": 0xff51, "Up": 0xff52, "Right": 0xff53, "Down": 0xff54,
    "PageUp": 0xff55, "PageDown": 0xff56, "Home": 0xff50, "End": 0xff57,
    "F1": 0xffbe, "F10": 0xffc7, "Space": 0x20,
}
#: US-layout shifted symbols: the VNC server turns a keysym into a key code
#: and drops the shift, so "*" would arrive as "8".
SHIFTED = dict(zip('!@#$%^&*()_+{}|:"<>?~', r"""1234567890-=[]\;',./`"""))
MODS = {"Shift": 0xffe1, "Ctrl": 0xffe3, "Alt": 0xffe9, "Cmd": 0xffeb}


class Driver:
    def __init__(self):
        self.s = socket.socket(socket.AF_UNIX)
        self.s.connect(SOCKET)
        self.f = self.s.makefile("rwb")
        self.pointer = (480 * SCALE, 300 * SCALE)
        self.buttons = 0

    def __call__(self, **req):
        self.f.write((json.dumps(req) + "\n").encode())
        self.f.flush()
        reply = json.loads(self.f.readline())
        if not reply.pop("ok"):
            raise RuntimeError(reply["error"])
        return reply

    # --- keys ----------------------------------------------------------------

    def _sym(self, name, down):
        self(op="key", sym=name if isinstance(name, int) else MODS[name], down=down)

    def key(self, name):
        """``Enter``, ``Shift-F``, ``Ctrl-T``, ``v`` / ``V`` (both the v key, as
        the keymap names it), ``*`` (shift added)."""
        parts = name.split("-") if len(name) > 1 and "-" in name.strip("-") else [name]
        mods, base = parts[:-1], parts[-1]
        if base in KEYSYMS:
            sym = KEYSYMS[base]
        elif len(base) == 1:
            if base in SHIFTED:
                mods = mods + ["Shift"]
                base = SHIFTED[base]
            sym = ord(base.lower())
        else:
            raise ValueError(name)
        for m in mods:
            self._sym(m, True)
        self._sym(sym, True)
        time.sleep(0.03)
        self._sym(sym, False)
        for m in reversed(mods):
            self._sym(m, False)

    def type(self, text, delay=0.09):
        for ch in text:
            self.key("Shift-" + ch.lower() if ch.isupper() else ch)
            time.sleep(delay)

    # --- pointer ---------------------------------------------------------------

    def _point(self):
        self(op="pointer", x=self.pointer[0], y=self.pointer[1], buttons=self.buttons)

    def move(self, x, y, duration=0.35):
        x, y = int(x * SCALE), int(y * SCALE)
        x0, y0 = self.pointer
        steps = max(1, int(duration * 60))
        for i in range(1, steps + 1):
            t = i / steps
            t = t * t * (3 - 2 * t)
            self.pointer = (int(x0 + (x - x0) * t), int(y0 + (y - y0) * t))
            self._point()
            time.sleep(duration / steps)

    def click(self, x, y, button=1, count=1):
        self.move(x, y)
        for _ in range(count):
            self.buttons = button
            self._point()
            time.sleep(0.06)
            self.buttons = 0
            self._point()
            time.sleep(0.08)

    def drag(self, x0, y0, x1, y1, mods=()):
        self.move(x0, y0)
        for m in mods:
            self._sym(m, True)
        self.buttons = 1
        self._point()
        time.sleep(0.2)
        self.move(x0 + 8, y0 + 4, 0.15)
        self.move(x1, y1, 0.9)
        time.sleep(0.3)
        self.buttons = 0
        self._point()
        for m in reversed(mods):
            self._sym(m, False)

    def scroll(self, x, y, clicks):
        self.move(x, y)
        button = 16 if clicks > 0 else 8
        for _ in range(abs(clicks)):
            self.buttons = button
            self._point()
            self.buttons = 0
            self._point()
            time.sleep(0.05)

    def run_action(self, a):
        if isinstance(a, str):
            self.key(a)
        elif "pause" in a:
            time.sleep(a["pause"])
        elif "text" in a:
            self.type(a["text"])
        elif "move" in a:
            self.move(*a["move"])
        elif "click" in a:
            self.click(*a["click"])
        elif "dclick" in a:
            self.click(*a["dclick"], count=2)
        elif "rclick" in a:
            self.click(*a["rclick"], button=4)
        elif "drag" in a:
            self.drag(*a["drag"], mods=a.get("mods", ()))
        elif "scroll" in a:
            self.scroll(*a["scroll"])
        elif "ssh" in a:
            subprocess.run([str(HERE / "vm.sh"), a["ssh"]], check=False)
        else:
            raise ValueError(a)
        time.sleep(0.05)


def run(out: Path, video: bool):
    scenes = importlib.import_module(os.environ.get("SCENES", "scenes"))
    out.mkdir(parents=True, exist_ok=True)
    d = Driver()
    if video:
        d(op="record", path=str((out / "raw.mp4").resolve()))
    log, t0 = [], time.monotonic()
    try:
        for n, (intent, actions, hold) in enumerate(scenes.SCENES, 1):
            start = time.monotonic() - t0
            for a in actions:
                d.run_action(a)
            time.sleep(hold)
            d(op="still", path=str((out / f"{n:02d}.png").resolve()))
            log.append({"step": n, "intent": intent, "start": round(start, 2),
                        "end": round(time.monotonic() - t0, 2)})
            print(n, intent, flush=True)
    finally:
        if video:
            d(op="stop")
        (out / "steps.json").write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    run(Path(sys.argv[2]), video=sys.argv[1] == "record")
