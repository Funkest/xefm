# GUI demo recorder (prototype)

Records the README's **GUI (macOS)** video: XeFM.app in a Tart macOS VM,
driven and captured over the Virtualization framework's VNC server. Why it
works this way, and the traps, are in
[doc/dev/DEMO_RECORDING_SYSTEM.md](../../doc/dev/DEMO_RECORDING_SYSTEM.md).
This is a prototype: it works, but each step is run by hand.

Run everything from the repository root. Run-time files (ssh key, VNC URL,
the generated home, recordings) go to `temp/gui-demo/`, which git ignores.

| File | What it is |
|---|---|
| `setup_vm.sh` | one-time: clone the VM, then provision it (ssh key, XeFM.app, Dock, 960x600 HiDPI) |
| `run_vm.sh` | boot the VM with the VNC server and no viewer |
| `vncd.py` | the daemon holding the one VNC connection; serves key / pointer / still / record over a Unix socket |
| `rfb.py` | the minimal VNC (RFB 3.8) client it uses |
| `drive.py` | runs a scene module against the daemon; a still after each scene, optionally the recording |
| `scenes.py` | the demo itself: `(intent, actions, hold)`, coordinates in points on 960x600 |
| `scenes_grant.py` | one-time: trigger and allow the guest's folder-permission prompts |
| `prep_home.py` | builds the home copied into the VM before each take |
| `reset_vm.sh` | before each take: fresh home, window frame, XeFM started |
| `modes.py` | lists or sets the guest's display mode (runs in the VM) |
| `vm.sh` | ssh into the VM |

## Once

```bash
python3 -m venv temp/gui-demo/venv
temp/gui-demo/venv/bin/pip install -r tools/gui_demo/requirements.txt
VENV=temp/gui-demo/venv

tools/gui_demo/setup_vm.sh create
tools/gui_demo/run_vm.sh &              # wait ~30 s for the guest to log in
tools/gui_demo/setup_vm.sh provision    # needs /Applications/XeFM.app on the host

PYTHONPATH=. python tools/gui_demo/prep_home.py temp/gui-demo/home
$VENV/bin/python tools/gui_demo/vncd.py temp/gui-demo/tart-run.log &
tools/gui_demo/reset_vm.sh
SCENES=scenes_grant $VENV/bin/python tools/gui_demo/drive.py still temp/gui-demo/grant
```

Look at `temp/gui-demo/grant/*.png`: each folder's prompt should have been
answered. A prompt left open takes keyboard focus and breaks every take
after it.

Also look for a notification banner in the top-right corner. `provision`
turns off the Tips service from the next login on, but a banner already
posted stays until it is closed: hover it and click its close button (at
about `{"click": [604, 52]}` on 960x600). Check the first still of every
take for this.

## Each session

```bash
tools/gui_demo/run_vm.sh &
$VENV/bin/python tools/gui_demo/vncd.py temp/gui-demo/tart-run.log &
```

**Start `vncd.py` once per boot, and leave it running.** A second VNC
connection, or restarting the daemon, can crash Tart. If that happens, the
VM stops with it: run both commands again.

## Each take

```bash
tools/gui_demo/reset_vm.sh
$VENV/bin/python tools/gui_demo/drive.py still temp/gui-demo/try1   # stills only
tools/gui_demo/reset_vm.sh
$VENV/bin/python tools/gui_demo/drive.py record temp/gui-demo/take1 # + raw.mp4
```

Tune `scenes.py` against the stills (`NN.png` after each scene, and
`steps.json` with the timings). Key names follow the keymap: `v` and `V` are
both the v key; write `Shift-V` for the capital. `drive.py` adds Shift for
shifted symbols such as `*` and `+`, which the VNC server would otherwise
drop.

The raw take is 1920x1200 at 30 fps. The README file is encoded from it:

```bash
ffmpeg -i temp/gui-demo/take1/raw.mp4 -vf "scale=960:600:flags=lanczos" \
       -c:v libx264 -preset slow -crf 24 -pix_fmt yuv420p -movflags +faststart -an \
       temp/gui-demo/take1/demo-960x600.mp4
```

Upload that MP4 to GitHub (drag it into an issue comment) and put the
`user-attachments` URL in the README, as a bare URL on its own line.
