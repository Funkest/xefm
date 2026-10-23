# Extra Python Libraries: `~/.xefm/requirements.txt`

English \| [日本語](PYTHON_PACKAGES_FEATURE.ja.md)

Some things you can do in `config.py` need a Python library XeFM doesn't ship:
a Pillow plugin such as `pillow-heif`, `rawpy` for camera RAW in an
`IMAGE_DECODERS` entry, or anything your own actions import. List them in
`~/.xefm/requirements.txt`, next to `config.py`, and sync:

```
# ~/.xefm/requirements.txt
pillow-heif
rawpy
```

```bash
xefm deps sync
```

Or, inside XeFM: **Tools → Advanced → Sync Python Packages** (also in the command palette
as `sync_python_packages`). The sync runs in the background, pip's output goes
to the log pane, and the configuration reloads when it finishes.

This works the same for every install: the macOS app (DMG or Homebrew cask),
the Windows app (zip or Microsoft Store), the Homebrew formula, and
pipx / uv / pip. The libraries live in `~/.xefm/site-packages/`, not in XeFM's
own install, so upgrading XeFM keeps them.

## How it behaves

- **The file is what counts.** Delete a line and sync, and that library is
  removed. An empty file (or none) removes them all.
- **XeFM's own libraries win.** If a library you list needs a different version
  of something XeFM already uses (Pillow, Pygments, …), the sync fails and the
  log names both sides of the conflict. Nothing changes until a sync succeeds.
- **Nothing is downloaded behind your back.** At startup XeFM only checks,
  offline, whether the file changed since the last sync, or whether XeFM itself
  was upgraded. If so, the log says a sync is due. Syncing is always something
  you start.
- **A new Python version needs one sync.** Libraries are kept per Python
  version (`site-packages/3.14/`). When a new XeFM runs on a newer Python, the
  log says so, and a sync installs the same list again.
- **Already-loaded libraries update on restart.** A library that was already
  imported keeps its old version until XeFM restarts. On Windows, if a library
  in use can't be replaced, the new set takes over at the next start.

## Extensions that need libraries

An extension package can list the libraries it needs in its manifest
(`requires.python_packages`). The same sync installs them alongside your
`requirements.txt`, all resolved together. Installing such an extension offers
to sync right away. Until a sync has run, the extension isn't loaded and the
log says why. Removing or disabling the extension leaves its libraries in place
until the next sync.

## Commands

| Command | What it does |
|---|---|
| `xefm deps sync` | Make `~/.xefm/site-packages` match `requirements.txt`. Needs the network. |
| `xefm deps status` | Say whether a sync is needed. Offline. Exits 1 when it is. |

`requirements.txt` is a normal pip requirements file: version specifiers,
`--index-url`, and paths relative to `~/.xefm` all work. If the file pulls in
another one with `-r`, editing that other file isn't noticed by the startup
check, so run the sync yourself.

Don't edit `~/.xefm/site-packages/` by hand; each sync replaces it. If you keep
`~/.xefm` in a dotfiles repository, commit `requirements.txt` and leave
`site-packages/` out: each machine syncs its own.
