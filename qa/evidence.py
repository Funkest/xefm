"""XeFM's evidence tools: facts about what a room left, for the operator.

    python qa/evidence.py check <room>                 the scenario's mechanical check
    python qa/evidence.py friction <room>              where the transcript shows it stumbling
    python qa/evidence.py calls <room>                 every `xefm` command it ran
    python qa/evidence.py config <room> [--before] [--backend desktop]
    python qa/evidence.py keys <room> <key> [--before] [--backend desktop]

Every answer is JSON, read from the room's own record - its evidence/ and
transcript - never from the live machine. The checks are the clean room's,
kept: each scenario's module in qa/checks/ asks the questions XeFM itself
would answer (its ConfigManager, its key parser, its association matcher).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE / "checks"))

import friction  # noqa: E402
import outcome  # noqa: E402


def _reply(room: pathlib.Path) -> str:
    replies = []
    path = room / "transcript.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("type") == "result":
                replies.append(str(event.get("result", "")))
    return replies[-1] if replies else ""


def _calls(room: pathlib.Path) -> list[str]:
    log = room / "evidence" / "calls" / "xefm-calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _scenario(room: pathlib.Path) -> str:
    """The scenario a room ran: its name, less any variant."""
    return room.name.split(".", 1)[0]


def read_outcome(room: pathlib.Path) -> outcome.Outcome:
    evidence = room / "evidence"
    after = evidence / "after" / "config.py"
    installed = sorted(p for p in (evidence / "extensions").glob("*") if p.is_dir()) \
        if (evidence / "extensions").is_dir() else []
    return outcome.Outcome(
        before=(evidence / "before" / "config.py").read_text(encoding="utf-8"),
        after=after.read_text(encoding="utf-8") if after.exists() else None,
        reply=_reply(room), xefm_calls=_calls(room), room=room, installed=installed)


def check(room: pathlib.Path) -> dict:
    module = outcome.load_checks([_scenario(room)])[0]
    found = read_outcome(room)
    failures = outcome.common_failures(found, module.KIND) + module.check(found)
    return {"scenario": module.NAME, "failures": failures,
            "config_changed": found.changed, "load_errors": found.load_errors()
            if found.after is not None else ["config.py is gone"],
            "installed": [p.name for p in found.installed]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidence.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (("check", "the scenario's mechanical check: failures, empty "
                                 "when there are none"),
                       ("friction", "where the transcript shows the room stumbling"),
                       ("calls", "every `xefm` command the room ran")):
        commands.add_parser(name, help=text).add_argument("room")
    for name, text in (("config", "config.py's values as XeFM loads them"),
                       ("keys", "the actions a key runs, preset and KEY_BINDINGS laid "
                                "together")):
        command = commands.add_parser(name, help=text)
        command.add_argument("room")
        if name == "keys":
            command.add_argument("key")
        command.add_argument("--before", action="store_true",
                             help="the fixture the room started from")
        command.add_argument("--backend", default="tui", choices=["tui", "desktop"])
    args = parser.parse_args(argv)
    room = pathlib.Path(args.room)
    if args.command == "check":
        answer = check(room)
    elif args.command == "friction":
        answer = [dataclasses.asdict(i) for i in friction.incidents(room / "transcript.jsonl")]
    elif args.command == "calls":
        answer = _calls(room)
    else:
        found = read_outcome(room)
        text = found.before if args.before else (found.after or "")
        loaded = outcome.inspect_config(text, args.backend)
        if args.command == "config":
            answer = loaded
        else:
            keymap = outcome.effective_keymap(loaded["values"], backend=args.backend)
            answer = {"key": args.key, "actions": outcome.actions_on(keymap, args.key)}
    print(json.dumps(answer, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
