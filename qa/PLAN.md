# XeFM's quality-loop plan

What the conductor (the `quality-loop` skill) reads before planning a run, and
updates after every one. The adapter is `qa/run.py`, named in
`qa/quality-loop.toml`; the map is
[doc/dev/AGENT_SKILL_CLEANROOM_SYSTEM.md](../doc/dev/AGENT_SKILL_CLEANROOM_SYSTEM.md).

## The product, as a room meets it

- **Who:** a user's agent (Claude Code, Claude Desktop) editing an XeFM
  user's `config.py` or writing them an extension, from a plain request.
- **Surface under test:** the agent skill as `xefm skill --zip` ships it,
  and the `xefm ext` / `xefm skill` commands it tells an agent to run. Not
  under test: the file manager's UI, the docs site, the source.
- **What the room may touch:** the run's own `~/.xefm` (a temporary home):
  `config.py` - a fixture, the template with the user's `# keep:` edits or
  the same edits "bare" - and the extensions it installs. The person's own
  `~/.xefm` is never touched.
- **Critical means:** the config no longer loads, the user's own lines lost,
  the file rewritten rather than edited, or the file manager launched.

## Evidence level

**Level 2.** `qa/evidence.py` answers from the room's record: `check` runs
the scenario's mechanical check (XeFM's own `ConfigManager`, key parser and
association matcher), `friction` reads the transcript, `calls` lists the
`xefm` commands, `config` and `keys` say what XeFM would load and run.

**A live check** on 01 and 07: after the room, the operator drives XeFM in
the terminal under the run's home - F12 reloading, the extension's command
logging the paths - and the steps and screens are in `evidence/live/`. The
desktop app (GUI) is not driven yet; quality-loop's `drive.DesktopApp` would,
once its macOS backend has been run for real.

## Priorities

1. Config edits that change only what was asked and keep the user's lines
   (01-04, 06, 08), on both fixtures.
2. Knowing what is not a config edit (05).
3. An extension end to end: scaffold, check, test, install (07).

## Open questions for the person

- Whether to drive the desktop app too (above). XeFM now writes a level-1
  event log when `QUALITY_LOOP_EVENTS` is set (#682): every log-pane line and
  every logged exception, so a live check need not read messages off the
  screen. Dialog and menu events still need a PuiKit layer observer.
- Where the policy lives: a tracking Issue (`quality-loop:loop`) or
  `qa/LOOP.md`.

## Coverage

| Scenario | Surface | Fixture | Last run | Open findings | Notes |
|---|---|---|---|---|---|
| 01 reload on F12 | config, key | bare | 1.8.0-20261019-002554 | `reload-no-distinct-confirmation`, `fn-keys-macos-media-keys` | live check |
| 02 editor in a new window, desktop only | config, external program | template | not yet run | `editor-wait-example-contradicts-desktop` (from the --wait version) | rewritten: the desktop app never waits for the editor, so --wait changed nothing |
| 03 favorite (Japanese) | config, favorites | template | 1.8.0-20261018-204618 | none | |
| 04 .log in less (terminal) | config, associations | bare | 1.8.0-20261018-204618 | `view-file-description-ignores-associations` | |
| 05 Dracula is chosen in XeFM | not a config edit | template | 1.8.0-20261018-204618 | none | |
| 06 Ctrl-T is taken | config, key conflict | template | 1.8.0-20261018-204618 | `moved-action-has-no-other-key`, `template-comment-palette-ctrl-t`, `punctuation-key-spelling-unclear` | |
| 07 extension logs paths | extension | template | 1.8.0-20261019-002554 | `help-extension-actions-labelled-config-py`, `skill-selected-dotdot-unspecified`, `statusbar-truncates-palette-key`, `afx-m-key-three-actions`, `ext-new-scaffolds-unneeded-settings` | live check |
| 08 old action name | config, key | custom | 1.8.0-20261018-204618 | `old-name-keep-or-rename-unstated` | |

Open findings are the run's `skill gap` and `product` ids, not yet filed.
The first run also reported three `harness` findings against qa/: the
evidence tool read `--backend desktop` as the terminal (fixed), and
`friction` does not count a check run twice as rework (open).
