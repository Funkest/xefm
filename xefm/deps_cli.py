"""``xefm deps …`` — sync the Python packages ``~/.xefm/requirements.txt``
declares (#664), from a shell and without opening a window.

A thin layer over :mod:`xefm.python_packages`, the same code the Sync Python
Packages action runs inside the app.
"""

from __future__ import annotations

import argparse

from xefm import python_packages as pp


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xefm deps",
        description="Install the Python packages listed in "
                    "~/.xefm/requirements.txt where this XeFM can import them.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="make ~/.xefm/site-packages match requirements.txt "
                   "(reaches the network)")
    sub.add_parser("status", help="say whether a sync is needed (offline)")
    return parser


def main(argv: list[str] | None = None, layout: pp.Layout | None = None) -> int:
    args = _parser().parse_args(argv)
    layout = layout or pp.Layout()

    if args.command == "status":
        status = pp.check(layout)
        if status.state == pp.UNUSED:
            print(f"nothing declared in {layout.requirements}")
            return 0
        if status.state == pp.IN_SYNC:
            print(f"in sync: {layout.target}")
            return 0
        print(status.message)
        return 1

    try:
        result = pp.sync(layout, log=print)
    except pp.SyncError as e:
        print(f"sync failed: {e}")
        return 1
    for line in result.installed:
        print(f"installed: {line}")
    if result.pruned:
        print(f"provided by XeFM itself: {', '.join(result.pruned)}")
    if result.pending_restart:
        print(f"{layout.target} is in use; the new packages take its place "
              "when XeFM next starts")
    else:
        print(f"in sync: {layout.target}")
    return 0
