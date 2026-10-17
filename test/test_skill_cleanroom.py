"""The clean-room scenarios' checks can fail, and can pass (#639).

A clean-room run costs minutes and money, so a check that is wrong has to be
caught here instead: every scenario's ``check`` is run against the untouched
fixture (a run that did nothing must fail, unless doing nothing is the right
answer) and against its ``reference`` edit (a correct run must pass). The
session itself is not started here.

Run with: python -m pytest test/test_skill_cleanroom.py -v
"""

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "xefm-skill-cleanroom" / "scripts"))

import outcome  # noqa: E402
import run_room  # noqa: E402

SCENARIOS = outcome.load_scenarios()
FIXTURE = outcome.fixture_config()
#: A reply that says what a good one would, for the checks that read it.
REPLY = "Done. Ctrl-T was the command palette; choose the theme in View ▸ Theme."


def _failures(scenario, after, reply=REPLY):
    o = outcome.Outcome(before=FIXTURE, after=after, reply=reply)
    return outcome.common_failures(o, scenario.KIND) + scenario.check(o)


def test_there_are_scenarios_in_order():
    names = [s.NAME for s in SCENARIOS]
    assert len(names) >= 7 and names == sorted(names)
    for s in SCENARIOS:
        assert s.KIND in ("config", "extension")
        assert s.PROMPT.strip() and s.MUST.strip() and s.TITLE


def test_the_fixture_loads_cleanly_and_carries_the_user_s_edits():
    loaded = outcome.inspect_config(FIXTURE)
    assert loaded["errors"] == []
    values = loaded["values"]
    assert values["KEY_PRESET"] == "afx"
    assert values["KEY_BINDINGS"] == {"quit": ["Shift-Q"]}
    assert values["CONFIRM_DELETE"] is False
    assert FIXTURE.count(outcome.KEEP) == 5
    assert outcome.common_failures(outcome.Outcome(FIXTURE, FIXTURE), "config") == []


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.NAME)
def test_doing_nothing_fails(scenario):
    failures = _failures(scenario, FIXTURE)
    if getattr(scenario, "UNTOUCHED_PASSES", False):
        assert failures == []
    else:
        assert failures, "a run that changed nothing would pass this check"


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.reference],
                         ids=lambda s: s.NAME)
def test_the_reference_edit_passes(scenario):
    assert _failures(scenario, scenario.reference(FIXTURE)) == []


def test_losing_a_user_line_fails():
    edited = SCENARIOS[0].reference(FIXTURE).replace("  # keep: my notes", "")
    assert any("lost the user's line" in f for f in _failures(SCENARIOS[0], edited))


def test_regenerating_the_file_from_the_template_fails():
    regenerated = (ROOT / "xefm" / "_config.py").read_text(encoding="utf-8")
    assert _failures(SCENARIOS[0], regenerated)


def test_launching_xefm_fails():
    o = outcome.Outcome(FIXTURE, FIXTURE, xefm_calls=["ext check .", "--backend gui"])
    assert any("launch XeFM" in f for f in outcome.common_failures(o, "config"))


def test_the_session_is_restricted_and_never_bypasses(monkeypatch):
    monkeypatch.setattr(run_room, "find_claude", lambda: "claude")
    command = run_room.session_command()
    assert "--restricted" in command and "--strict-mcp-config" in command
    assert command[command.index("--permission-mode") + 1] == "dontAsk"
    assert command[command.index("-p") + 1] == run_room.PROMPT
    assert "bypassPermissions" not in " ".join(command)
    allow = json.loads(command[command.index("--settings") + 1])["permissions"]["allow"]
    # Bash is there for `xefm ext …`, never unrestricted.
    assert "Bash" not in allow and "Bash(*)" not in allow
    assert "Bash(xefm ext *)" in allow


def test_the_audit_flags_a_read_of_the_checkout(tmp_path):
    room = tmp_path / "room"
    room.mkdir()
    events = [
        {"type": "system", "subtype": "init", "slash_commands": []},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "a", "name": "Read",
             "input": {"file_path": str(ROOT / "xefm" / "_config.py")}},
            {"type": "tool_use", "id": "b", "name": "Read",
             "input": {"file_path": str(room / "skills" / "xefm" / "SKILL.md")}},
        ]}},
        {"type": "result", "result": "done"},
    ]
    transcript = room / "transcript.jsonl"
    transcript.write_text("\n".join(json.dumps(e) for e in events))
    breaches, refused = run_room.audit(room, transcript, set())
    assert any("reached into the checkout" in b for b in breaches)
    assert refused == []
    assert not any("SKILL.md" in b for b in breaches)


def test_the_room_holds_the_skill_and_nothing_else(tmp_path):
    room = run_room.build_room(SCENARIOS[0], tmp_path)
    assert sorted(p.name for p in room.iterdir()) == [
        "CLAUDE.md", "QUESTIONS.md", "RULES.md", "TASK.md", "skills"]
    assert (room / "skills" / "xefm" / "SKILL.md").is_file()
    task = (room / "TASK.md").read_text(encoding="utf-8")
    assert SCENARIOS[0].PROMPT.strip() in task
    assert "Must" not in task          # the scoring key stays out of the room
