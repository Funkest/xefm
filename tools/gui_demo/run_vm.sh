#!/bin/sh
# Boot the demo VM with the Virtualization framework's VNC server and no
# viewer. --no-graphics matters: without it Tart opens Screen Sharing as a
# second VNC client, and that client coming and going crashes Tart.
# Runs until the VM stops; the vnc:// line goes to temp/gui-demo/tart-run.log.
WORK="$(cd "$(dirname "$0")/../.." && pwd)/temp/gui-demo"
mkdir -p "$WORK"
exec tart run "${XEFM_DEMO_VM:-xefm-demo}" --vnc-experimental --no-graphics > "$WORK/tart-run.log" 2>&1
