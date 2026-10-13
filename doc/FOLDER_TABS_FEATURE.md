# Folder Tabs

Each pane can hold several **tabs**, and each tab keeps its own place open.
Use them for the handful of directories a task moves between, or to keep a
search result or an imported list while you browse somewhere else.

| Action | Key | Menu |
|--------|-----|------|
| `new_tab` | `T` | View → New Tab |
| `open_in_new_tab` | `Shift-T` | View → Open in New Tab |
| `close_tab` | `Ctrl-W` | View → Close Tab |
| `next_tab` | `Ctrl-PageDown` | View → Next Tab |
| `prev_tab` | `Ctrl-PageUp` | View → Previous Tab |

All of them act on the **active pane**. The left and right panes have separate
tabs.

## Opening and closing

- **New Tab** opens a tab showing the same place as the current one, with the
  cursor on the same item, and switches to it. On a search result or a list,
  the new tab shows that list's directory, and the results stay in their own
  tab.
- **Open in New Tab** opens the directory under the cursor in a new tab, so
  the current tab stays where it is.
- **Close Tab** closes the current tab and shows the next one. A pane's last
  tab can't be closed.
- **Next / Previous Tab** wrap around at either end.

## The tab strip

Once a pane has more than one tab, a strip appears above its path:

```
 1 src   2 docs   3 ⌕ TODO
 ~/projects/xefm/doc
```

The current tab is highlighted. Click a tab to switch to it. A pane with one
tab shows no strip, so it takes no extra space in a terminal.

Each label is the directory's name. A search shows as `⌕ query` and an
imported list as `[title]`. Labels are shortened when they don't all fit.

## What a tab keeps

Everything the pane shows: the directory, cursor, selection, sort and filter.
Search results, imported lists and branch views are kept as they are, so you
can leave one and come back to it later.

A directory tab is re-read when you switch back to it. Anything that changed
while it was hidden (including changes made from the other pane) shows up
without a flicker.

**History is shared.** `H` lists the directories you have visited in any tab.

## Between sessions

When you quit, XeFM saves each pane's tabs (directory, sort and filter) and
which tab was current. On the next launch, only the current tab is read. The
others are read the first time you switch to them, so a tab on a remote server
doesn't connect at startup.

A search-result or list tab comes back as its directory. A pane you open on a
directory from the command line starts with that one tab.

## Changing the keys

```python
KEY_BINDINGS['next_tab'] = ['Ctrl-PAGE_DOWN', 'Ctrl-TAB']
KEY_BINDINGS['prev_tab'] = ['Ctrl-PAGE_UP', 'Ctrl-Shift-TAB']
```

`Ctrl-Tab` is not a default because terminals don't send it. Add it yourself
if you only use the desktop app. See [Key Bindings](KEY_BINDINGS_FEATURE.md).
