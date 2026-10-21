# Python Packages from requirements.txt — Implementation (#664)

User doc: [PYTHON_PACKAGES_FEATURE.md](../PYTHON_PACKAGES_FEATURE.md).

## Files

| File | Role |
|---|---|
| `xefm/python_packages.py` | Layout, stamp, startup check, activation, pip discovery, sync |
| `xefm/deps_cli.py` | `xefm deps sync / status`, dispatched from `app.main` before argparse |
| `xefm/config.py` | `ConfigManager.prepare_python_packages()`, called from `load_config` before `config.py` runs |
| `xefm/app.py` | `sync_python_packages` action (worker thread + `_pump_python_packages`), startup notice |

## Layout

```
~/.xefm/requirements.txt
~/.xefm/site-packages/
    3.14/            target, on sys.path (appended via site.addsitedir)
        .stamp       JSON: requirements sha256, host sha256, python, platform
    .3.14.new/       staging: built by a sync, swapped in whole
    .3.14.old/       the previous target during a swap
    .pip/            pip wheel downloaded from PyPI (Windows app only)
```

The directory is per minor version because compiled packages are. It is kept
apart from `extensions/` on purpose: `prepare_user_extensions` evicts every
module under `extensions/` on reload, which is wrong for numpy or a C extension.

## Stamp and startup check

`check()` is offline and compares the stamp only:

- `platform` (`cache_tag-sys.platform-machine-abiflags`) differs → `FOREIGN`,
  not loaded. `~/.xefm` travels with dotfiles.
- `requirements` (sha256 of the file's text) differs → `NEEDS_SYNC`, loaded.
- `host` (sha256 of the host's `name==version` set) differs → `NEEDS_SYNC`,
  loaded. This catches an XeFM upgrade that moved a pinned package, and two
  installs (app and formula) sharing `~/.xefm`: the prune depends on the host,
  so a directory synced for one host can be missing what the other lacks.
- No stamp but declared requirements → `NEEDS_SYNC`, naming other `X.Y`
  directories if there are any (a Python upgrade).

The check never syncs. A sync reaches the network.

## Sync

1. **Host set.** `importlib.metadata.distributions()` in the running process,
   excluding anything under `site-packages/` itself, first one per normalized
   name. That is exactly what imports resolve to.
2. **pip.** `pip install --target <staging> -r requirements.txt -c <host
   constraints>`, cwd `~/.xefm`, with `PIP_TARGET` / `PIP_PREFIX` / `PIP_USER` /
   `PIP_REQUIRE_VIRTUALENV` removed from the environment. `--target` resolves
   as if nothing were installed, so the constraints are what pin a dependency
   to the host's version. A clash fails resolution; `_conflict_lines` lifts the
   "The conflict is caused by:" block into the error when a `(constraint)` line
   is in it.
3. **Prune.** Every distribution in staging whose name the host has is removed
   by its RECORD, only for paths inside staging (`--target` RECORDs can name
   `../../bin/...`), followed by empty parents and the dist-info.
4. **Stamp**, then **swap**: target → `.old`, staging → target. If the first
   rename fails (Windows: a loaded `.pyd` pins the directory), nothing has
   changed and staging waits. `activate()` at the next start swaps it in
   before the directory is put on `sys.path`. A staging directory without a
   stamp is an interrupted sync and is discarded.

Nothing declared and no target: the sync does nothing. Nothing declared with a
target: an empty staging is swapped in like any other, then target and (if
empty) `site-packages/` are removed, so the check reads `UNUSED` again.

## Which pip

`xefm_python` (from `external_programs`): the real interpreter even in the
bundles. In order:

1. `python -m pip`: pipx venvs, plain pip installs, the Homebrew formula
   (its venv is `--without-pip` but `--system-site-packages` sees python@3.14's
   pip).
2. ensurepip's bundled wheel, run as `python <wheel>/pip`, which pip supports.
   Covers the macOS app (python.org framework keeps `ensurepip`) and uv venvs.
3. A pip wheel from PyPI's JSON API, sha256-checked against the digest PyPI
   lists, cached in `site-packages/.pip/`. The Windows app's embeddable CPython
   has neither pip nor ensurepip.

## In-app action

`sync_python_packages` runs `sync()` on a daemon thread. pip's lines go to
`_log_queue` as `STDOUT` (dimmed), and the outcome is left in
`_python_packages_done` for `_pump_python_packages` on the UI thread, which
logs it and calls `reload_config()` so a `config.py` import that failed for a
missing package gets another try. The menu item is disabled while a sync runs.

## Open checks

- Windows app and Store package: route 3 (PyPI download) and loading an
  unsigned `.pyd` from `~/.xefm` have not been run there.
- macOS app: XeFM.app carries `disable-library-validation`, so an unsigned
  `.so` from pip should load; not yet confirmed in a signed build.
- Extensions: a `requires.python_packages` in `xefm-extension.toml` could feed
  the same sync later. `requires.host_packages` is unchanged.
