# Search Options Feature

## Overview

The search dialog (`find_files` for filenames, `find_in_files` for contents,
`index_search` for the OS index; `Tab` steps between them) carries four
live options: whether capitals are matched exactly, whether only whole words
count, whether the query is a regular expression, and whether subfolders are
searched. They change the search you are already looking at — results re-run the
moment you flip one — and they are all behind one key.

Press the **options** key while the search dialog is open — the dialog's footer
names it, and so does `F1`.

## The chips

The right-hand end of the status row, next to the result count, always shows one
chip per option that applies. A chip is **filled with the accent color when the
option is on** and sits on a plain grey block when it is off, so the strip says
what this particular search is doing at a glance and you never have to open
anything to find out.

```
3 results                        [ Aa ] [ Word ] [ .* ] [ Sub ]
                                   off    off      on     on
```

| Chip | On means |
|------|----------|
| `Aa` | Capital letters are matched exactly |
| `Word` | Only whole words match — `cat` no longer finds `concatenate` |
| `.*` | The query is a regular expression |
| `Sub` | Subfolders are searched |

**Click a chip to flip it.** The block you see is the button — the whole filled
area, padding included — so the strip is the quickest way to change one option
without opening anything. The search re-runs on the click.

Filename search shows only `Aa` and `Sub`: filenames are matched as glob
patterns, so whole-word and regular-expression do not apply there and are not
listed at all. The OS index shows none of the four: it reads its own query
language and always searches everything below the folder.

## The options box

It opens a small box over the search. There is no typing in it, so **every
option is toggled by the initial of its name**:

```
  Case sensitive                off
  Whole word                    off
  Regular expression             on
  Search subfolders              on
```

- `c` / `w` / `r` / `s` — toggle that option straight away
- `↑` `↓` — move, `Space` — toggle what is selected
- a click on a row toggles it too, and the box stays open
- `Esc` or `Enter` — close

Changes apply the moment you make them; the search behind the box re-runs while
you watch. There is nothing to confirm, and closing does not undo anything.

### Case sensitive

Off by default, so `todo` finds `TODO`. Turn it on and only the capitals you
typed match. Applies to both filename and content search.

### Whole word

Off by default. On, the query has to sit on a word boundary at both ends:
`cat` finds `a cat sat` but not `concatenate`. Content search only.

### Regular expression

**On** by default — that is what content search has always been. `.`, `*`, `+`,
`^`, `$`, `[…]` and friends are live, and an invalid pattern reports
"Invalid pattern" in the status line.

Turn it **off** to search for the characters you typed and nothing more: `a.c`
then matches `a.c` and not `abc`, and a query that would be an invalid regular
expression — `C++(` — simply searches for itself. Content search only.

### Search subfolders

On by default — the whole tree under the current directory. Turn it off to
search this directory alone, which is useful right after filtering the pane,
when you mean "these files here".

Subdirectories still *match* by name in filename search when this is off; they
are just not walked into.

## Filter chips

Three more chips narrow what is found, in every mode, without any query
syntax:

```
3 results            [ Aa ] [ .* ] [ Sub ] [ Images ] [ Date ] [ Size ]
```

| Chip | Values |
|------|--------|
| `Kind` | Any kind, Folders, Documents, Images, Videos, Audio, Archives |
| `Date` | Any date, modified Today, in the Past 7 days, the Past 30 days, This year |
| `Size` | Any size, 1 MB, 100 MB or 1 GB or more (files only) |

**Click a chip to pick a value** from a menu under it. A chip that narrows
the search shows its value (`Images`) in the accent color; one that does not
shows its name on grey. In the options box they are rows like the others:
`k`, `m` and `z` step to the next value, and `←` / `→` step either way.

The chips combine with what you type: `*report*` with **Documents** finds
documents whose name contains "report". In filename search and in the OS
index they also **search on their own**, with the field empty. Content search
needs words to look for.

The kinds are decided by file extension, the same way in every mode:
Documents are PDF, Office, OpenDocument, iWork, text, Markdown, CSV and EPUB
files; Archives include `.zip`, `.tar.gz`, `.7z`, `.rar`, `.dmg` and `.iso`.

The chips go back to **Any** every time the dialog opens, for the reason
Search subfolders does.

## Recent searches

Each mode keeps the queries you searched with. Click `▾` at the right end of
the query field, or press `Alt-↓`, for the list. Picking one puts it in the
field and searches. **Clear Recent Searches** forgets that mode's list. A
query is remembered when you press `Enter` on its results.

## What is remembered

Case, whole word and regular expression stay as you set them for the rest of the
session, so a preference you express once keeps applying. **Search subfolders
always goes back to on** when you reopen the dialog: a scope you narrowed for
one search should not silently narrow the next one, especially since it is the
option that decides how much of your disk gets read.

Nothing is written to disk — reopening XeFM starts from the defaults again.

## Changing the keys

The keys shipped for the `options` action are in `_config.py`, and both are
rebindable in `~/.xefm/config.py`:

```python
KEY_BINDINGS = {
    'search.options': ['Ctrl-P'],
}
```

Each option also has an action of its own, deliberately left **unbound**, for
the one you change often enough to want a direct key:

```python
KEY_BINDINGS = {
    'search.toggle_case': ['Ctrl-T'],       # match capitals exactly
    'search.toggle_word': ['Ctrl-W'],       # whole words only
    'search.toggle_regex': ['Ctrl-R'],      # read the query as a regex
    'search.toggle_subdirs': ['Ctrl-Y'],    # subfolders, or this directory only
}
```

The key must be one the query field does not want: the search dialog is a text
field, so anything printable — including Space — is typing and can never fire an
action. Use a modified or non-printable key. XeFM says so in the log pane at
startup if a binding breaks this rule.

## See also

- `doc/KEY_BINDINGS_FEATURE.md` — the full key-binding reference
- `doc/MIGEMO_SEARCH_FEATURE.md` — finding Japanese names by typing romaji
- `doc/dev/OPTIONS_SYSTEM.md` — how the options mechanism is built
