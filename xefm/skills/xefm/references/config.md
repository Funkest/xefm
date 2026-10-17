# Editing XeFM's configuration

Read `SKILL.md` first: the ground rules there (never launch XeFM, finish with
a reload or restart) apply here too.

## 1. The file

The configuration is **`~/.xefm/config.py`**, an ordinary Python file that
XeFM executes. It must define `class Config:`, and every setting is an
UPPER_CASE attribute of that class:

```python
from xefm.external_programs import xefm_tool, xefm_python
from xefm.backend_detector import is_desktop_mode

class Config:
    TEXT_EDITOR = 'code' if is_desktop_mode() else 'vim'
    KEY_BINDINGS = {
        'reload_config': ['F12'],
    }
```

- **A setting the file leaves out keeps XeFM's default.** XeFM fills every
  missing attribute from its template, so adding one setting means adding one
  attribute — never pasting in the rest.
- **The template is the authority on names and shapes**: `xefm/_config.py` in
  the XeFM source, every setting with a comment. Read the one for the user's
  version: `https://github.com/crftwr/xefm/blob/vX.Y.Z/xefm/_config.py`
  (`xefm --version`, or **Help ▸ About**, gives X.Y.Z). The user's own
  `config.py` started as a copy of it, so it usually holds the same comments —
  from the version they first installed, which may be older.
- XeFM creates the file on first launch. If it does not exist, ask the user to
  start XeFM once rather than writing one from scratch.
- On Windows the file is `C:\Users\<name>\.xefm\config.py`.

## 2. Rules for editing

- **Change only what was asked.** Edit the one attribute (or the one entry in
  a table) the request is about. Keep every other line, the user's comments,
  and the order of the file as it is.
- **Never regenerate the file** from the template, and never "tidy" it. It is
  the user's file; it may hold settings and functions you do not recognize.
- **Edit an attribute that is already there** rather than adding a second
  one: in a class body the later assignment silently wins. Search for the name
  first, including commented-out copies (`# KEY_BINDINGS = …`) — uncomment
  and edit those rather than adding a new block next to them.
- **Keep the user's conditionals.** `TEXT_EDITOR = 'code' if is_desktop_mode()
  else 'vim'` says the desktop app and the terminal want different editors.
  When the user asks for a different editor, change the branch they mean, or
  ask which one.
- **Copy the file first** for anything beyond a one-line change
  (`config.py.bak` beside it), and say so. A broken file costs the user their
  whole configuration until it is fixed (see *Checking an edit*).
- No secrets. `NETWORK_SERVERS` has no password field on purpose; passwords go
  in the system keychain from XeFM's own connection dialog.

## 3. The main tables

### Keys: `KEY_PRESET` and `KEY_BINDINGS`

Every key comes from a **keymap preset**: `'afx'` (single letters: `C` copy,
`M` move, `K` delete …) or `'orthodox'` (function keys: `F5` copy, `F6` move,
`F8` delete; letters start an incremental search). The user picks one at
first launch or in **Tools ▸ Keymap**; `KEY_PRESET = 'afx'` or `'orthodox'` in
`config.py` overrides that choice. `None` (the default) leaves it to the menu.

`KEY_BINDINGS` holds **only the user's changes** to the preset. An entry
replaces that action's keys under every preset; an action not listed keeps the
preset's keys.

```python
KEY_BINDINGS = {
    'reload_config': ['F12'],                    # action -> list of keys
    'quit': [],                                  # an empty list unbinds it
    'delete_permanently': {'keys': ['Shift-DELETE'], 'selection': 'required'},
    'text_viewer.page_down': ['SPACE'],          # inside one viewer only
}
```

- Keys: a character (`'Q'`, `'?'` — a capital letter is *not* Shift), a name
  (`'ENTER'`, `'ESCAPE'`, `'TAB'`, `'SPACE'`, `'UP'`, `'PAGE_DOWN'`, `'F1'`…`'F12'`,
  `'DELETE'`, `'BACKSPACE'`), or a chord with `Shift-`, `Ctrl-`, `Alt-`,
  `Cmd-` (macOS): `'Ctrl-T'`, `'Shift-F'`, `'Cmd-ENTER'`. A name XeFM does not
  know never fires and is only reported in XeFM's log.
- `'selection'`: `'any'` (default), `'required'` (only with files selected),
  `'none'` (only without).
- **Action names** are listed in
  https://crftwr.github.io/xefm/doc/KEY_BINDINGS_FEATURE.html, and in XeFM's
  help (`F1`) and command palette. Use those names exactly; do not guess one
  from a menu label.
- **A key the user wants may already be taken** (by the preset or another
  entry). Find out which action has it and say so; if the user wants the key
  moved, give that action its other keys (or `[]`) explicitly, so nothing is
  left bound twice.
- A config from an XeFM older than the presets may hold a *full* copy of the
  old keymap in `KEY_BINDINGS`. Every entry in it overrides the preset. Do not
  delete it on your own; if the user's keys are not what the preset promises,
  point at it.

Key names in full: https://crftwr.github.io/xefm/doc/KEY_BINDINGS_FEATURE.html.
Presets: https://crftwr.github.io/xefm/doc/KEYMAP_PRESETS_FEATURE.html.

### Editor, diff tool, shell, terminal

```python
TEXT_EDITOR = ['code', '--wait']   # edit_file; a string or an argv list
TEXT_DIFF = ['code', '--diff']     # E in the diff viewers
SUBSHELL = None                    # None = $SHELL, else the platform's
TERMINAL = None                    # desktop app only: where terminal programs open
```

A string is split like a shell command line; a list is taken as argv, and is
the form to use for a Windows path with spaces or backslashes.

### Favorites

```python
FAVORITES = [
    {'name': 'Home', 'path': '~'},
    {'name': 'Work', 'path': '~/work'},
    {'name': 'Todo', 'path': '~/notes/todo.md'},     # a file works too
    {'name': 'Server', 'path': 'ssh://devbox/var/www'},
]
```

Append to the list; keep the user's entries and their order. Favorites the
user adds inside XeFM (the **Add to Favorites** command) are kept in XeFM's own
state, not in this file — you will not find them here, and should not copy
them in. `DRIVE_LOCATIONS` (the Drives dialog's fixed rows, `None` = built-in)
and `NETWORK_SERVERS` (`{'name', 'url', 'user'}`) have the same shape.

### External programs: `PROGRAMS`

```python
PROGRAMS = [
    {'name': 'Open in VSCode', 'command': [xefm_python, xefm_tool('vscode.py')]},
    {'name': 'Disk usage', 'command': ['du', '-sh']},
    {'name': 'View with less', 'command': ['less'], 'options': {'terminal': True}},
]
```

`command` is an argv list. `options: {'terminal': True}` hands the terminal to
a full-screen program (in the desktop app it opens in `TERMINAL`). The
program gets the panes' directories and selections as `XEFM_*` environment
variables. `xefm_tool('x.py')` finds a script in `~/.xefm/tools/` first.

### File associations: `FILE_ASSOCIATIONS`

A list of rules, read top to bottom. For each action, the first rule that
matches the file name **and names that action** wins; a matching rule that
leaves an action out lets a later rule supply it.

```python
{
    'pattern': ['*.jpg', '*.png'],        # fnmatch, one or a list
    'enter': 'viewer',                    # ENTER: 'viewer', 'navigate', 'list' or None
    'open|view': ['open', '-a', 'Preview'],   # several actions, one command
    'edit': None,                         # not available
}
```

`enter` names a built-in handler, never a program. `open` (Cmd/Ctrl-Enter),
`view` (V) and `edit` take a command; `'view': None` means XeFM's own viewer.
Put a new rule above a broader one that names the same action. There is
deliberately no rule for text files: the built-in viewer sniffs them.

### Themes: `THEMES`

`THEMES` *defines* themes; it does not choose one. Which theme is shown is
picked in XeFM (**View ▸ Theme**, or the theme-cycle key) and remembered there.
So "switch to the dark theme" is something the user does in XeFM — tell them
so rather than editing the file. To add or tweak a theme:

```python
THEMES = {
    'Ocean': {                                  # a new theme, built on Dark+
        'accent': (38, 139, 210),               # colors are (R, G, B), 0-255
        'file_types': {'directory': (120, 200, 220)},
    },
    'Paper': {'base': 'Light+', 'file_types': {'directory': (150, 110, 0)}},
}
```

Built-ins: Dark+, Monokai, Dracula, Nord, Solarized, Gruvbox Dark, Light+,
Solarized Light. A theme with no `base` builds on the built-in of the same
name, else on Dark+. Every key a theme may set is listed in the template's
comment above `THEMES`.

### Actions: `ACTIONS` (Preview API)

A short function of the user's own, bound to a key:

```python
def select_documents(ctx):                       # module level, above class Config
    """Select every Word/PDF document in the active pane."""
    n = ctx.pane.select(lambda e: e.suffix.lower() in ('.docx', '.pdf'))
    ctx.message(f"Selected {n} document(s)")

class Config:
    ACTIONS = {'select-documents': select_documents}
    KEY_BINDINGS = {'select-documents': ['Shift-Y']}
```

The function gets the same `ctx` an extension does — the API is in
`references/extensions.md`, section 3, and the same rules hold (no `print()`,
no private names, keep it quick). `EVENT_HOOKS`, `SORT_KEYS`, `FILTERS`,
`IMAGE_DECODERS`, `PATH_SCHEMES` and `LEXERS` work the same way; the template
documents each. Anything longer belongs in an extension (see `SKILL.md`).

### Everything else

Confirmations (`CONFIRM_*`), `DELETE_TO_TRASH`, `SHOW_HIDDEN_FILES`, sort
defaults, fonts (`UI_FONT_NAME`, `MONO_FONT_NAME`, `FONT_SIZE`, desktop app
only), Migemo search, caches, file monitoring: each is one attribute, named
and explained in the template. Look it up there; do not invent a name — an
attribute XeFM does not know is silently ignored.

## 4. Checking an edit

XeFM cannot be started to try the file, and there is no `xefm config check`.
What you can check:

1. **It parses.** With any Python 3 (use the full path on Windows):

   ```bash
   python3 -c "import ast, sys; ast.parse(open(sys.argv[1], encoding='utf-8').read())" ~/.xefm/config.py
   ```

   This proves the syntax only. The file imports from `xefm`, so it cannot be
   run outside XeFM.
2. **By reading it back:** `class Config:` is still there, the attribute you
   changed appears once, its name matches the template exactly, and the value
   has the shape the template shows (a list where it wants a list, a dict
   entry with the keys it wants).

Tell the user what you checked and what you could not. If loading fails, XeFM
logs `Error loading configuration: …` and runs on **built-in defaults for
everything** — the user's other settings are not lost from the file, but none
of them apply until it is fixed. An out-of-range value is applied and logged
as `Config warning: …`.

## 5. Applying it

**Tools ▸ Reload Configuration** applies, without a restart: key bindings,
the keymap preset, file associations, external programs, favorites,
confirmations, the editor and diff tool, and `ACTIONS` and the other function
tables.

**A restart** is needed for: themes and their effects, fonts, the pane-split
and log-height ratios, and file-monitoring intervals.

Say which one the change needs.
