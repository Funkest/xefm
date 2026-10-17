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
REPLY = ("Done. Ctrl-T was the command palette; choose the theme in View ▸ Theme. "
         "The desktop app does not wait for the editor, so --wait is not needed there.")


def _fixture(scenario):
    return outcome.fixture_config(getattr(scenario, "FIXTURE", "template"))


def _failures(scenario, after, reply=REPLY):
    o = outcome.Outcome(before=_fixture(scenario), after=after, reply=reply)
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
    failures = _failures(scenario, _fixture(scenario))
    if getattr(scenario, "UNTOUCHED_PASSES", False):
        assert failures == []
    else:
        assert failures, "a run that changed nothing would pass this check"


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.reference],
                         ids=lambda s: s.NAME)
def test_the_reference_edit_passes(scenario):
    assert _failures(scenario, scenario.reference(_fixture(scenario))) == []


def test_losing_a_user_line_fails():
    edited = SCENARIOS[0].reference(_fixture(SCENARIOS[0])).replace("  # keep: my notes", "")
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


def test_the_bare_fixture_has_no_template_text_but_the_same_edits():
    bare = outcome.fixture_config("bare")
    loaded = outcome.inspect_config(bare)
    assert loaded["errors"] == []
    assert loaded["values"]["KEY_BINDINGS"] == {"quit": ["Shift-Q"]}
    assert loaded["values"]["CONFIRM_DELETE"] is False
    assert "reload_config" not in bare and "FILE_ASSOCIATIONS" not in bare
    assert outcome.common_failures(outcome.Outcome(bare, bare), "config") == []


def test_some_scenarios_run_on_the_bare_fixture():
    assert {"template", "bare"} <= {getattr(s, "FIXTURE", "template") for s in SCENARIOS}


def test_dropping_the_default_associations_fails():
    """04's trap: a FILE_ASSOCIATIONS holding only the new rule."""
    scenario = next(s for s in SCENARIOS if s.NAME.startswith("04"))
    bare = _fixture(scenario)
    only_new = bare.replace("    CONFIRM_DELETE = False",
                            "    FILE_ASSOCIATIONS = [{'pattern': '*.log', 'view': ['less']}]\n"
                            "    CONFIRM_DELETE = False", 1)
    assert any(".jpg" in f for f in _failures(scenario, only_new))


@pytest.mark.parametrize("key,safe", [
    ("F2", True), ("Ctrl-UP", True), ("Ctrl-T", True), ("Shift-F", True),
    ("Ctrl-Shift-P", False), ("Cmd-K", False), ("Command-ENTER", False),
    ("Shift-SPACE", False), ("Ctrl-ENTER", False)])
def test_terminal_safe_keys(key, safe):
    assert outcome.terminal_safe(key) is safe


# --- friction: what the room stumbled on, noticed or not ---------------------------

import friction  # noqa: E402


def _transcript(path, calls, texts=(), result="Done.", subtype="success"):
    """A stream-json transcript: ``calls`` are (name, input, result, is_error)."""
    events = [{"type": "system", "subtype": "init", "slash_commands": []}]
    for n, (name, given, answer, error) in enumerate(calls):
        events.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": f"t{n}", "name": name, "input": given}]}})
        events.append({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": f"t{n}", "content": answer,
             "is_error": error}]}})
    for text in texts:
        events.append({"type": "assistant", "message": {"content": [
            {"type": "text", "text": text}]}})
    events.append({"type": "result", "subtype": subtype, "result": result})
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    return path


def test_friction_finds_what_went_wrong(tmp_path):
    config = str(pathlib.Path.home() / ".xefm" / "config.py")
    transcript = _transcript(tmp_path / "t.jsonl", [
        ("Bash", {"command": "rm -rf /"}, "Permission to use Bash has been denied", True),
        ("Bash", {"command": "xefm ext check ."}, "error: contributes.actions: entry missing", False),
        ("Bash", {"command": "python -m pytest"}, "1 failed, 3 passed in 0.2s", False),
        ("Bash", {"command": "xefm ext check ."}, "ok", False),
        ("Grep", {"pattern": "reload_config"}, "No matches found", False),
        ("Write", {"file_path": config}, "File created", False),
        ("Write", {"file_path": config}, "File created", False),
        ("Bash", {"command": "xefm ext install ./logpaths"}, "installed", False),
        ("Bash", {"command": "xefm ext install ./logpaths"}, "installed", False),
    ], texts=["The skill does not say which key is free, so I guessed F12."],
        result="Stopped.", subtype="error_max_turns")
    kinds = [incident.kind for incident in friction.incidents(transcript)]
    assert kinds.count("tool error") == 1
    assert kinds.count("command trouble") == 2
    assert kinds.count("searched, found nothing") == 1
    assert kinds.count("rework") == 2          # config.py written twice, installed twice
    assert kinds.count("said so") == 1
    assert kinds.count("session") == 1


def test_friction_reads_a_refusal_logged_as_a_system_event(tmp_path):
    """A refused call is also logged as a system event whose "message" is a
    string, not a dict - every confined room has one."""
    transcript = _transcript(tmp_path / "t.jsonl", [
        ("Bash", {"command": "cat /etc/hosts"}, "Permission to use Bash has been denied", True)])
    lines = transcript.read_text(encoding="utf-8").splitlines()
    lines.insert(2, json.dumps({"type": "system", "subtype": "permission_denied",
                                "tool_name": "Bash", "tool_use_id": "t0",
                                "message": "Permission to use Bash has been denied"}))
    transcript.write_text("\n".join(lines), encoding="utf-8")
    kinds = [incident.kind for incident in friction.incidents(transcript)]
    assert kinds == ["tool error"]


def test_a_clean_run_has_no_friction_and_says_so(tmp_path):
    room = tmp_path / "room"
    room.mkdir()
    _transcript(room / "transcript.jsonl", [
        ("Edit", {"file_path": "x"}, "updated", False),
        ("Edit", {"file_path": "x"}, "updated", False),          # edits are not rework
        ("Bash", {"command": "xefm ext check ."}, "ok - no problems", False)],
        result="Put Reload Configuration on F12. Reload once to pick it up.")
    assert friction.incidents(room / "transcript.jsonl") == []
    assert "Nothing:" in friction.report(room)


def test_findings_gather_failures_friction_and_questions(tmp_path):
    room = tmp_path / "01_reload_on_f12"
    room.mkdir()
    (room / "QUESTIONS.md").write_text("# What\n\n## Which action name reloads\n",
                                       encoding="utf-8")
    result = {"name": room.name, "title": "Put Reload on F12", "room": room,
              "breaches": [], "refused": [], "failures": ["F12 is also bound to quit"],
              "questions": 1,
              "friction": [friction.Incident("command trouble", 4, "`xefm ext check .`",
                                             "error: entry missing")]}
    text = run_room.write_findings(tmp_path, [result]).read_text(encoding="utf-8")
    assert "## 01_reload_on_f12 - FAIL" in text
    assert "F12 is also bound to quit" in text
    assert "error: entry missing" in text
    assert "Which action name reloads" in text


def test_the_audit_flags_the_checkout_in_a_windows_spelling(tmp_path, monkeypatch):
    # A checkout at a Windows path on every OS: on macOS the real ROOT has no
    # drive letter, and a backslashed /Users/... is not a path anyone would write.
    checkout = pathlib.PureWindowsPath("C:/Users/me/xefm")
    monkeypatch.setattr(run_room, "ROOT", checkout)
    room = tmp_path / "room"
    room.mkdir()
    windows = str(checkout / "xefm" / "_config.py")
    transcript = room / "transcript.jsonl"
    transcript.write_text("\n".join(json.dumps(e) for e in [
        {"type": "system", "subtype": "init", "slash_commands": []},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "a", "name": "Grep",
             "input": {"path": windows, "pattern": "KEY_"}}]}},
        {"type": "result", "result": "done"},
    ]), encoding="utf-8")
    breaches, _refused = run_room.audit(room, transcript, set())
    assert any("reached into the checkout" in b for b in breaches)


def test_an_interrupted_session_still_leaves_its_transcript(tmp_path, monkeypatch):
    """Ctrl-C mid-run: the session is stopped and what it wrote is kept."""
    room = tmp_path / "room"
    room.mkdir()
    script = tmp_path / "fake_claude.py"
    script.write_text("import sys, time\nprint('{\"type\": \"system\"}', flush=True)\n"
                      "time.sleep(30)\n", encoding="utf-8")
    monkeypatch.setattr(run_room, "session_command",
                        lambda *a, **k: [sys.executable, str(script)])
    monkeypatch.setattr(run_room, "_report",
                        lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        run_room.run_session(room, tmp_path, None, 1)
    assert (room / "transcript.jsonl").exists()


def test_a_skill_page_that_says_error_is_not_trouble(tmp_path):
    """A room reads the skill through the shell; the page's own prose is not
    the command going wrong - even when a long output is cut mid-line."""
    room = tmp_path / "room"
    (room / "skills").mkdir(parents=True)
    (room / "skills" / "config.md").write_text(
        "A key bound to two actions is not an\n"
        "  error — one of them silently never fires. A `KEY_BINDINGS` entry\n",
        encoding="utf-8")
    _transcript(room / "transcript.jsonl", [
        ("Bash", {"command": "cat skills/config.md"},
         "A key bound to two actions is not an\n  error — one of them silently", False),
        ("Bash", {"command": "xefm ext check ."}, "error: contributes.actions", False)])
    found = friction.incidents(room / "transcript.jsonl")
    assert [(i.kind, i.step) for i in found] == [("command trouble", 2)]


def test_a_failure_shows_why_and_a_refusal_shows_what(tmp_path):
    transcript = _transcript(tmp_path / "t.jsonl", [
        ("Bash", {"command": "cat a.md; echo =====; cat b.md"},
         "Exit code 1\n# A\nsome text\n(eval):1: ==== not found", True),
        ("Bash", {"command": "rm log-paths/settings.py"},
         "Permission to use Bash has been denied because Claude Code is running in "
         "don't ask mode. IMPORTANT: You *may* attempt…", True)])
    failed, refused = friction.incidents(transcript)
    assert failed.evidence == "(eval):1: ==== not found"
    assert refused.detail == "refused: `rm log-paths/settings.py`"
    assert refused.evidence == ""


def test_writing_up_the_guesses_is_not_doubt(tmp_path):
    transcript = _transcript(tmp_path / "t.jsonl", [
        ("Edit", {"file_path": "QUESTIONS.md"}, "updated", False)],
        texts=["Now recording what I had to guess.",
               "Next I'll write the guesses into QUESTIONS.md.",
               "The config already binds the old name, so I edit that entry instead."])
    assert friction.incidents(transcript) == []


@pytest.mark.parametrize("answer, error, flagged", [
    ("507a5ac Merge pull request #647", False, "breach"),
    ("fatal: not a git repository (or any of the parent directories): .git", True, "refused"),
])
def test_the_audit_flags_git_in_the_room(tmp_path, answer, error, flagged):
    """The room is inside the checkout: `git log` there reads its history."""
    room = tmp_path / "room"
    room.mkdir()
    transcript = room / "transcript.jsonl"
    transcript.write_text("\n".join(json.dumps(e) for e in [
        {"type": "system", "subtype": "init", "slash_commands": []},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "a", "name": "Bash",
             "input": {"command": "cat RULES.md; ls -la; git log --oneline | head"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "a", "content": answer, "is_error": error}]}},
        {"type": "result", "result": "done"},
    ]), encoding="utf-8")
    breaches, refused = run_room.audit(room, transcript, set())
    assert any("ran git" in line for line in (breaches if flagged == "breach" else refused))
