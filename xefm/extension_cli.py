"""``xefm ext …`` — manage extension packages from a shell (#583).

Runs without opening a window, so it works the same from a pipx install, the
macOS bundle and the Windows package, which share ``~/.xefm/`` and nothing else.
Every subcommand is a thin layer over :mod:`xefm.extensions`; ``check`` is the
static validator an author (or an assistant writing a package) runs, and its
exit status says whether the package would install.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from xefm import extensions as ext


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xefm ext", description="Manage XeFM extension packages.")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="validate a package without running it")
    check.add_argument("path", help="the package directory (the one holding "
                       f"{ext.MANIFEST})")

    install = sub.add_parser("install", help="check a package and install it")
    install.add_argument("source", help="a directory, a .zip, an https:// zip "
                         "URL, or github:owner/repo[@ref]")
    install.add_argument("-y", "--yes", action="store_true",
                         help="do not ask before installing")

    uninstall = sub.add_parser("uninstall", help="remove an installed package")
    uninstall.add_argument("id")
    data = uninstall.add_mutually_exclusive_group()
    data.add_argument("--delete-data", action="store_true",
                      help="also delete ~/.xefm/extension-data/<id>/")
    data.add_argument("--keep-data", action="store_true",
                      help="keep ~/.xefm/extension-data/<id>/ (no question)")

    sub.add_parser("list", help="list packages and whether they load")
    for name, text in (("enable", "load a package again"),
                       ("disable", "keep a package installed but unloaded")):
        p = sub.add_parser(name, help=text)
        p.add_argument("id")
    sub.add_parser("sync", help="reinstall listed packages whose files are missing")
    settings = sub.add_parser("settings", help="print a package's settings class "
                              "for config.py, with every default")
    settings.add_argument("id")
    return parser


def _ask(prompt: str) -> bool:
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _print_problems(problems) -> None:
    for problem in problems:
        print(problem)


def main(argv: list[str] | None = None, layout: ext.Layout | None = None) -> int:
    args = _parser().parse_args(argv)
    layout = layout or ext.Layout()

    if args.command == "check":
        root = Path(args.path)
        others = [m for m in ext.discover(layout) if m.root.resolve() != root.resolve()]
        manifest, problems = ext.check_package(root, others=others)
        _print_problems(problems)
        bad = ext.errors(problems)
        if not bad:
            name = f"{manifest.id} {manifest.version}" if manifest else str(root)
            print(f"ok: {name}" + (f" ({len(problems)} warning(s))" if problems else ""))
            if manifest is not None and manifest.data.get("settings") is not None:
                print(f"settings: class {ext.config_class_name(manifest)} in config.py")
        return 1 if bad else 0

    if args.command == "install":
        try:
            if not args.yes:
                # Show what it adds before anything is copied: extensions run
                # in-process, with no sandbox.
                import tempfile
                with tempfile.TemporaryDirectory(prefix="xefm-ext-") as tmp:
                    root = ext.fetch(args.source, Path(tmp))
                    manifest = ext.read_manifest(root)
                    print(f"{manifest.name} {manifest.version} ({manifest.id}) adds:")
                    for line in ext.summarize(manifest) or ["(nothing)"]:
                        print(f"  {line}")
                    print("Extensions run inside XeFM with your permissions.")
                    if not _ask("Install it?"):
                        print("Not installed.")
                        return 1
            manifest = ext.install(args.source, layout)
        except ext.InstallError as exc:
            _print_problems(exc.problems)
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except ext.ManifestError as exc:
            print(exc.problem, file=sys.stderr)
            return 1
        print(f"installed {manifest.id} {manifest.version} — reload the config "
              "(Tools ▸ Reload Configuration) or restart XeFM to load it")
        return 0

    if args.command == "uninstall":
        delete = args.delete_data
        data_dir = layout.data_dir(args.id)
        if not delete and not args.keep_data and data_dir.exists():
            delete = _ask(f"Also delete its data in {data_dir}?")
        try:
            ext.uninstall(args.id, layout, delete_data=delete)
        except ext.InstallError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"uninstalled {args.id}")
        return 0

    if args.command == "list":
        installed = ext.read_installed(layout)
        manifests = ext.discover(layout)
        if not manifests and not installed:
            print(f"no extension packages in {layout.packages}")
            return 0
        seen = set()
        for manifest in manifests:
            seen.add(manifest.id)
            entry = installed.get(manifest.id)
            state = "local" if entry is None else (
                "enabled" if entry.enabled else "disabled")
            bad = ext.errors(ext.check_manifest(manifest, others=manifests,
                                                machine=False))
            note = f" — will not load: {bad[0].message}" if bad else ""
            source = f"  from {entry.source}" if entry and entry.source else ""
            print(f"{manifest.id} {manifest.version} [{state}]{source}{note}")
            if manifest.data.get("settings") is not None:
                print(f"    settings: class {ext.config_class_name(manifest)} "
                      "in config.py")
        for ext_id, entry in sorted(installed.items()):
            if ext_id not in seen:
                print(f"{ext_id} {entry.version} [missing — run `xefm ext sync`]")
        return 0

    if args.command in ("enable", "disable"):
        try:
            ext.set_enabled(args.id, args.command == "enable", layout)
        except ext.InstallError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"{args.id} {args.command}d — takes effect on the next config reload")
        return 0

    if args.command == "settings":
        manifest = next((m for m in ext.discover(layout) if m.id == args.id), None)
        if manifest is None:
            print(f"error: {args.id} is not installed", file=sys.stderr)
            return 1
        try:
            print(ext.settings_template(manifest))
        except Exception as exc:
            print(f"error: could not read the settings of {args.id}: {exc}",
                  file=sys.stderr)
            return 1
        return 0

    if args.command == "sync":
        lines = ext.sync(layout)
        for line in lines or ["nothing to reinstall"]:
            print(line)
        return 1 if any("could not" in line for line in lines) else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
