# File List Layouts

English \| [日本語](FILE_LIST_LAYOUTS_FEATURE.ja.md)

A **layout** decides what each row of the file list shows: which columns, in
what order, how each value is written, and what small marks sit beside the
text. XeFM ships one layout, **Default** — name, extension, size and date, with
your tags as colored dots after the name — and you can define more in
`config.py`: one built around Git status for working trees, a narrow one with
only names and sizes, one that shows dates as "3 days ago".

The values a layout shows are **attributes**. Name, extension, size, date,
tags and a folder's total size are built in; `config.py` and extension
packages can add their own, such as a Git status or a line count.

> **Preview.** `ATTRIBUTES`, `LAYOUTS` and `LAYOUT_RULES` may still change in
> any release. XeFM logs one line when your config uses them. See
> [Customization](CUSTOMIZATION_FEATURE.md).

## Choosing a layout

**View → Layout ▸** lists every layout. The choice belongs to the active
pane's current tab: each tab keeps its own, a new tab starts with the one it
was opened from, and XeFM remembers them across sessions. The
`choose_layout` action opens the same choice as a dialog, and is in the
command palette.

**Automatic**, where every tab starts, lets `LAYOUT_RULES` in `config.py` pick
a layout for each folder you open (see below). Choosing a layout by hand fixes
the tab on it until you choose **Automatic** again. With no rules, Automatic
means **Default**.

## Folder sizes

The size column shows `<DIR>` for a folder, because finding out how much a
folder holds means counting everything below it. **View → Calculate Folder
Sizes** (`calculate_folder_sizes`) counts it and shows the total in the size
column:

- with items selected, the selected folders;
- otherwise the folder under the cursor;
- with the cursor on a file, every folder in the pane.

Counting runs in the background, and each total appears as it is done.
Leaving the folder stops it. The totals stay while you are in the folder; one
whose folder changed meanwhile goes back to `<DIR>` until you calculate it
again.

## Sorting by a column

The sort dialog (`sort`) lists, after its own keys, the columns of the pane's
layout that are not already one of them — **Total size** in the default
layout, a Git status in a layout that shows one. Sorting by such a column:

- orders **this folder only**. Go to another folder and the pane is sorted the
  way it was before; come back and choose it again.
- uses the values the pane already has. A row without one — a folder whose size
  was not calculated — goes last, whichever way the sort runs.
- is greyed out while values are still arriving, for a column that is filled
  in automatically. It becomes available once every row has its value.

**View → Reverse Sort** reverses it, as it does any other sort. The status bar
shows it with "(this folder)".

## Defining your own

Open **Tools → Edit Configuration…**. The three tables below are documented
with examples in the comments above them in the file itself.

### `ATTRIBUTES` — values XeFM can know about an entry

One function, `read(directory, entries)`, computes the values on a background
thread. `entries` are rows of one folder and `directory` is that folder; it
returns one value per entry, in the same order. XeFM hands it a whole folder at
once, so a source that answers a folder in one go — `git status` — is asked
once rather than once per file:

```python
import subprocess

def line_count(directory, entries):
    def count(entry):
        with open(entry.path, 'rb') as f:
            return sum(1 for _ in f)
    return [count(e) for e in entries]

def git_status(directory, entries):
    try:
        def git(*args):
            return subprocess.run(['git', *args], cwd=str(directory), check=True,
                                  capture_output=True, text=True).stdout
        prefix = git('rev-parse', '--show-prefix').strip()
        items = git('status', '--porcelain', '-z', '--', '.').split('\0')
    except (OSError, subprocess.CalledProcessError):
        return [None] * len(entries)        # not a Git working tree
    codes, skip = {}, False
    for item in items:
        if skip or len(item) < 4:
            skip = False
            continue
        code, path = item[:2], item[3:]
        skip = code[0] in 'RC'              # a rename's old path follows
        if path.startswith(prefix):
            # the entry here the change is in: a file, or the folder holding it
            name = path[len(prefix):].split('/')[0]
            codes.setdefault(name, code.strip()[:1])
    return [codes.get(e.path.name) for e in entries]

class Config:
    ATTRIBUTES = {
        'lines': {'label': 'Lines', 'type': 'count', 'read': line_count},
        'git': {
            'label': 'Git status', 'type': 'enum', 'read': git_status,
            'values': {
                'M': {'label': 'Modified',  'color': 'yellow'},
                'A': {'label': 'Added',     'color': 'green'},
                '?': {'label': 'Untracked', 'color': 'muted'},
            },
        },
    }
```

| Key | What it says |
|---|---|
| `read` | The function: `read(directory, entries)`, returning one value per entry in the order of `entries`. |
| `label` | The name shown in the sort dialog. |
| `type` | `text`, `count`, `size` (bytes), `time` (a timestamp), `enum` (one of `values`) or `tags`. It decides how the value is written and how it sorts. |
| `values` | For an `enum`: each value's meaning, and a color to show it in. |
| `where` | The storage it is asked about: `local` (the default), `archive`, `ssh`, `s3`. A call per file is cheap on a disk and a request each on S3. |
| `compute` | `auto` (the default) or `on_request`. |

Defining an attribute shows it nowhere — a layout does that. Once a layout on
screen shows it, it is worked out for **every row of the folder**, in the
background, so a definition should answer a folder's worth quickly. One that
cannot — it reads every file whole, say — sets `'compute': 'on_request'`, and
is then computed only when you ask: **View → Compute Values**
(`compute_values`), for the selection or the item under the cursor. It is
then handed one entry per call, so the values appear one by one and leaving
the folder stops them.

A value is empty until it arrives. A function that fails, or returns a list of
the wrong length, costs only that call's values, and says so once in the log
pane.

Your own functions — a sort key, a filter, an action — can read a value XeFM
already has with `entry.attr('git')`. It never computes one and never waits:
until the value is there, it is `None`.

### `LAYOUTS` — how a row is drawn

```python
from xefm.user_api import Cell

GIT_MARK = {'M': Cell('●', color='yellow'),
            'A': Cell('+', color='green'),
            '?': Cell('?', color='muted')}

def git_mark(value, entry):
    return GIT_MARK.get(value, '')

class Config:
    LAYOUTS = {
        'git': {
            'label': 'Git',
            'columns': [
                {'attr': 'name', 'markers': [
                    'tags',
                    {'attr': 'git', 'format': git_mark, 'side': 'before',
                     'max_width': 1},
                ]},
                'ext',
                'size',
                {'attr': 'mtime', 'format': 'relative', 'priority': 1},
            ],
        },
        'compact': {'label': 'Name and size', 'columns': ['name', 'size']},
    }
```

A column is an attribute's name, or a dict:

| Key | What it says |
|---|---|
| `attr` | The attribute to show. |
| `format` | How to write it: a format's name (below) or a function of your own. |
| `width` | In cells. Each format has its own. |
| `align` | `left` or `right`. Numbers and dates are right-aligned. |
| `priority` | When the pane is too narrow, columns with a priority are dropped, lowest first. A column without one stays. |
| `markers` | Small marks drawn beside this column's text (below). |

Every layout has a `name` column, and it takes the width the others leave.
Leave out `ext` and the extension stays part of the name. The built-in
`name`, `ext`, `size`, `mtime`, `tags` and `total_size` (a file's size, or a
folder's once it is calculated) can be used in any layout.

**Formats.**

| Type | Formats (the first is the default) |
|---|---|
| `size` | `compact` (`12.3K`), `bytes` (`12,345`) |
| `time` | `short`, `full` — `DATE_FORMAT` picks between them by default — `iso`, `relative` (`5 min ago`), `recent` (`13:24` today, `10/21` this year, `2024` before) |
| `enum` | `letter` (the value itself), `word` (its label from `values`) — both in its color |
| `tags` | `dots`, `names` |
| `count` | `number` |
| `text` | `text` |

A function of your own takes `(value, entry)` and returns text, or a `Cell` to
color it — or a list of them. `value` is `None` while the value is still being
worked out. A `Cell`'s `color` is `'muted'`, `'accent'`, `'accent2'`,
`'text'`, a name (`'red'`, `'green'`, `'yellow'`, `'blue'`, `'purple'`,
`'orange'`, `'gray'`) or an `(r, g, b)`; it can also be `bold` or `italic`.
The selection, the cursor and the resting pane's dimming still apply on top,
so a color never makes a row unreadable.

**Markers** are marks beside the text of the column they are in, the way the
tag dots sit after the name: an attribute's name, or a dict with `attr`,
`format`, `side` (`'after'`, the default, or `'before'`) and `max_width` (3
cells unless you say). A marker with nothing to show on a row takes no room
there. On the name column the name gives up the room its markers take; on any
other column the room is kept free on every row, so the values stay lined up.

**Replacing the default.** Naming a layout `'default'` replaces the built-in
one, which needs `'override': True` so that a typo cannot.

### `LAYOUT_RULES` — which layout a folder gets

A list of `(condition, layout)` pairs, read top to bottom; the first that
matches decides, for every tab on **Automatic**. A condition is a path
pattern, or a function of the folder's path — which runs on a background
thread, so it may look at the disk:

```python
def in_git_tree(path):
    return any((p / '.git').exists() for p in (path, *path.parents))

class Config:
    LAYOUT_RULES = [
        ('s3://*', 'compact'),
        (in_git_tree, 'git'),
    ]
```

### From an extension package

An extension package can bring attributes and layouts
(`[contributes.attributes]`, `[contributes.layouts]`; see
[Extension Packages](EXTENSIONS_FEATURE.md)). It cannot bring rules: whether a folder
uses a layout is yours to say, so installing an extension never changes how
your folders look.

## Related

- [Sort Dialog](SORT_DIALOG_FEATURE.md)
- [File Tags](FILE_TAGS_FEATURE.md)
- [Customization](CUSTOMIZATION_FEATURE.md)
- [Menu Bar](MENU_BAR_FEATURE.md)
