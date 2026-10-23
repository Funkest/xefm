"""(intent, actions, hold). Coordinates are in points (960x600)."""

ROW0, ROW_H = 94, 17          # first file row's centre, row pitch
VIEW_MENU = [303, 14]
THEME_ITEM = [330, 369]
THEMES = {"Shinagawa": 553, "Phosphor": 577}


def row(n, x=60, right=False):
    return [x + (480 if right else 0), ROW0 + n * ROW_H]


def pick_theme(name):
    return [{"click": VIEW_MENU}, {"pause": 0.4},
            {"move": THEME_ITEM}, {"pause": 0.5},
            {"move": [530, 369]}, {"pause": 0.2},
            {"move": [530, THEMES[name]]}, {"pause": 0.5},
            {"click": [530, THEMES[name]]}]


SCENES = [
    ("look", [], 1.5),
    ("click photos", [{"click": row(3)}], 0.4),
    ("open photos", [{"dclick": row(3)}], 1.0),
    ("quick view", ["Shift-V"], 1.5),
    ("next", ["Down"], 0.8),
    ("next", ["Down"], 0.8),
    ("next", ["Down"], 1.0),
    ("quick view off", ["Shift-V"], 0.3),
    ("image viewer", ["Enter"], 1.5),
    ("zoom", ["=", {"pause": 0.3}, "="], 0.8),
    ("pan", ["Shift-Right", {"pause": 0.2}, "Shift-Right"], 0.8),
    ("fit", ["0"], 0.6),
    ("next image", ["Down"], 1.0),
    ("close", ["Esc"], 0.4),
    ("up", ["Backspace"], 0.6),
    ("theme Shinagawa", pick_theme("Shinagawa"), 3.0),
    ("README", [{"click": row(11)}], 0.4),
    ("view README", ["V"], 1.0),
    ("render markdown", ["M"], 2.2),
    ("close", ["Esc"], 0.4),
    ("context menu", [{"rclick": row(1)}], 1.5),
    ("close menu", ["Esc"], 0.4),
    ("drag photos to the right pane", [{"drag": row(3) + [700, 400]}], 1.5),
    ("confirm the move", [{"click": [386, 373]}], 1.2),
    ("search", ["Shift-F", {"text": "*forecast*"}], 2.2),
    ("feed", ["Enter"], 1.0),
    ("scroll", [{"scroll": [300, 300, 6]}], 1.0),
    ("back", ["Backspace"], 0.5),
    ("theme Phosphor", pick_theme("Phosphor"), 3.0),
    ("compare", ["Shift-="], 1.2),
    ("expand data", ["Right"], 0.6),
    ("to src", ["Down"] * 8, 0.3),
    ("expand src", ["Right"], 0.5),
    ("expand aurora", ["Down", "Right"], 0.8),
    ("to forecast.py", ["Down"] * 4, 0.8),
    ("diff", ["Enter"], 2.2),
    ("close diff", ["Esc"], 0.4),
    ("close compare", ["Q"], 0.4),
    ("palette", ["Ctrl-T", {"text": "tab"}], 1.5),
    ("new tab", ["Enter"], 1.0),
    ("end", [], 2.5),
]
