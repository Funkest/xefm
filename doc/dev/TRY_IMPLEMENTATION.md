# `xefm try` — Implementation

User doc: [TRY_FEATURE.md](../TRY_FEATURE.md). Issue #682.

## Why one command

Running the TUI in a pseudo-terminal under a throwaway home was first done by
hand while Compute Hash was built, and it caught #679, which both
`xefm ext check` and the unit tests (a fake `ctx`) had missed. The same method
serves three jobs: an extension's author (often an agent) seeing menus,
prompts, task progress and cancel; an automated test of XeFM itself; and a
demo recorded for a README. So it is a top-level `xefm try`, beside `xefm ext`,
`xefm skill` and `xefm deps`. Extensions are one option (`--ext`), not the
point.

## Modules

- `xefm/try_cli.py` — argument parsing and the exit status. `xefm.app.main`
  dispatches `argv[1] == "try"` here before the UI's argparse runs, so this
  process never opens a backend.
- `xefm/trial.py` — the home, the script, the pty, the recording.
- `xefm/event_log.py` — the event log the scripted run reads.

## How it works

- **`TryHome`** makes a temporary `~` (`HOME` and `USERPROFILE`) with a
  fixture folder for the left pane. It copies `--config` in if given, so a
  test can check a config edit. Otherwise XeFM writes its template on first
  start, as for a new user. Each `--ext` source is installed with
  `extensions.install` (the same check and copy as `xefm ext install`), and a
  `python_packages` requirement is synced into the home. It writes
  `keymap.preset` and `tips.enabled = False` into the home's `state.db`. Those
  are the two dialogs a fresh home opens, and each used to take a script's
  first keys: an Esc meant for something else picked a preset. A home that
  fails half-way is removed before the error is raised.
- **The child XeFM** gets this XeFM's package directory first on
  `PYTHONPATH`, so the XeFM that runs is the one that installed the packages.
  It is started by `external_programs.xefm_python`, not `sys.executable`: in an
  app bundle `sys.executable` is the launcher, which would open the desktop
  app.
- **Interactive** (no `--keys`) hands the terminal to that XeFM and waits.
- **Scripted** (`--keys`) is a small `PtyApp`: a fixed-size pty, with `pyte`
  kept in step with every byte. Keys use quality-loop's notation
  (`quality_loop.drive.keys`), so a script reads like an operator's live
  check. `PtyApp` is a copy of quality-loop's rather than a use of it, because
  the recording needs the raw bytes, and quality-loop's reader keeps them to
  itself. Between steps it waits for quiet, counted from the last key as well
  as the last output. Each step's screen goes to `NN.txt`. `steps.jsonl` gets
  the keys, whether the screen settled, the highlights, and the event-log
  lines written during the step.
- **Highlights** stand in for colour, which `screen.display` drops. The
  selection and the menu row under the cursor exist only as a background
  colour, so `highlights()` lists the runs whose background is tinted (channel
  spread ≥ 0.15) or reversed. Panels, shadows and separators are greys and
  drop out. The file list's cursor row needs nothing, because PuiKit draws it
  between `[` and `]`. The status bars come along too: they are tinted, and
  telling them apart would mean knowing the theme. A heuristic on the
  rendered cells was chosen over dialog/menu events from a PuiKit observer
  (#682 proposal 3) because the screen already says what an agent needs once
  colour is kept, and it costs XeFM and PuiKit nothing. Events can follow if
  scripted regression tests outgrow reading screens. The run ends when the script does, so an agent's shell is
  never held. The script is read and validated before the home is made, so a
  typo costs no install.
- **`Recording`** writes asciicast v2:
  - the header carries the one size the app draws at for the whole session,
    so it cannot disagree with the rows. A recorder that wrote it mid-resize
    put every row one off in `agg`.
  - `"o"` events go through an incremental UTF-8 decoder, because a read can
    split a character.
  - each step adds an `"m"` marker, which players show as chapters.

  Replaying a recording through pyte reproduces the last step's screen
  exactly.

The script mode depends on `quality-loop[tui]` (MIT; pyte, LGPL, comes with
it), imported only when `--keys` is given. It is not a requirement, because
the desktop bundles would have to carry and attribute pyte for a developer
feature. It is POSIX only: Windows has ConPTY, which neither this nor
quality-loop drives yet.

## The event log

With `QUALITY_LOOP_EVENTS=<file>` in the environment (`xefm try --keys` sets
it, and so does quality-loop for every app it starts), XeFM appends one JSON
line for:

- each log-pane line (`"kind": "message"`), written where the line is
  appended: `log_info` on the UI thread, and `_drain_captured_output` for
  everything queued;
- each logged exception (`"kind": "exception"`), written by
  `_LogSinkHandler` with the traceback.

A message read off the screen can scroll away before the next look. The
event log keeps it.

## Not done (#682)

- **Dialog, menu and selection events.** XeFM opens its dialogs and menus
  through PuiKit's `Panel.push_layer` from about twenty places, and nothing
  public reports a layer coming or going. The clean place for that is a PuiKit
  observer, not wrappers in XeFM (the capability-branch rule). Selection
  already shows as `Selected: …` messages.
- **Demo polish from #682's comments**: starting a recording after the
  startup lines (the log prints the home's path), and a GIF straight from
  the run. `agg` turns the cast into one today.
- **Driving the desktop app.** Left for later, as the issue proposed.

## Tests

`test/test_trial.py` covers `xefm try` short of starting XeFM:

- the home: the packages given and nothing of the user's, none at all,
  several, no first-run dialog, removal on a failed start;
- the script reader, and that a bad script installs nothing;
- the asciicast;
- the event log;
- the dispatch before the UI starts.

`test/test_extension_skill.py` checks that every `xefm try` option the skill
uses exists, and that the skill's example script reads. A real run (scaffold →
palette → action) was checked by hand. It takes a few seconds, which is too
slow for the suite.
