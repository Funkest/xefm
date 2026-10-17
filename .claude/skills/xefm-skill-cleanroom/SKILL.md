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
`config.py.cleanroom-backup`) and a fixture stands in: the template plus
the edits a real user makes, each marked `# keep:`. It is put back on any
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
  matched as XeFM matches them), and every `# keep:` line and 97% of the
  file survived.
- **must** — the scenario's `MUST` list, for you to read against the reply
  and the transcript. A miss is a skill defect, not a model defect: fix the
  skill, and re-run every scenario if the change was to a rule.
- **questions** — read `QUESTIONS.md`. That is the result.

## Scenarios

One file each in `scenarios/`, run in file order. A scenario module has
`TITLE`, `KIND` (`"config"` or `"extension"`), `PROMPT` (intent only, the way
a user would ask — never an action or attribute name the skill should
supply), `MUST`, `check(outcome) -> list[str]` and `reference(text)`, the
edit a correct run would make (`None` when there is no single one).
`test/test_skill_cleanroom.py` runs every check against the untouched
fixture (it must fail, unless `UNTOUCHED_PASSES`) and against `reference`
(it must pass), so a check that cannot fail is caught without a run.
