"""Build the demo VM's home (projects + ~/.xefm) under OUT: the TUI demo's
sample project, generated night-sky photos, and a ~/.xefm with the keymap
chosen, tips off, Gruvbox Dark and the panes on the two projects.

    PYTHONPATH=. python tools/gui_demo/prep_home.py temp/gui-demo/home
"""
import math, random, shutil, sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import make_demo_gif as tui
from xefm.state_manager import StateManager

out = Path(sys.argv[1]); shutil.rmtree(out, ignore_errors=True)
projects = out / "projects"
tui._project(projects / "aurora")
tui._project(projects / "aurora-backup", backup=True)


def sky(path, seed):
    rnd = random.Random(seed)
    W, H = 1600, 1000
    im = Image.new("RGB", (W, H))
    px = im.load()
    top = (rnd.randint(2, 10), rnd.randint(4, 16), rnd.randint(20, 40))
    bottom = (rnd.randint(10, 30), rnd.randint(30, 60), rnd.randint(50, 80))
    for y in range(H):
        t = y / H
        c = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(W):
            px[x, y] = c
    d = ImageDraw.Draw(im)
    for _ in range(500):
        x, y = rnd.randrange(W), rnd.randrange(int(H * 0.7))
        b = rnd.randint(120, 255)
        d.point((x, y), fill=(b, b, b))
    # aurora curtains
    layer = Image.new("RGB", (W, H))
    ld = ImageDraw.Draw(layer)
    hue = rnd.choice([(60, 255, 140), (80, 220, 255), (190, 90, 255), (120, 255, 90)])
    for band in range(3):
        base = H * (0.25 + 0.12 * band) + rnd.uniform(-40, 40)
        amp, freq, ph = rnd.uniform(40, 120), rnd.uniform(1.5, 3.5), rnd.uniform(0, 6.3)
        for x in range(0, W, 2):
            y = base + amp * math.sin(freq * x / W * 6.28 + ph)
            hgt = rnd.uniform(120, 260)
            f = 0.55 - 0.15 * band
            ld.line((x, y - hgt, x, y), fill=tuple(int(c * f) for c in hue), width=2)
    layer = layer.filter(ImageFilter.GaussianBlur(14))
    im = ImageChops.screen(im, layer)
    # mountains
    d = ImageDraw.Draw(im)
    pts = [(0, H)]
    y = H * rnd.uniform(0.72, 0.8)
    for x in range(0, W + 40, 40):
        y = min(H * 0.92, max(H * 0.62, y + rnd.uniform(-35, 35)))
        pts.append((x, y))
    pts.append((W, H))
    d.polygon(pts, fill=(5, 8, 12))
    im.save(path, quality=88)


photos = projects / "aurora" / "photos"
photos.mkdir(parents=True)
for i in range(8):
    sky(photos / f"night-2026-10-{i * 3 + 2:02d}.jpg", i)

xefm = out / ".xefm"; xefm.mkdir()
config = (Path("xefm") / "_config.py").read_text(encoding="utf-8")
(xefm / "config.py").write_text(config.replace("    CONFIRM_COPY = True", "    CONFIRM_COPY = False"), encoding="utf-8")
(xefm / "tools").mkdir()
st = StateManager(xefm / "state.db")
st.set_state("tips.enabled", False)
st.set_state("keymap.preset", "afx")
st.set_state("theme", "Gruvbox Dark")
st.set_state("pane.left", {"path": "/Users/admin/projects/aurora", "sort_mode": "name"})
st.set_state("pane.right", {"path": "/Users/admin/projects/aurora-backup", "sort_mode": "name"})
st.close() if hasattr(st, "close") else None
print("ok", out)
