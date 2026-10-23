"""One-time: open the home's protected folders in XeFM so macOS asks for
access, and click Allow on each prompt (at its place on the 960x600 screen;
check the stills). Run after reset_vm.sh:

    SCENES=scenes_grant $VENV/bin/python tools/gui_demo/drive.py still temp/gui-demo/grant
"""

ALLOW = [698 * 960 // 1280, 309 * 600 // 800]

SCENES = [("home", ["Backspace", {"pause": 0.4}, "Backspace"], 1.0)]
for name in ["Desktop", "Documents", "Downloads"]:
    SCENES += [
        (name, ["f", {"text": name}, "Enter", "Enter"], 1.5),
        (f"allow {name}", [{"click": ALLOW}], 0.8),
        (f"back from {name}", ["Backspace"], 0.6),
    ]
