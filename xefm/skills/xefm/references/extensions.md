# Writing an XeFM extension

Read `SKILL.md` first: the ground rules there (never launch XeFM, where its
files are) apply here too.

An XeFM extension is a folder with a manifest (`xefm-extension.toml`) and,
when it runs code, a Python package. XeFM reads the manifest, checks it
**without running any of the code**, and only then wires the code into its
tables.

The loop is always the same:

1. `xefm ext new <id>` to start, or edit an existing package.
2. Write the manifest and the code, following sections 2–5.
3. `xefm ext check <dir>` — fix every line it prints and re-run until it says
   `ok:` **with no warnings** other than the machine-dependent ones (a program
   "not on PATH", a host package "not importable" here). The check covers the
   manifest *and* the code rules in section 3, so a clean check means the
   package meets XeFM's requirements.
4. `python -m pytest tests` in the package directory (see *Testing*).
5. `xefm ext install <dir>` (add `--yes` only when the user has said to install).
6. Tell the user to run **Tools ▸ Reload Configuration** in XeFM, or restart
   it.

Never launch XeFM yourself to try an extension: `xefm` (and `python -m xefm`)
opens an interactive file manager that blocks until a person quits it. The
`xefm ext …` subcommands are safe; they never open a window.

## 1. Start a package

```bash
xefm ext new hello-xefm            # creates ./hello-xefm/, which passes the check
xefm ext new hello-xefm --dir ~/src
```

It creates:

```
hello-xefm/
  xefm-extension.toml     # one action, settings defaults
  pytest.ini              # puts the package on the path for the tests
  hello_xefm/
    __init__.py
    actions.py            # thin actions: read ctx, call logic, report
    logic.py              # plain functions, no XeFM — what tests exercise
    settings.py           # defaults for the user's settings class
  tests/
    test_hello_xefm.py
```

Keep that shape: new work goes into `logic.py` (or more plain modules), and
`actions.py` stays a thin layer over it.

The id is lowercase letters, digits, `.`, `_` and `-`. The Python package
inside is the id with `-` and `.` turned into `_` (`hello_xefm`). It must not
share a name with the standard library, `xefm`, `puikit`, or any other
installed extension's top-level module.

To *promote* an action that already lives in the user's `config.py`, move the
function into the package's module, list it in the manifest, and remove it
from `ACTIONS` in `config.py`. While both define it, `config.py` wins.

## 2. The manifest

```toml
[extension]
id = "hello-xefm"                   # required
version = "0.1.0"                   # required
api_version = 0                     # required: the XeFM API written against (0 = Preview)
name = "Hello"                      # optional, shown to the user
description = "Says hello"          # optional
min_xefm = "1.7.0"                  # optional: the oldest XeFM it runs on
backends = ["desktop", "tui"]       # optional, default both
platforms = ["macos", "windows", "linux"]   # optional, default all
homepage = "https://github.com/me/hello-xefm"   # optional

[contributes.actions]
"hello.greet" = { entry = "hello_xefm.actions:greet", description = "Say hello" }
"hello.count" = "hello_xefm.actions:count"     # short form; docstring is the description

[contributes.key_suggestions]
"hello.greet" = ["Ctrl-Shift-G"]    # only for this package's own actions

[contributes.event_hooks]
directory_changed = "hello_xefm.hooks:on_cd"   # or a list of references

[contributes.themes."Hello Dark"]   # data, no code
base = "dark"

[contributes.filters.pictures]      # data form…
globs = ["*.png", "*.jpg"]
[contributes.sort_keys]
by_length = "hello_xefm.sorting:BY_LENGTH"     # …or a reference to the value

[settings]
defaults = "hello_xefm.settings:Settings"
# config_class = "HelloConfig"      # optional; default is derived from the id

[requires]
programs = ["ffmpeg"]               # external programs; missing → action says so
host_packages = ["PIL"]             # importable packages XeFM itself ships
```

Rules the check enforces — each violation is an `error:` naming the field:

- Only the sections `extension`, `contributes`, `requires`, `settings`, and only
  the keys shown above. A typo is an error, not ignored.
- A reference is `package.module:name`, and `name` must be bound at the top
  level of that module's file inside the package (a `def`, `class`,
  assignment or import). The check reads the file; it does not import it.
- Contribution kinds: `actions`, `event_hooks`, `sort_keys`, `filters`,
  `image_decoders`, `path_schemes`, `lexers`, `themes`, `key_suggestions`.
- Action names must not be a built-in action's name. Prefix them with a
  short name for your extension — any lowercase word, usually the id or its
  first part (`hello.greet` for `hello-xefm`); an unprefixed name is a
  warning.
- `[settings]` is optional: leave it (and `settings.py`) out when the package
  has nothing for the user to set.
- Events: `startup`, `quit`, `directory_changed`, `file_open`.
- Keys use `KEY_BINDINGS` spelling: `"G"`, `"Shift-G"`, `"Ctrl-Shift-F12"`,
  `"Alt-Enter"`, `"Cmd-K"`. A key that is already bound is not an error, but
  the suggestion is then not applied — the user binds it themselves.
- `api_version` higher than the running XeFM's is refused.

What each table entry *does* is the same as the `config.py` table it feeds —
`ACTIONS`, `EVENT_HOOKS`, `SORT_KEYS`, `FILTERS`, `IMAGE_DECODERS`,
`PATH_SCHEMES`, `LEXERS`, `THEMES`. Each is documented, with the shape of
its values, in the comment above it in `references/config-template.md`; for a
`sort_keys`, `filters`, `image_decoders` or `path_schemes` entry the
referenced object is exactly the value that table would hold.

## 3. The code: the public API only

An action is `def name(ctx): ...`; a hook is `def name(ctx, *event_args)`.
The function's docstring is its help text (first line = one-line summary).

`ctx` is an `xefm.user_api.ActionContext`. Use **only** the names below.
`xefm ext check` enforces this on your code:

- **error** — any `._name` attribute on something other than `self`/`cls`
  (`ctx._app`, `pane._pane`): private, changes without notice.
- **error** — importing any `xefm` module except `xefm.user_api` and
  `xefm.path_base` (the base classes for a `path_schemes` backend).
- **warning** — `print()`: it never reaches the user.
- **warning** — touching `sys.path` (see *Dependencies*).

Vendored code under `_vendor/` is not checked.

The public names:

- `ctx.pane`, `ctx.other`, `ctx.left`, `ctx.right` — a `PaneApi`
- `ctx.invoke(action_name)` — run any action, built-in or not
- `ctx.run_program(command, *, terminal=False, cwd=None, env=None)` — run an
  external program; `terminal=True` hands it the terminal (TUI) or opens a
  terminal window (desktop)
- `ctx.message(text)` — one line in the log pane (XeFM's "log"); call it
  once per line rather than passing a string with newlines
- `ctx.input(prompt, default="", *, title="", on_accept=None, on_cancel=None)`
- `ctx.choose(title, items, *, type="choice", on_result=None)` — `type` is
  `"choice"` or `"filter"`; `on_result` gets the index or `None`
- `ctx.confirm(prompt, *, title="Confirm", on_result=None)` — `on_result` gets
  `True`/`False`
- `ctx.api_version`, `ctx.action_names()`
- `ctx.extension` — this package's handle (below)

`PaneApi` (`ctx.pane`):

- `name` (`"left"`/`"right"`), `is_active`, `activate()`
- `path`, `cd(path, focus_name=None)`, `refresh()`
- `open_list(paths, *, title)` — show a list of paths as a virtual folder
- `entries` — every listed `EntryInfo`, in the pane's order (a property)
- `focused` — the `EntryInfo` under the cursor (a property). `None` in an
  empty directory, and it can be the `..` entry: skip an entry named `..`
  when acting on files.
- `selected()` — **a method**: the selected entries, in listing order,
  `[]` when nothing is selected. It never falls back to `focused`; do that
  yourself: `selected() or [focused]`.
- `cursor` (read/write index)
- `select(predicate=None)`, `unselect(predicate=None)` — return the count

`EntryInfo`: `name` (as displayed — use it for matching), `path` (the real,
absolute path, a `pathlib.Path`-like object; `str(entry.path)` gives the text,
which for a remote or in-archive entry is a URI such as `ssh://host/dir/f`;
use `path` for any file operation), `is_dir`, `is_link`, `is_file`,
`stem`, `suffix`, `size`, `mtime`. `size`/`mtime` cost a `stat` on first
access; a predicate that only reads names stays fast.

`ctx.extension` (`None` for actions defined in `config.py`):

- `id`, `version`
- `settings` — your `settings.defaults` class's values, overlaid with the
  user's class (below)
- `state` — `get(key, default=None)`, `set(key, value)`, `delete(key)`,
  `keys()`; JSON-serialisable values, kept across restarts
- `data_dir` — a `pathlib.Path` for your own files, created on first use

### Things that are true of every action

- **It runs on the UI thread and XeFM waits.** Keep it short. Anything slow
  (a big walk, a network call, an external tool) belongs in
  `ctx.run_program(...)` or must be avoided — there is no background-work
  helper in API version 0.
- **Prompts do not block.** `ctx.input`, `ctx.choose`, `ctx.confirm` return
  at once; put the rest of the action in the callback.
- **Exceptions are caught at the boundary** and logged with a traceback; the
  action simply stops. Do not wrap everything in `try/except` to hide errors.
- **No `print()`.** Use `ctx.message(...)` for the user; for diagnostics,
  `import logging; logging.getLogger(__name__)` is routed into XeFM's log.
- **A storage backend** (`path_schemes`) subclasses
  `xefm.path_base.ReadOnlyPathImpl`, never `xefm.path.PathImpl`.
- The same code runs in the terminal and the desktop window, on macOS,
  Windows and Linux. Use `pathlib`/`entry.path`, never string-joined paths,
  and do not assume a shell.

## 4. Settings

Settings the user writes by hand go in a **plain class in their
`config.py`** — no base class, no import:

```python
class HelloXefmConfig:        # derived from the id "hello-xefm"
    GREETING = "Hi"
```

Your package declares the defaults:

```python
# hello_xefm/settings.py
class Settings:
    GREETING = "Hello"
```

with `[settings] defaults = "hello_xefm.settings:Settings"`. Settings are the
upper-case attributes. Read them as `ctx.extension.settings.GREETING`. The
class name is the id in PascalCase plus `Config`; `xefm ext list` and
`xefm ext check` print it, and `xefm ext settings <id>` prints a
ready-to-paste class with every default. Tell the user that name; do not
make them guess it.

## 5. Dependencies

- Pure-Python libraries: vendor them inside your package
  (`hello_xefm/_vendor/foo/`) and import them as `hello_xefm._vendor.foo`,
  rewriting the library's own absolute imports if it has any. Never add
  `_vendor` to `sys.path`: every extension shares one process, and two
  extensions vendoring different versions would collide.
- Libraries XeFM itself ships (Pillow, Pygments): list them in
  `requires.host_packages` and import them normally.
- External programs: list them in `requires.programs`; the action is refused,
  with a message naming the program, until it is on PATH.
- Compiled libraries XeFM does not ship (numpy, scipy…): not supported. Say so
  rather than working around it.

### After installing: how the user runs it

Every action is in XeFM's **command palette** (the `command_palette`
action — see `references/actions.md` for its key), key or no key, described by
its docstring. To put it on a key, the user adds it to `KEY_BINDINGS` in
`config.py` (`'hello.greet': ['Ctrl-Shift-G']`), or the package suggests one
in `[contributes.key_suggestions]`. Tell the user both; edit their
`config.py` only if they ask.

## 6. Testing

`xefm ext check` is static. For behaviour, unit-test what does not need XeFM:
keep the logic in plain functions that take paths and values, and keep the
action a thin wrapper over them.

```python
# tests/test_logic.py — run with: python -m pytest tests
from hello_xefm.logic import new_name

def test_new_name():
    assert new_name("a.txt", 3) == "a-3.txt"
```

If `python -m pytest` reports that pytest is not installed, say so to the
user (`python -m pip install pytest` installs it) rather than skipping the
tests silently.

For the thin wrapper, a small fake is enough — make it match the real API's
shape, methods as methods (`selected=lambda: [...]`):

```python
from types import SimpleNamespace
from hello_xefm import actions

def test_greet_logs():
    lines = []
    ext = SimpleNamespace(settings=SimpleNamespace(GREETING="Hi"),
                          state=SimpleNamespace(get=lambda k, d=None: d,
                                                set=lambda k, v: None))
    ctx = SimpleNamespace(message=lines.append, extension=ext)
    actions.greet(ctx)
    assert lines == ["Hi"]
```

## 7. Installing, sharing, removing

```bash
xefm ext install ./hello-xefm          # shows what it adds and asks
xefm ext install github:me/hello-xefm  # a GitHub repo (manifest at the root)
xefm ext list
xefm ext disable hello-xefm | enable hello-xefm
xefm ext uninstall hello-xefm          # asks before deleting its data
```

To share a package, put it in a GitHub repository with the manifest at the
repository root, or zip the folder.

## When `xefm ext check` complains

Every line reads `error: xefm-extension.toml: <field>: <what is wrong>`. Fix
that field — do not rename things at random:

- `… has no top-level 'greet'` — the function is missing, misspelt, or nested
  inside another block; or the reference names the wrong module.
- `module … is not in the package — expected hello_xefm/actions.py` — create
  that file, or fix the reference.
- `unknown key` / `unknown section` / `unknown contribution` — the message
  lists the valid spellings.
- `is a built-in action` — prefix the action name.
- `top-level module 'x' is also provided by 'other'` / `would shadow` — rename
  your Python package.
- `'._x' is private` / `'xefm.x' is internal to XeFM` — rewrite that line with
  the public API in section 3. If the public API cannot do what is needed,
  say so to the user rather than reaching past it; that gap is worth
  reporting to XeFM.
- `asks for API version N; this XeFM has M` — set `api_version = M` and check
  the code still uses only the API above.
