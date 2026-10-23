#!/bin/sh
# Run a command in the demo VM over ssh (the key setup_vm.sh installed).
WORK="$(cd "$(dirname "$0")/../.." && pwd)/temp/gui-demo"
exec ssh -i "$WORK/id_demo" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o LogLevel=ERROR "admin@$(tart ip "${XEFM_DEMO_VM:-xefm-demo}")" "$@"
