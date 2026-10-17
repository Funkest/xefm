---
name: xefm-skill-cleanroom
description: Clean-room test the shipped XeFM agent skill (xefm/skills/xefm) - run every predefined real-world scenario (config edits and an extension) in a room that holds the skill and nothing else, with the user's ~/.xefm/config.py swapped for a fixture, then audit, check and collect what the skill failed to answer. Use when the user says "clean-room test the skill", "run the skill scenarios", or asks whether the XeFM skill is self-contained.
---

# Clean-room testing the XeFM skill

**The failures are the product.** This measures whether the *skill* can
teach an agent to edit XeFM's config and write an extension, not whether a
model can. Every point where the room had to guess is a line the skill
should have carried; `QUESTIONS.md` in each room is that list. A run with
zero questions measured nothing, or broke a rule.

## Run

```
make cleanroom                          # every scenario, in order
make cleanroom SCENARIO=reload_on_f12   # one
make cleanroom ARGS=--list              # what there is
```

Each scenario gets a room under `cleanroom/<version>-<time>/<scenario>/`
(gitignored): the skill unpacked from the same zip `xefm skill --zip`
writes, `RULES.md` (from `room/`), `TASK.md` (the scenario's `PROMPT` and
nothing else) and an empty `QUESTIONS.md`. A `claude -p` session runs in it
with `--restricted`, told only "Read RULES.md, then do TASK.md."

**Your `~/.xefm/config.py` is moved aside for each run** (to
`config.py.cleanroom-backup`) and a fixture stands in. A scenario picks it
with `FIXTURE`: `"template"` (the default) is the template plus the edits a
real user makes, each marked `# keep:`; `"bare"` is the same edits with no
template text at all — a user who deleted the comments, so the skill cannot
lean on them; or the scenario's own text. It is put back on any
exit; a backup found at start-up means a run died, and the script refuses
until `ARGS=--restore` puts it back. Do not reload the config in a running
XeFM while a run is going. Extensions a room installs are copied into the
room and removed from `~/.xefm/extensions/`.

## What isolates the room

- **`--restricted`** skips CLAUDE.md discovery (the room is inside the
  checkout), ignores the settings files, hides this checkout's skills, and
  confines the file tools to the room plus `--add-dir ~/.xefm`. The room's
  own `CLAUDE.md` is a canary only a session started without the flag reads.
- **Bash, narrowed.** The extension scenario needs `xefm ext …` and pytest,
  so Bash is named in `--tools`, and `--permission-mode dontAsk` with an
  explicit allow list refuses every other command. A refusal is printed: it
  is either the confinement holding or the skill naming a command it should
  not.
- **`xefm` is a shim** outside the checkout that runs only `ext`, `skill`
  and `--version`, and logs every call — which is how "never launch XeFM"
  is checked.
- **The audit** reads the transcript for tool calls aimed at the checkout,
  the installed package, the PuiKit checkout, the backed-up real config, or
  another author's extension. A call that was refused is reported, not held
  against the run; one that came back with something disqualifies it.

## Score

Printed per scenario:

- **checks** — mechanical, from the scenario's `check()`: the config loads
  in XeFM's own `ConfigManager`, the requested change is in force (keys as
  XeFM parses them, the preset laid under `KEY_BINDINGS`, associations
  matched as XeFM matches them), every `# keep:` line survived, and no more
  than two lines (or 3%) of the original were changed.
- **must** — the scenario's `MUST` list, for you to read against the reply
  and the transcript. A miss is a skill defect, not a model defect: fix the
  skill, and re-run every scenario if the change was to a rule.
- **friction** — `FRICTION.md`, from `scripts/friction.py`: where the
  transcript shows the room stumbling, *whether or not it noticed* — a tool
  call that failed or was refused, a command that printed an error (`xefm ext
  check` complaining before it passed, a failing test), a search of the skill
  that came back empty, config.py written wholesale or an extension installed
  more than once, a session that ran out of turns, and the sentences where
  the room said it was unsure or had it wrong. Read off the record, not the
  room's account of it.
- **questions** — `QUESTIONS.md`: what the room noticed it had to guess.

`FINDINGS.md`, beside the rooms, gathers every scenario's check failures,
friction and questions in one place; that is the result. **Friction that no
question mentions is the most valuable kind** — the gap the room worked
around without seeing it — and zero questions is still not a pass.

**Not every item is a skill gap.** Sort each one: a *skill gap* (the skill
should have said it — fix the skill), *out of scope* (true of the task or
the user's setup, not of XeFM), or *tooling* (the room's own tools or this
runner). Only the first changes the skill.

## Scenarios

One file each in `scenarios/`, run in file order. A scenario module has
`TITLE`, `KIND` (`"config"` or `"extension"`), optionally `FIXTURE`,
`PROMPT` (intent only, the way
a user would ask — never an action or attribute name the skill should
supply), `MUST`, `check(outcome) -> list[str]` and `reference(text)`, the
edit a correct run would make (`None` when there is no single one).
`test/test_skill_cleanroom.py` runs every check against the untouched
fixture (it must fail, unless `UNTOUCHED_PASSES`) and against `reference`
(it must pass), so a check that cannot fail is caught without a run.
