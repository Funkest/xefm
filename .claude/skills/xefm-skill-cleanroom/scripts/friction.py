"""Where a room stumbled, read off its transcript - including what it never wrote down.

    PYTHONPATH=. python .claude/skills/xefm-skill-cleanroom/scripts/friction.py <room>

QUESTIONS.md is what the room *noticed* it had to guess. It is not everything
that went wrong: a command that failed and was quietly fixed, `xefm ext check`
complaining before it passed, a search of the skill that found nothing,
config.py rewritten twice - none of those is a question the room thought to
ask, and each is a place where the skill cost it something. Keyhac's clean
room, which this one was modelled on, added the same reading after its
first runs showed every room meeting one blank tool answer that only one of
them mentioned (crftwr/keyhac#196).

So this reads the record, not the room's account of it, and lists each such
moment as an incident with the line that shows it. run_room.py writes them to
the room's FRICTION.md and into the run's FINDINGS.md beside the questions;
triage both the same way (SKILL.md, Score). An incident no question mentions
is the more valuable kind - it is the gap nobody noticed.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re
import sys


@dataclasses.dataclass
class Incident:
    kind: str           # one of KINDS
    step: int           # the tool call it is about, counting from 1 (0: none)
    detail: str         # what happened, in one line
    evidence: str = ""  # the line of the record that shows it

    def line(self) -> str:
        where = f"step {self.step}: " if self.step else ""
        shown = f"\n    > {self.evidence}" if self.evidence else ""
        return f"- **{self.kind}** - {where}{self.detail}{shown}"


#: What each kind means, for the reader of FRICTION.md.
KINDS = {
    "tool error": "a tool call failed or was refused",
    "command trouble": "a command ran, and what it printed was an error",
    "searched, found nothing": "the room looked in the skill for something that is not there",
    "rework": "the same file written, or the same install run, more than once",
    "session": "the session itself did not end cleanly",
    "said so": "the room said, as it worked, that it was unsure or had it wrong",
}

#: In a command's output: it went wrong. Per line, so one error among a test
#: run's passing lines is found and the passing lines are not.
TROUBLE = re.compile(
    r"Traceback|^\s*(error|ERROR)\b|\berror:|\bFAILED\b|\d+ failed\b|"
    r"\bnot found\b|No such file|refused in the clean room", re.MULTILINE)

#: The room's bookkeeping: saying it is now writing up its guesses is not a
#: guess.
BOOKKEEPING = re.compile(
    r"QUESTIONS|\b(writ\w*|record\w*|not\w*|log\w*) (down |up )?(the |my |what |in )",
    re.IGNORECASE)

#: The file tools' own "nothing here" answers.
NOTHING_FOUND = re.compile(r"^(No matches found|No files found)", re.IGNORECASE)

#: In the room's own words, while it works: doubt and correction, not caution.
UNSURE = re.compile(
    r"not documented|undocumented|doesn't say|does not say|isn't (stated|said|clear)|"
    r"unclear|not sure|no way to|can't tell|cannot tell|couldn't find|could not find|"
    r"\bguess|assum(e|ing)\b|didn't work|did not work|that failed|wrong|mistake|"
    r"let me (try|retry) again|try again", re.IGNORECASE)
# Not "instead": "so I edit that entry instead of adding one" is a choice
# made with the skill's help, and that is most of what the word marks.

#: Where a sentence ends: a stop followed by space, or a line break - not the
#: "." inside every file name the room mentions.
_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n")


def _events(transcript: pathlib.Path) -> list[dict]:
    events = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return str(content or "")


def _parts(event: dict) -> list[dict]:
    """An event's content parts. Not every event has them: a refusal is
    logged as a system event whose "message" is the refusal's text."""
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [part for part in content or [] if isinstance(part, dict)] \
        if isinstance(content, list) else []


def _calls(events: list[dict]) -> list[dict]:
    """Every tool call, in order, with its result and whether it failed."""
    calls, by_id = [], {}
    for event in events:
        for part in _parts(event):
            if event.get("type") == "assistant" and part.get("type") == "tool_use":
                call = {"name": part.get("name", ""), "input": part.get("input") or {},
                        "result": "", "is_error": False}
                calls.append(call)
                by_id[part.get("id")] = call
            elif event.get("type") == "user" and part.get("type") == "tool_result":
                if call := by_id.get(part.get("tool_use_id")):
                    call["result"] = _text(part.get("content"))
                    call["is_error"] = bool(part.get("is_error"))
    return calls


def _sentence(text: str, match: re.Match, width: int = 220) -> str:
    starts = [m.end() for m in _BOUNDARY.finditer(text, 0, match.start())]
    start = starts[-1] if starts else 0
    after = _BOUNDARY.search(text, match.end())
    sentence = " ".join(text[start:after.start() if after else len(text)].split())
    return sentence if len(sentence) <= width else sentence[:width - 1] + "…"


def _first_line(text: str, pattern: re.Pattern | None = None) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if pattern is not None:
        lines = [line for line in lines if pattern.search(line)] or lines
    return (lines[0] if lines else "")[:220]


def _command(call: dict, width: int = 100) -> str:
    command = " ".join(str(call["input"].get("command", "")).split())
    return command if len(command) <= width else command[:width - 1] + "…"


def _skill_lines(room: pathlib.Path) -> set[str]:
    """Every line of the skill the room was given. A command that shows a
    skill page prints them, and a page that says "error:" is not an error."""
    lines = set()
    for path in (room / "skills").rglob("*"):
        if path.is_file():
            try:
                lines.update(line.strip() for line in
                             path.read_text(encoding="utf-8").splitlines())
            except (UnicodeDecodeError, OSError):
                continue
    lines.discard("")
    return lines


def _trouble(result: str, quoted: set[str]) -> list[str]:
    """The lines of a command's output that say it went wrong - not the ones
    it printed out of a skill page."""
    return [line.strip() for line in result.splitlines()
            if TROUBLE.search(line) and not _quoted(line.strip(), quoted)]


def _quoted(line: str, quoted: set[str]) -> bool:
    # A long output is cut short mid-line, so part of a skill line counts too.
    return line in quoted or (len(line) >= 20 and any(line in q for q in quoted))


def _failure(call: dict, quoted: set[str]) -> tuple[str, str]:
    """What a failed call was, and the line that says why. A refusal names
    the command and nothing more: its text is the same every time. A failed
    command's first line is its exit code; the reason is further down."""
    result = call["result"].replace("<tool_use_error>", "").replace("</tool_use_error>", "")
    if call["name"] != "Bash":
        return f"{call['name']} failed", _first_line(result)
    if "Permission to use" in result or "has been denied" in result:
        return f"refused: `{_command(call)}`", ""
    lines = [line.strip() for line in result.splitlines()
             if line.strip() and not re.fullmatch(r"Exit code \d+", line.strip())]
    trouble = _trouble(result, quoted)
    why = trouble[0] if trouble else lines[-1] if lines else ""
    return f"`{_command(call)}` failed", why[:220]


def _written(call: dict) -> str | None:
    """The user-side file a call replaced wholesale, if it did. Edits are
    not counted: several small edits to one file is how editing goes."""
    if call["name"] == "Write":
        path = str(call["input"].get("file_path", "")).replace("\\", "/")
        if "/.xefm/" in path:
            return "~/.xefm/" + path.split("/.xefm/", 1)[1]
    return None


def _installs(call: dict) -> str | None:
    if call["name"] == "Bash":
        command = str(call["input"].get("command", ""))
        if found := re.search(r"\bxefm ext install\s+(\S+)", command):
            return found.group(1)
    return None


def incidents(transcript: pathlib.Path) -> list[Incident]:
    """Every stumble in one room's transcript, in the order they happened."""
    if not transcript.exists():
        return [Incident("session", 0, "no transcript - the room never ran")]
    events = _events(transcript)
    calls = _calls(events)
    quoted = _skill_lines(transcript.parent)
    found: list[Incident] = []
    writes: dict[str, list[int]] = {}
    installs: dict[str, list[int]] = {}

    for step, call in enumerate(calls, 1):
        name = call["name"]
        if call["is_error"]:
            found.append(Incident("tool error", step, *_failure(call, quoted)))
        elif name == "Bash" and (trouble := _trouble(call["result"], quoted)):
            found.append(Incident("command trouble", step, f"`{_command(call)}`",
                                  trouble[0][:220]))
        elif name in ("Grep", "Glob") and NOTHING_FOUND.match(call["result"].strip()):
            found.append(Incident("searched, found nothing", step,
                                  f"{name} {call['input'].get('pattern', '')!r} came back empty"))
        if target := _written(call):
            writes.setdefault(target, []).append(step)
        if target := _installs(call):
            installs.setdefault(target, []).append(step)

    for what, steps, verb in [(t, s, "written") for t, s in writes.items()] + \
                             [(t, s, "installed") for t, s in installs.items()]:
        if len(steps) > 1:
            found.append(Incident("rework", steps[-1],
                                  f"{what} {verb} {len(steps)} times "
                                  f"(steps {', '.join(map(str, steps))})"))

    failed_at = {i.step for i in found if i.kind in ("tool error", "command trouble")}

    # The final reply is read on its own below; here it would count twice.
    final = next((e.get("result", "") or "" for e in reversed(events)
                  if e.get("type") == "result"), "")
    step = 0
    for event in events:
        if event.get("type") == "assistant":
            for part in _parts(event):
                if part.get("type") == "tool_use":
                    step += 1
                elif part.get("type") == "text":
                    text = part.get("text", "")
                    if final and text.strip() == final.strip():
                        continue
                    for match in UNSURE.finditer(text):
                        sentence = _sentence(text, match)
                        # Writing up its guesses is bookkeeping, and "so I'll
                        # do it another way" right after a failure is that
                        # failure again, already listed.
                        if BOOKKEEPING.search(sentence) or step in failed_at:
                            continue
                        found.append(Incident("said so", step, "while working", sentence))
        elif event.get("type") == "result":
            if event.get("subtype") not in (None, "success") or event.get("is_error"):
                found.append(Incident("session", step,
                                      f"ended as {event.get('subtype')!r}"
                                      + (" - it ran out of turns"
                                         if "max_turns" in str(event.get("subtype")) else "")))
            for match in re.finditer(r"mistake|by accident|I overwrote|wrongly", final,
                                     re.IGNORECASE):
                found.append(Incident("said so", step, "in its final reply",
                                      _sentence(final, match)))

    # Two doubtful words in one sentence are one incident.
    unique = {(i.kind, i.step, i.detail, i.evidence): i for i in found}
    return sorted(unique.values(), key=lambda incident: incident.step)


def report(room: pathlib.Path, failures: list[str] | None = None) -> str:
    """FRICTION.md for one room: the checks' failures, then the incidents,
    grouped by kind."""
    found = incidents(room / "transcript.jsonl")
    lines = [f"# Where {room.name} stumbled", "",
             "Read off the transcript by scripts/friction.py, after the run. "
             "QUESTIONS.md is what the room noticed; this is what the record "
             "shows, noticed or not. Triage both the same way: skill gap, out "
             "of scope, or tooling.", ""]
    if failures:
        lines += ["## The checks failed", ""] + [f"- {f}" for f in failures] + [""]
    if not found:
        lines += ["Nothing: no failed call, no command that printed an error, no "
                  "search that came back empty, no rework, no doubt said out loud.", ""]
    for kind, meaning in KINDS.items():
        mine = [incident for incident in found if incident.kind == kind]
        if mine:
            lines += [f"## {kind} ({len(mine)}) - {meaning}", ""]
            lines += [incident.line() for incident in mine] + [""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        raise SystemExit(__doc__)
    print(report(pathlib.Path(argv[0])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
