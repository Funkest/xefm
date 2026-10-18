# Agent Skill Clean-Room Testing

The `xefm` agent skill (`xefm/skills/xefm/`, user doc
[AGENT_SKILL_FEATURE.md](../AGENT_SKILL_FEATURE.md)) promises that an agent
holding it — and nothing else — can edit a user's `config.py` and write an
extension correctly. That cannot be checked from a session that has read this
repository, so it is checked in a **clean room**, run by
[quality-loop](https://github.com/crftwr/quality-loop) (a dev dependency in
`requirements-dev.txt`; the design is crftwr/keyhac#205).

```
make qa                            # every scenario, attached
make qa SCENARIO=reload_on_f12     # one
.venv/bin/quality-loop run 01      # in the background; then `quality-loop watch`
.venv/bin/quality-loop findings    # new / still there / gone / back, against the run before
```

Ask Claude Code in this checkout to "run the QA loop" and the conductor
skill (`.claude/skills/quality-loop/`, installed and upgraded only by
`quality-loop init`) plans, runs, reads the findings and files them with you.

## Pieces

| Path | Role |
|---|---|
| `qa/scenarios/NN_name.md` | One real-world request each: the **Prompt** (intent only, the only part that reaches the room), **Must** and **Must not** (what the operator checks). `_always.md` is what every room is held to. |
| `qa/checks/NN_name.py` | The scenario's mechanical check: `KIND`, `FIXTURE`, `check(outcome)`, `reference(text)`. Named like its scenario. |
| `qa/checks/outcome.py` | The fixtures (the template plus `# keep:` user edits, or the same edits "bare"), and the questions checks ask, answered the way XeFM would: `ConfigManager` under a throwaway HOME, keys parsed by `KeyBindings`, presets laid under `KEY_BINDINGS`, associations matched by XeFM's matcher. |
| `qa/checks/friction.py` | Reads a transcript for where the room stumbled, noticed or not. |
| `qa/evidence.py` | The operator's evidence tool: `check`, `friction`, `calls`, `config`, `keys`, each answering JSON from the room's record. |
| `qa/run.py` | The adapter: the bundle, the run's home, the room's `xefm`, what the room may run and reach. |
| `qa/RULES.md` | What the room may read and run; formatted with the run's home. |
| `qa/PLAN.md` | The plan the conductor reads and keeps current: the product as a room meets it, priorities, coverage. |
| `test/test_qa.py` | Every check fails on the untouched fixture and passes on its reference; the evidence tool, the room's `xefm` and the adapter - all without starting a session. |

## A run, per scenario

quality-loop builds the room (the skill exactly as `xefm skill --zip` ships
it, `RULES.md`, `TASK.md` holding the Prompt verbatim, an empty
`QUESTIONS.md`), stands the scenario's fixture in for `config.py`, runs a
`claude -p --restricted` session in it, collects what it made and audits the
transcript. An operator agent then reads the record, checks the Must lines
with `qa/evidence.py`, and writes `REPORT.md`: problems, each with a severity,
a kind, an id and its evidence. No pass/fail. `FINDINGS.md` and
`findings.json` beside the rooms (`cleanroom/<version>-<time>/`) gather them.

## Design decisions

- **The run has a home of its own.** The room's `xefm` runs with HOME at a
  temporary directory, so its `~/.xefm` is the run's: the fixture config,
  the extensions the room installs. Your `~/.xefm` is never set aside, so
  nothing has to be put back after a run that died, and a running XeFM of
  yours is unaffected. The room's own session keeps your HOME, because
  Claude Code's login lives there, and `RULES.md` tells it where the run's
  home is.
- **The finding is a report of problems, with evidence.** The room records
  every point where the skill left it guessing (`QUESTIONS.md`); the operator
  adds what the record shows it stumbling on without noticing (`friction`),
  and whether each Must line was met (`check` and the others). Friction no
  question mentions is the gap nobody noticed.
- **The mechanical checks are evidence, not a verdict.** They were paid for
  by earlier runs and stay as code, so the operator cites what XeFM itself
  answered instead of reading a config by eye.
- **Bash is allowed, narrowly.** The extension scenario needs `xefm ext …`
  and pytest. `--permission-mode dontAsk` plus an allow list refuses
  everything else, and `xefm` on the room's PATH is a shim that runs only
  `ext`, `skill` and `--version` and logs each call. POSIX only: the shim is
  a shell script.
- **The web is forbidden too.** The skill links to published docs and the
  template on GitHub; a link where the answer should be is a gap the room
  reports, not a lookup it makes.
