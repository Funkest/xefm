"""Check the real extensions against this working tree (#713, plan §7.3).

For every package in crftwr/xefm-extensions, run what ``xefm ext check`` runs
and the package's own tests, against the XeFM checked out here. The API
snapshot says what changed; this says whether anyone it was promised to
noticed.

The packages come from ``../xefm-extensions`` when that checkout exists, and
are otherwise cloned (shallow) into ``temp/xefm-extensions``. The check never
reads ``~/.xefm``: an installed copy of the same package is not a conflict
here.

Usage (from the repo root):
    PYTHONPATH=. python tools/api_compat.py [PACKAGE_DIR_OR_CHECKOUT]
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/crftwr/xefm-extensions.git"


def checkout(argument: str | None) -> Path:
    if argument:
        return Path(argument).resolve()
    sibling = ROOT.parent / "xefm-extensions"
    if sibling.is_dir():
        return sibling
    target = ROOT / "temp" / "xefm-extensions"
    if target.is_dir():
        subprocess.run(["git", "-C", str(target), "pull", "-q", "--ff-only"], check=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--depth", "1", REPO, str(target)], check=True)
    return target


def main(argv=None) -> int:
    from xefm import extensions as ext

    args = sys.argv[1:] if argv is None else argv
    base = checkout(args[0] if args else None)
    packages = [base] if (base / ext.MANIFEST).is_file() else sorted(
        p for p in base.iterdir() if (p / ext.MANIFEST).is_file())
    if not packages:
        print(f"no extension packages under {base}", file=sys.stderr)
        return 1

    failed = []
    for root in packages:
        manifest, problems = ext.check_package(root, machine=False)
        bad = ext.errors(problems)
        previews = ext.preview_uses(manifest) if manifest is not None else []
        print(f"== {root.name}: {len(bad)} error(s), {len(problems) - len(bad)} "
              f"warning(s), {len(previews)} Preview use(s)")
        for problem in problems + previews:
            print(f"   {problem}")
        tests = root / "tests"
        if tests.is_dir():
            env = dict(os.environ, PYTHONPATH=os.pathsep.join(
                filter(None, [str(ROOT), os.environ.get("PYTHONPATH")])))
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
                cwd=root, env=env, capture_output=True, text=True)
            summary = (result.stdout.strip().splitlines() or ["(no output)"])[-1]
            print(f"   tests: {summary}")
            if result.returncode != 0:
                print(result.stdout + result.stderr)
                failed.append(f"{root.name} (tests)")
        if bad:
            failed.append(f"{root.name} (check)")

    if failed:
        print(f"\nFAILED: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"\nok: {len(packages)} package(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
