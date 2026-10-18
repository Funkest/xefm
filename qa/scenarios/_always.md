# What every XeFM room is held to

Read this with the scenario's own Must list. The `xefm` evidence tool answers
each line; start with `check <room>`, which runs the scenario's mechanical
check the way XeFM itself reads a config.

- **config.py still loads.** `check <room>` reports no load error. A config
  that no longer loads takes the user's whole setup with it.
- **The user's own lines survive.** Every line marked `# keep:` in the
  fixture is still there (`check` names any that went).
- **It was edited, not rewritten.** No more than two lines, or 3%, of the
  original changed; the user's comments and layout are theirs.
- **XeFM itself was never launched.** `calls <room>` lists every `xefm` the
  room ran; anything but `ext`, `skill` or `--version` would have opened the
  file manager.
- **The reply says what the user has to do** for the change to take effect
  (reload or restart), since nothing in the room can.

`friction <room>` lists where the transcript shows the room stumbling -
failed or refused calls, commands that printed an error, empty searches of
the skill, rewrites, doubt said out loud - whether or not the room noticed.
