# Agent Skill Clean-Room Testing

The `xefm` agent skill (`xefm/skills/xefm/`, user doc
[AGENT_SKILL_FEATURE.md](../AGENT_SKILL_FEATURE.md)) promises that an agent
holding it — and nothing else — can edit a user's `config.py` and write an
extension correctly. That cannot be checked from a session that has read this
repository, so it is checked in a **clean room**.

The procedure, its rules and its flags live with the project skill that runs
it: `.claude/skills/xefm-skill-cleanroom/SKILL.md`. This page is the map.

## Pieces

| Path | Role |
|---|---|
| `.claude/skills/xefm-skill-cleanroom/scenarios/NN_name.py` | One real-world request each: `PROMPT` (intent only), `MUST` (read by a person), `check()` (mechanical), `reference()` (a correct edit). Run in file order. |
| `…/scripts/run_room.py` | Builds a room per scenario, swaps `~/.xefm/config.py` for the fixture, drives `claude -p --restricted`, audits the transcript, checks, restores. `make cleanroom`. |
| `…/scripts/outcome.py` | The fixture (the template plus `# keep:` user edits), and the questions checks ask, answered the way XeFM would: `ConfigManager` under a throwaway HOME, keys parsed by `KeyBindings`, presets laid under `KEY_BINDINGS`, associations matched by XeFM's matcher. |
| `…/room/RULES.md` | What the room may read and run; copied into each room. |
| `test/test_skill_cleanroom.py` | Every check fails on the untouched fixture and passes on its reference, without starting a session. |

## Design decisions

- **The finding is `QUESTIONS.md`.** The room records every point where the
  skill left it guessing; the mechanical checks only say whether the edit
  landed. Modelled on Keyhac's `keyhac-skill-cleanroom`.
- **The real config is swapped, not the HOME.** A session with a different
  HOME cannot use the operator's Claude login (it lives in the keychain), so
  the room runs under the real HOME and `~/.xefm/config.py` is moved to
  `config.py.cleanroom-backup` for the length of each run. A backup present
  at start-up means a run died; the runner refuses until `--restore`.
- **Bash is allowed, narrowly.** The extension scenario needs `xefm ext …`
  and pytest. `--permission-mode dontAsk` plus an allow list refuses
  everything else, and `xefm` on the room's PATH is a shim that runs only
  `ext`, `skill` and `--version` and logs each call.
- **The web is forbidden too.** The skill links to published docs and the
  template on GitHub; a link where the answer should be is a gap the room
  reports, not a lookup it makes.
