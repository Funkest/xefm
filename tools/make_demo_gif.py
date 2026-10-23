"""Record the README's TUI demo GIF.

Drives the terminal XeFM through a fixed script with ``xefm try``'s machinery
(:mod:`xefm.trial`), in a throwaway home holding a small sample project, then
turns the asciicast into a GIF with agg.

A raw recording is mostly waiting: after every step the runner waits for the
screen to settle, and that silence lands in the cast. agg's
``--idle-time-limit`` caps every gap alike, which also cuts the pauses meant
for reading. So the cast is retimed here instead: every gap is squeezed to at
most ``MAX_GAP``, then each step gets its own ``hold`` — how long its result
stays on screen — just before the next step starts.

    PYTHONPATH=. python tools/make_demo_gif.py temp/demo     # demo.cast, demo.gif

Needs ``pip install 'quality-loop[tui]'`` and agg on PATH. POSIX only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from xefm import trial

COLS, ROWS = 120, 40

#: The longest silence kept from the raw recording, in seconds. Typing pauses
#: and animation frames are shorter, so they survive; waiting for the screen to
#: settle is longer, so it goes.
MAX_GAP = 0.15

#: Seconds between typed characters.
TYPE_DELAY = 0.1


# --- the sample project ------------------------------------------------------

_MAIN_PY = '''\
"""Aurora — collect sky-camera frames and forecast the next clear night."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from aurora.forecast import Forecaster
from aurora.storage import FrameStore


@dataclass
class Settings:
    station: str
    latitude: float
    longitude: float
    interval: int = 60

    @classmethod
    def load(cls, path: Path) -> "Settings":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data["station"])


def report(nights, scores, *, width: int = 40) -> str:
    """A small bar chart, one row per night."""
    rows = []
    for night, score in zip(nights, scores):
        bar = "#" * round(score * width)
        rows.append(f"{night:%a %d}  {bar:<{width}}  {score:5.1%}")
    best = max(zip(scores, nights))[1] if scores else None
    if best is not None:
        rows.append(f"best night: {best:%A %d %B}")
    return "\\n".join(rows)


def notify(settings: Settings, text: str) -> None:
    """Send the report to whoever watches this station."""
    if not text:
        return
    subject = f"[aurora] {settings.station}: forecast"
    print(subject)
    print(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aurora")
    parser.add_argument("--config", type=Path, default=Path("data/config.json"))
    parser.add_argument("--nights", type=int, default=3)
    args = parser.parse_args(argv)

    settings = Settings.load(args.config)
    store = FrameStore(Path("frames"))
    forecaster = Forecaster(settings.latitude, settings.longitude)

    for night in forecaster.next_nights(args.nights):
        score = forecaster.clear_sky_score(night, store.recent(hours=6))
        print(f"{night:%Y-%m-%d}  clear sky {score:5.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

_FORECAST_PY = '''\
"""Clear-sky scoring from recent frames."""

import math
from datetime import date, timedelta


class Forecaster:
    def __init__(self, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude

    def next_nights(self, count: int):
        today = date.today()
        return [today + timedelta(days=n) for n in range(count)]

    def clear_sky_score(self, night, frames) -> float:
        if not frames:
            return 0.0
        cloud = sum(f.cloud_cover for f in frames) / len(frames)
        moon = abs(math.cos(night.toordinal() / 29.53 * math.pi))
        return max(0.0, 1.0 - cloud) * (1.0 - 0.3 * moon)
'''

_STORAGE_PY = '''\
"""Frames on disk, newest first."""

from pathlib import Path


class FrameStore:
    def __init__(self, root: Path):
        self.root = root

    def recent(self, hours: int):
        frames = sorted(self.root.glob("*.json"), reverse=True)
        return frames[: hours * 60]
'''

_README = '''\
# Aurora

Collect sky-camera frames and **forecast the next clear night** for
astrophotography.

## Features

- Reads frames from any camera that writes JSON metadata
- Scores each night by cloud cover and moon phase
- Runs unattended on a Raspberry Pi

## Quick start

```bash
pip install -e .
aurora --config data/config.json --nights 3
```

## Configuration

| Key | Meaning | Default |
|-----|---------|---------|
| `station` | Name shown in reports | — |
| `latitude` | Degrees north | — |
| `interval` | Seconds between frames | 60 |

> Tip: keep the camera dome clean — dew reads as cloud.
'''

_CONFIG = {
    "station": {"station": "Mauna Kea", "latitude": 19.82,
                "longitude": -155.47, "interval": 60},
    "camera": {"model": "AllSky-340", "exposure_ms": 15000, "gain": 12},
    "alerts": {"email": "night-desk@example.org", "threshold": 0.8},
}

_METRICS = """date,cloud_cover,moon,score
2026-10-01,0.12,0.84,0.66
2026-10-02,0.40,0.91,0.44
2026-10-03,0.05,0.97,0.67
2026-10-04,0.71,0.99,0.20
2026-10-05,0.22,0.95,0.56
2026-10-06,0.09,0.87,0.70
"""


def _project(root: Path, *, backup: bool = False) -> None:
    """The sample project; ``backup`` is an older copy of it, a little behind,
    so comparing the two finds something."""
    files = {
        "README.md": _README,
        "pyproject.toml": '[project]\nname = "aurora"\nversion = "0.4.0"\n'
                          'requires-python = ">=3.10"\n',
        "LICENSE": "MIT License\n\nCopyright (c) 2026 Aurora contributors\n",
        "src/aurora/__init__.py": '__version__ = "0.4.0"\n',
        "src/aurora/__main__.py": _MAIN_PY,
        "src/aurora/forecast.py": _FORECAST_PY,
        "src/aurora/storage.py": _STORAGE_PY,
        "data/config.json": json.dumps(_CONFIG, indent=2) + "\n",
        "data/metrics.csv": _METRICS,
        "docs/観測メモ.md": "# 観測メモ\n\n- 10/03 快晴、オリオン座流星群\n",
        "docs/setup-guide.md": "# Setup\n\nMount the camera facing north.\n",
        "tests/test_forecast.py": "def test_no_frames():\n    assert True\n",
        "tests/test_forecast_models.py": "def test_models():\n    assert True\n",
        "tests/test_storage.py": "def test_recent():\n    assert True\n",
        "src/aurora/models/__init__.py": "",
        "src/aurora/models/forecast_ml.py": "# A learned clear-sky model.\n",
        "src/aurora/models/cloud_cover.py": "# Cloud cover from a frame.\n",
        "notebooks/forecast-tuning.ipynb": '{"cells": [], "nbformat": 4}\n',
        "notebooks/cloud-cover.ipynb": '{"cells": [], "nbformat": 4}\n',
        "scripts/plot_forecast.py": "# Plot a month of forecasts.\n",
        "scripts/fetch_frames.sh": "#!/bin/sh\nrsync -a pi:frames/ frames/\n",
    }
    # A month of nightly reports: what makes searching worth it.
    for day in range(1, 32):
        files[f"reports/2026-10/forecast-2026-10-{day:02d}.md"] = (
            f"# Forecast for 2026-10-{day:02d}\n\nClear sky: {(day * 37) % 100}%\n")
    if backup:
        for day in range(25, 32):
            del files[f"reports/2026-10/forecast-2026-10-{day:02d}.md"]
        files["README.md"] = _README.replace("Runs unattended on a Raspberry Pi",
                                             "Runs on a laptop")
        files["src/aurora/forecast.py"] = _FORECAST_PY.replace("0.3 * moon", "0.5 * moon")
        del files["data/metrics.csv"]
        del files["docs/観測メモ.md"]
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    with zipfile.ZipFile(root / "frames-2026-10.zip", "w") as z:
        for day in range(1, 7):
            info = zipfile.ZipInfo(f"frames/2026-10-{day:02d}/meta.json",
                                   (2026, 10, day, 23, 30, 0))
            z.writestr(info, json.dumps({"day": day, "frames": 480 + day}) + "\n")
        z.writestr(zipfile.ZipInfo("frames/README.txt", (2026, 10, 1, 9, 0, 0)),
                   "One folder per night.\n")


#: Imported by the demo XeFM at startup (``sitecustomize``). Log lines name
#: full paths, and the home here is a temporary folder with a long,
#: meaningless name: write it as ``~``. Every line, whether from a logger or
#: the app's own status messages, reaches the log pane through
#: ``LogView.append``.
_SITECUSTOMIZE = """\
import os

from puikit.widgets.log_view import LogView

_HOMES = sorted({os.path.expanduser("~"), os.path.realpath(os.path.expanduser("~"))},
                key=len, reverse=True)
_append = LogView.append


def _append_home_as_tilde(self, text, style=None):
    for home in _HOMES:
        text = text.replace(home, "~")
    return _append(self, text, style)


LogView.append = _append_home_as_tilde
"""


def _prepare_home(home: trial.TryHome) -> None:
    """The template config and the tools folder made already, so a fresh start
    logs nothing about creating them, ``_SITECUSTOMIZE`` on the path, and the
    coloured-underline cursor on.

    Copying asks no confirmation: the dialog names the destination by its
    full path, the temporary one."""
    template = Path(trial.__file__).parent / "_config.py"
    config = template.read_text(encoding="utf-8")
    assert "    CONFIRM_COPY = True" in config
    (home.xefm / "config.py").write_text(
        config.replace("    CONFIRM_COPY = True", "    CONFIRM_COPY = False"), encoding="utf-8")
    (home.xefm / "tools").mkdir(exist_ok=True)
    site = home.root / ".demo-site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(_SITECUSTOMIZE, encoding="utf-8")
    environment = home.environment()
    environment["PYTHONPATH"] = os.pathsep.join([str(site), environment["PYTHONPATH"]])
    # The recording's terminal can draw a coloured underline, so the cursor is
    # the rule under the row rather than the [ ] brackets a terminal without
    # one gets.
    environment["PUIKIT_UNDERLINE_COLOR"] = "1"
    home.environment = lambda: environment


# --- the script --------------------------------------------------------------

def typed(text: str) -> list:
    """``text`` one character at a time, as a person types it."""
    out = []
    for ch in text:
        out += [{"text": ch}, {"pause": TYPE_DELAY}]
    return out


#: (intent, keys, hold seconds[, patience]). ``hold`` is how long the step's
#: result stays on screen in the GIF.
SCENES = [
    ("look around", [], 1.0),
    ("into src", ["Down"] + [{"pause": 0.08}, "Down"] * 4 + ["Enter"], 0.6),
    ("into aurora", ["Enter"], 0.6),
    ("to __main__", ["Down", {"pause": 0.1}, "Down"], 0.4),
    ("view it", ["V"], 1.2),
    ("scroll", ["PageDown"], 1.0),
    ("close", ["Esc"], 0.3),
    ("back to the top", ["Backspace", {"pause": 0.2}, "Backspace"], 0.6),
    ("isearch", ["F"] + typed("rea"), 1.2),
    ("end isearch", ["Enter"], 0.3),
    ("view README", ["V"], 0.6),
    ("render markdown", ["M"], 2.2),
    ("close", ["Esc"], 0.3),
    ("quick view", ["Up", "Shift-V"], 1.0),
    ("quick view next", ["Down"], 1.0),
    ("quick view close", ["Shift-V"], 0.3),
    ("menu", ["F10"], 0.6),
    ("to View", ["Right", {"pause": 0.2}, "Right", {"pause": 0.2}, "Right",
                 {"pause": 0.2}, "Right"], 0.6),
    ("to Theme", ["Down"] + [{"pause": 0.12}, "Down"] * 9, 0.5),
    ("theme submenu", ["Right"], 0.6),
    ("to Dracula", ["Down", {"pause": 0.25}, "Down"], 1.2),
    ("apply theme", ["Enter"], 2.0),
    ("into the zip", ["Up", "Up", "Up", "Enter"], 0.6),
    ("into frames", ["Enter"], 0.8),
    ("out of the zip", ["Backspace", {"pause": 0.2}, "Backspace"], 0.5),
    ("flat view", ["Shift-B"], 1.2),
    ("filter", [";"] + typed("*.py"), 1.2),
    ("filter apply", ["Enter"], 1.0),
    ("clear filter", [":"], 0.3),
    ("flat view off", ["Shift-B"], 0.5),
    ("find files", ["Shift-F"] + typed("*forecast*"), 2.2),
    ("find files feed", ["Enter"], 1.2),
    ("scroll the results", ["PageDown"], 0.8),
    ("back", ["Backspace"], 0.3),
    ("compare dirs", ["+"], 1.2),
    ("expand data", ["Right"], 0.6),
    ("to src", ["Down"] + [{"pause": 0.08}, "Down"] * 6, 0.3),
    ("expand src", ["Right"], 0.5),
    ("expand aurora", ["Down", {"pause": 0.15}, "Right"], 0.8),
    ("to forecast.py", ["Down"] + [{"pause": 0.1}, "Down"] * 3, 0.8),
    ("diff it", ["Enter"], 2.2),
    ("close diff", ["Esc"], 0.4),
    ("close compare", ["Q"], 0.3),
    ("into docs", ["Down", "Enter"], 0.5),
    ("select all", ["Home"], 1.0),
    ("copy", ["C"], 1.5),
    ("palette", ["Ctrl-T"] + typed("tab"), 1.5),
    ("palette run", ["Enter"], 1.0),
    ("back to the other tab", ["Ctrl-PageUp"], 0.6),
    ("look around", ["Down", {"pause": 0.15}, "Down", {"pause": 0.15}, "Tab"], 2.5),
]


def steps() -> list[trial.Step]:
    keys = trial._keys_module()
    return [trial.Step(keys=keys.sequence(k), intent=intent,
                       patience=rest[0] if rest else 10.0)
            for intent, k, _hold, *rest in SCENES]


# --- retiming ----------------------------------------------------------------

def retime(src: Path, dst: Path) -> float:
    """Squeeze every gap to ``MAX_GAP`` and add each step's hold before the
    next step's marker (and the last one's at the end). Markers are dropped.
    The new length, in seconds."""
    lines = src.read_text(encoding="utf-8").splitlines()
    header, events = lines[0], [json.loads(line) for line in lines[1:]]
    holds = [scene[2] for scene in SCENES]
    out, clock, last, step = [], 0.0, 0.0, 0
    for t, kind, data in events:
        clock += min(t - last, MAX_GAP)
        last = t
        if kind == "m":
            if step > 0:
                clock += holds[step - 1]
            step += 1
            continue
        out.append([round(clock, 4), kind, data])
    clock += holds[step - 1] if step else 0.0
    # A last no-op event, so the final hold is part of the timeline.
    out.append([round(clock, 4), "o", ""])
    dst.write_text("\n".join([header] + [json.dumps(e, ensure_ascii=False)
                                         for e in out]) + "\n", encoding="utf-8")
    return clock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", type=Path, help="output directory")
    parser.add_argument("--no-gif", action="store_true",
                        help="record and retime only (read the screens)")
    parser.add_argument("--font-size", type=int, default=14)
    # 1.125, not agg's 1.4: at 120x40 it makes the GIF 16:10, the shape of
    # the GUI video it sits beside in the README, so the two match in height.
    parser.add_argument("--line-height", type=float, default=1.125)
    args = parser.parse_args(argv)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    screens = out / "screens"
    shutil.rmtree(screens, ignore_errors=True)

    home = trial.TryHome()
    try:
        _prepare_home(home)
        projects = home.root / "projects"
        _project(projects / "aurora")
        _project(projects / "aurora-backup", backup=True)
        raw = out / "demo.raw.cast"
        result = trial.run_script(
            home, trial.xefm_argv(projects / "aurora", projects / "aurora-backup"),
            steps(), screens=screens, record=raw, rows=ROWS, cols=COLS)
    finally:
        home.remove()
    print(f"ran {result.steps} of {len(SCENES)} steps; screens in {screens}")
    if result.unsettled:
        print("unsettled: " + ", ".join(map(str, result.unsettled)))
    if result.exited is not None:
        print(f"XeFM exited during the script (status {result.exited})")
        return 1
    cast = out / "demo.cast"
    length = retime(raw, cast)
    print(f"retimed: {length:.1f}s -> {cast}")
    if args.no_gif:
        return 0
    gif = out / "demo.gif"
    subprocess.run(["agg", "--quiet", "--font-size", str(args.font_size),
                    "--line-height", str(args.line_height),
                    "--idle-time-limit", "60", "--last-frame-duration", "0",
                    str(cast), str(gif)], check=True)
    print(f"gif: {gif} ({gif.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
