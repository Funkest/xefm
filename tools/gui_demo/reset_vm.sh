#!/bin/sh
# Before each take: a fresh home in the VM (built by prep_home.py), the
# window frame filling the 960x600 screen, and XeFM started on it.
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$HERE/../../temp/gui-demo"
"$HERE/vm.sh" 'pkill -x XeFM; sleep 1; rm -rf ~/projects ~/.xefm'
(cd "$WORK/home" && tar cf - projects .xefm) | "$HERE/vm.sh" 'tar xf - -C ~'
"$HERE/vm.sh" 'defaults write com.xefm.app "NSWindow Frame XeFMMainWindow" "0 0 960 570 0 0 960 600 "; open -a XeFM'
sleep 6
