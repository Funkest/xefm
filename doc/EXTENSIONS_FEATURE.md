# Extension Packages — Preview

An extension package is a folder that adds actions, event hooks, themes, sort
orders, filters, picture formats, locations or syntax highlighting to XeFM.
These are the same kinds of things `config.py` can add, with no lines in
`config.py`. A package can be installed, shared, disabled and removed as one
unit.

Extensions run against the same Preview API as `config.py` customization (API
version 0, see [Customization](CUSTOMIZATION_FEATURE.md)), so the format may
still change.

## Installing and managing

From a shell — this works the same for pip/pipx/uv and Homebrew installs, the
macOS app and the Windows app:

```bash
xefm ext install ~/Downloads/hello-xefm.zip   # a .zip
xefm ext install ./hello-xefm                 # a folder
xefm ext install github:someone/hello-xefm    # a GitHub repository (@ref optional)
xefm ext install https://example.com/hello-xefm.zip

xefm ext list                 # what is installed, and whether it will load
xefm ext disable hello-xefm   # keep it, but don't load it
xefm ext enable hello-xefm
xefm ext uninstall hello-xefm # asks whether to delete its data too
xefm ext sync                 # reinstall anything listed but missing
xefm ext settings hello-xefm  # its settings class, ready to paste into config.py
```

Inside XeFM:

- To install, put the cursor on a package folder or `.zip` and choose
  **Tools ▸ Advanced ▸ Install Extension…**.
- **Tools ▸ Advanced ▸ Extensions…** shows which packages loaded, and why any did not.

Before installing, XeFM checks the package and shows everything it adds,
including which code each item runs. Extensions run inside XeFM with your
permissions, and there is no sandbox. Install only packages you trust.

After installing or enabling a package, reload the configuration (**Tools ▸
Reload Configuration**) or restart XeFM.

### Your config.py always wins

If a package and your `config.py` both define the same action, theme, filter,
location or other entry, your entry is used. The package's entry is skipped,
with a note in the log.

Packages only *suggest* keys. A suggested key is used only when you haven't
bound that action yourself and the key isn't already in use. Otherwise bind it
in `KEY_BINDINGS`. Any action is also reachable from the command palette.

### Settings

A package with settings reads them from a class in your `config.py`. Write it
the way `Config` is written: a plain class with no base class and no import.

```python
class CommandPaletteConfig:
    MAX_ITEMS = 30

class Config:
    ...
```

The class name comes from the package id in PascalCase plus `Config`, so
`command-palette` becomes `CommandPaletteConfig`. A package can choose a
different name. `xefm ext list` shows each package's class name.

`xefm ext settings <id>` prints a ready-to-paste class with every setting and
its default. Settings you leave out keep their defaults.

XeFM warns in the log in two cases:

- **A setting the package doesn't have**, such as a typo. The warning lists the
  settings that do exist.
- **A `…Config` class that no installed package claims**, such as a misspelled
  class name.

If you uninstall the package, its class stays in `config.py` unused, and the
config still loads.

### Where things live

| What | Where |
|---|---|
| Packages | `~/.xefm/extensions/<id>/`, beside your own modules |
| What is installed, from where, enabled or not | `~/.xefm/extensions.toml` |
| A package's own files | `~/.xefm/extension-data/<id>/` |
| A package's remembered state | XeFM's state database |

`extensions.toml` is the part worth keeping. Copy it to another machine and run
`xefm ext sync`, and the packages are fetched again. A reinstall never touches
`extension-data/`.

## Writing a package

The quickest start is the scaffold. It creates a package that already passes
the check, with one action, settings and a test:

```bash
xefm ext new hello-xefm
```

### With an AI assistant

XeFM provides a skill for AI agents, `xefm`, that walks through writing,
checking and installing a package (it also covers editing your `config.py`).
It covers the manifest, the API your code may use, settings, dependencies and
testing, and it has the agent run `xefm ext check` until the package is clean.
It works with any agent that reads [Agent Skills](https://agentskills.io).

You can let the agent install the skill itself. Give it the page
[The XeFM Skill for AI Agents](AGENT_SKILL_FEATURE.md)
(https://crftwr.github.io/xefm/doc/AGENT_SKILL_FEATURE.html)
and ask it to install the skill. You can also download
`xefm-X.Y.Z-skill.zip` from the releases page and unzip it into your
agent's skills folder yourself; that page explains both.

Then ask for the feature ("make an XeFM extension that…"). If the agent follows
the skill, the result meets the requirements below. `xefm ext check` verifies
every one of them, so a clean check confirms it.

### The layout

A package is a folder containing a manifest and, if it runs code, a Python
package:

```
hello-xefm/
  xefm-extension.toml
  hello_xefm/
    __init__.py
    actions.py
    settings.py
```

```toml
[extension]
id = "hello-xefm"
version = "0.1.0"
api_version = 0                       # the XeFM API it was written for
# optional:
name = "Hello"
description = "Says hello"
min_xefm = "1.8.0"
backends = ["desktop", "tui"]         # default: both
platforms = ["macos", "windows", "linux"]   # default: all

[contributes.actions]
"hello.greet" = { entry = "hello_xefm.actions:greet", description = "Say hello" }

[contributes.key_suggestions]
"hello.greet" = ["Ctrl-Shift-G"]

[settings]
defaults = "hello_xefm.settings:Settings"
# config_class = "HelloConfig"        # default: derived from the id

[requires]
programs = ["ffmpeg"]                 # missing → its actions say so when run
host_packages = ["PIL"]               # must already be in this XeFM build
python_packages = ["PyYAML>=6"]       # installed from PyPI by the sync
```

```python
# hello_xefm/actions.py
def greet(ctx):
    """Say hello in the log."""
    times = ctx.extension.state.get("times", 0) + 1
    ctx.extension.state.set("times", times)
    ctx.message(f"{ctx.extension.settings.GREETING} (#{times})")
```

```python
# hello_xefm/settings.py
class Settings:
    GREETING = "Hello"
```

Code is only referenced, as `module:name`. XeFM imports it only when the
package loads, never when it is checked.

### What a package can contribute

Each `[contributes.<kind>]` table feeds the `config.py` table of the same name
— see [Customization](CUSTOMIZATION_FEATURE.md) for what each entry does.

| Kind | Feeds | Entry |
|---|---|---|
| `actions` | `ACTIONS` | `"mod:func"`, or `{ entry = "mod:func", description = "..." }` |
| `event_hooks` | `EVENT_HOOKS` | `"mod:func"`, or a list of them |
| `sort_keys` | `SORT_KEYS` | `"mod:name"` |
| `filters` | `FILTERS` | `"mod:name"`, or a table such as `{ globs = ["*.png"] }` |
| `image_decoders` | `IMAGE_DECODERS` | `"mod:name"` |
| `path_schemes` | `PATH_SCHEMES` | `"mod:Class"` |
| `lexers` | `LEXERS` | a Pygments alias, or `{ entry = "mod:LexerClass" }` |
| `themes` | `THEMES` | a table of colors, as in `config.py` |
| `key_suggestions` | `KEY_BINDINGS` | a list of keys, for the package's own actions |

A package with only themes, glob filters, lexer aliases and key suggestions
runs no code at all.

Name actions `<something>.<name>`, such as `hello.greet`. A name without a dot
gets a warning, and a built-in action's name is refused.

### What your code is given

While your action or hook runs, `ctx.extension` holds:

- `id`, `version`
- `settings` — your defaults, overlaid with the user's settings class
- `state` — `get(key, default)`, `set(key, value)`, `delete(key)` and `keys()`;
  values are anything JSON can hold
- `data_dir` — your folder under `~/.xefm/extension-data/`, created on first use

For an action defined in `config.py`, `ctx.extension` is `None`.

### Checking a package

```bash
xefm ext check ./hello-xefm
```

The check validates the manifest without running any of the package's code.
Each problem it reports names the manifest field it concerns:

```
error: xefm-extension.toml: contributes.actions."hello.greet".entry: module hello_xefm.actions has no top-level 'greet'
```

The check also reads the package's Python files, again without running
them:

- **Error:** using a private name such as `ctx._app` (anything starting with
  `_` on an object other than `self`), or importing an XeFM module other than
  `xefm.user_api` and `xefm.path_base`. Such code works today and breaks on
  any release.
- **Warning:** `print()`, which never reaches you (use `ctx.message`), and
  changing `sys.path`.

Files under a `_vendor/` folder are skipped.

The exit status is 0 when the package would install. An install runs the same
check and installs nothing if it finds an error.

### Dependencies

- **Libraries from PyPI** (PyYAML, numpy, rawpy, compiled or not): list them
  in `python_packages` and import them normally. They are installed by the
  same sync as `~/.xefm/requirements.txt`
  ([Extra Python Libraries](PYTHON_PACKAGES_FEATURE.md)), into one shared
  directory, resolved together with every other extension's and your own.
- **Libraries XeFM already ships** (Pillow, for example): list them in
  `host_packages`.
- **Small pure-Python helpers:** you can also vendor them inside your own
  package (`hello_xefm/_vendor/`) and import them through it. A vendored
  library needs no sync and no network. Every loaded package shares one Python
  process, so a top-level module name may belong to only one package. Two
  packages providing `foo` are refused, and so is a name that would hide a
  standard-library module.
- **External programs:** list them in `programs`.

`python_packages` entries are plain requirements: a project name, optional
`[extras]`, version specifiers and a `;` marker. Pip options (`--index-url`),
URLs and paths are refused by the check, so no extension can redirect where
pip downloads from.

What the user sees:

- Installing shows each package under "installs Python package from PyPI".
  `xefm ext install` then asks to sync (with `-y` it just does). Install
  Extension in XeFM syncs right after installing.
- Until a sync has installed exactly the listed packages, the extension is not
  loaded, and the log says it needs Sync Python Packages.
- If two extensions (or an extension and XeFM itself) need versions that can't
  both be installed, the sync fails and the log names the extensions.
- Uninstalling or disabling an extension leaves its packages in place until
  the next sync, and `xefm ext` says a sync is due.

## Things to know

- Actions and hooks run on the UI thread, as they do in `config.py`. Running a
  slow external program from one freezes the window until it finishes.
- A package that fails the check or fails to import is skipped as a whole,
  with the reason in the log. It is never partly loaded.
- This version has no catalog. Packages are installed from a folder, a zip or a
  repository.
