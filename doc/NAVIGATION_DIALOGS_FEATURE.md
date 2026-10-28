# Navigation Dialogs

English \| [日本語](NAVIGATION_DIALOGS_FEATURE.ja.md)

XeFM's directory navigation dialogs all share one searchable-list picker: a
scrollable list you filter by typing, with the same keys for moving through it
and choosing an entry. Four actions open four flavors of that picker (press `F1`
for the keys yours are on, or find them in the **Go** menu). Keys depend on your keymap preset — see
[Keymap Presets](KEYMAP_PRESETS_FEATURE.md#every-key-side-by-side).

| Action | Dialog | What it lists |
|--------|--------|---------------|
| `favorites` | Favorites | Your favorite directories and files |
| `history` | History | Directories you have already visited in this pane |
| `drives` | Drives | Storage locations and volumes (and S3 buckets, if available) |
| `connect_server` | Connect to Server | Saved servers, plus the ones found on the network (macOS and Windows) |

Whichever one you open, pressing **Enter** navigates the current pane to the
selected location.

A fifth way to go somewhere, [Jump to Path](#jump-to-path) (`jump_to_path`), is
not a list: it is a field you type or paste a path into.

## Shared controls

Every navigation dialog uses the same list-picker controls:

- **Type** to filter the list, using the same search syntax as the file pane's
  incremental search: matching is case-insensitive and hits anywhere in the row,
  several keywords separated by spaces all have to match (`work src` finds
  `Projects — /home/me/work/src`), `*` and `?` wildcards work (`*.py`), and
  romaji finds Japanese entries through Migemo (`kensaku` finds `検索`).
  The best matches come first: a row that starts with what you typed, then one
  where it starts a word (after a space, `/`, `_`, `-` or `.`), then one where
  it is inside a word, so `doc` puts `Documents` above a favorite whose path
  merely ends in `/docs`. Rows that match equally well keep the list's own order
- **Backspace** to remove filter characters
- **Up/Down** to move through results
- **Page Up/Page Down** to scroll by page
- **Home/End** to jump to the first/last result
- **Enter** to navigate to the selected entry
- The **remove** key (`remove_list_item`) to drop the highlighted entry, where
  there is something to
  remove: it forgets a directory in History or the Filter prompt, forgets a
  saved server in Connect to Server, forgets a favorite you added with **Add to Favorites…**,
  and disconnects or ejects a volume in Drives. Favorites written in your
  config and External Programs are yours to edit there, so the key leaves them
  alone
- **Escape** or **q** to cancel and close

A line along the bottom of each dialog names the keys that are live in it, so
the remove key shows up only where it applies — and shows the key *you* have
bound if you rebound it.

### Fields with a history

Two dialogs are for text you type rather than an entry you pick: the **Filter**
prompt (**View → Filter…**) and [Open List → From Command](FILE_LIST_IMPORT_FEATURE.md#from-a-command). They
look like a text prompt — a label and a field, no magnifier — with the history
listed below, and they work the other way round:

- **Enter** uses what the **field** holds, always. Typing `py` applies the
  pattern `py`, even with `*.py` in the history.
- Typing narrows the history, but highlights nothing in it.
- **↓** moves into the history and copies the highlighted entry into the
  field. **Enter** there chooses it: you are back in the field with the
  entry's text, to use with a second Enter or to change first. **↑** past the
  first entry, or **Esc**, goes back to what you typed.
- A click copies an entry in; a second click on it uses it.
- The remove key forgets the highlighted entry while you are in the history.
- In the Filter prompt, a filter from your config goes into the field as its
  name, and *clear filter* as an empty field — Enter then clears the filter.

## Favorites

Choose **Go ▸ Go to Favorite…** (`favorites`) to open a searchable list of your favorites and jump to any of them
instantly. A favorite is usually a directory, but it can also be a file: picking
one opens its directory with the cursor on the file.

The list opens immediately, whatever is on it. XeFM does not go and look at your
favorites before showing them — checking a network share that is asleep, offline
or behind a VPN you have not connected can take the better part of a minute per
entry, and a few of those turned opening the list into a stall (issue #430). So
nothing is contacted until you pick a row.

Pick one that is not there and **the pane does not move**. It keeps the
directory it was showing, with your cursor where you left it, and the log says
`Directory not found: …` — one line, once. The same goes for the Drives and
History pickers, which also name directories you cannot see from where you are.

That means a favorite can be anywhere: a NAS, a USB disk you plug in on
Tuesdays, an `ssh://` or `s3://` location. It sits quietly in the list whether
or not it is reachable today.

### Adding and removing favorites

Choose **Go ▸ Add to Favorites…** (`add_favorite`) to add one. XeFM
asks which of two things you mean:

- **This directory** — the directory the pane is showing. It is first, so
  choosing **Add to Favorites…** and pressing **Enter** adds where you are.
- **Under the cursor** — the directory or file the cursor is on.

Then type the name it should be listed under (it starts as the directory's or
file's own name) and press **Enter**. Where only one of the two makes sense —
an empty directory has nothing under the cursor, and a search-results list has
no directory of its own — XeFM goes straight to the name.

Right-clicking a row and choosing **Add to Favorites…** adds that row — the
directory or file you clicked — without the choice, straight to the name.

Favorites added this way are listed after the ones in your config, in the order
you added them, and are kept in XeFM's own state database — your `config.py` is
never rewritten. Adding a place that is already a favorite renames it instead of
listing it twice.

To remove one, highlight it in the Favorites list and press the remove key
(**Shift-Delete** by default). Favorites written in `FAVORITES` are
not removed there: delete them from your config.

### Tags in the same dialogs

**Add to Favorites…** also tags files: its dialog lists your tags after the
favorite rows. Finding files by tag is a search, not a place to go, so it is
**View → Search Tags…**, not **Go to Favorite…**. See [File Tags](FILE_TAGS_FEATURE.md).

### Default favorites

XeFM ships with four — Home, Documents, Downloads and Desktop — and they are
yours to edit from the first run; your `~/.xefm/config.py` holds its own copy.

Each entry is shown with the path you wrote (with `~` expanded), e.g.:

```
Home (/Users/username)
Projects (/Users/username/dev)
Web Server (/var/www)
```

### Favorites in your config

For favorites you want to keep in a file you control — the same list on every
machine you copy your config to — edit `FAVORITES` in your `~/.xefm/config.py`. Each entry needs a
`name` (what to call it) and a `path` (where it is; `~` expands to your home
directory). A `path` may be a file as well as a directory — selecting it opens the
file's directory with the cursor on the file, just like a file favorite added with
**Add to Favorites…**. You don't say which it is: XeFM finds out when you pick the row, so a list
of paths loaded from elsewhere can go in as it is:

```python
class Config:
    FAVORITES = [
        {'name': 'Home', 'path': '~'},
        {'name': 'Work Projects', 'path': '~/work'},
        {'name': 'Scripts', 'path': '~/bin'},
        {'name': 'Web Server', 'path': '/var/www'},
        {'name': 'Todo', 'path': '~/notes/todo.md'},
        # Add your own here
    ]
```

`FAVORITES` used to be called `FAVORITE_DIRECTORIES`, from when it could only
hold directories. A config that still uses the old name keeps working, and if
both are set, the two lists are joined. Renaming yours to `FAVORITES` is all it
takes to switch.

To use different keys, rebind the `favorites` and `add_favorite` actions in
`KEY_BINDINGS`, e.g. `'favorites': ['f']`.

## Jump to Path

**Jump to Path** (`jump_to_path`, also **Go ▸ Jump to Path…**) asks for a path
and takes the current pane there. It is a text prompt, not a list: the
[shared list controls](#shared-controls) above do not apply to it.

The field opens with the current directory already in it, ending in a
separator, so you can type the name of a directory inside it straight away —
or select the whole field and paste a path from somewhere else. It accepts:

- an absolute path (`/var/log`, `C:\Users`)
- a path relative to the current directory (`src/xefm`, `..`)
- `~` for your home directory (`~/Documents`)
- a remote address: `ssh://host/path` or `s3://bucket/prefix` (see
  [SFTP support](SFTP_SUPPORT_FEATURE.md) and [S3 support](S3_SUPPORT_FEATURE.md))

**Tab** completes the name you are typing, files as well as directories — see
[Tab completion](TAB_COMPLETION_FEATURE.md).

A path to a **file** opens the directory it is in, with the cursor on the file —
handy for a full path copied out of a log or an error message.

Press **Enter** to go. A path that does not exist keeps the prompt open and says
so, and **Esc** closes it without moving the pane.

## History

Choose **Go ▸ History…** (`history`) to open a searchable list of directories you have already visited in
the current pane, and jump back to any of them. Each pane keeps its own history.

The **remove** key forgets the highlighted directory. Every visit to it is
dropped, not just the most recent one, and the change is saved immediately. It
is not a blocklist: going there again puts it back at the top.

The number of remembered entries is set by `MAX_HISTORY_ENTRIES` in
`~/.xefm/config.py` (default 100).

## Drives dialog

Choose **Go ▸ Drives…** (`drives`) to open a searchable list of storage locations and jump to one. On
macOS and Windows its first row is **Connect to Server…**, which opens the
[Connect to Server](CONNECT_TO_SERVER_FEATURE.md) dialog.

### Local locations

The list opens with a few fixed locations — Home (`~`), Root (`/`) on macOS and
Linux, and Desktop, Documents and Downloads when they exist — followed by
whatever the machine has mounted: drive letters on Windows, `/Volumes` on macOS,
`/media` and `/mnt` on Linux.

### Choosing your own fixed locations

The fixed part is yours to define. Set `DRIVE_LOCATIONS` in `~/.xefm/config.py`
to the list you want and it replaces the built-in one:

```python
DRIVE_LOCATIONS = [
    {'name': 'Home', 'path': '~'},
    {'name': 'Work', 'path': '~/work'},
    {'name': 'NAS', 'path': 'ssh://nas/'},
]
```

Set it to `[]` to drop the fixed rows entirely and list only the mounted
volumes. Left unset (`None`), you get the built-in set described above.

A local path that does not exist is skipped. A remote location (`ssh://`,
`s3://`) is listed exactly as written, and nothing connects until you select it.

Mounted volumes, SSH hosts and S3 buckets are not configured here — they are
read from the machine every time the dialog opens. The SSH rows come from your
`~/.ssh/config`, so a host you no longer use is removed by editing that file.

### S3 buckets

When `boto3` is installed and AWS credentials are configured, the drives dialog
also lists every S3 bucket your credentials can reach. Select a bucket and press
**Enter** to browse it in the current pane like any other filesystem.

To enable S3 listing, configure AWS credentials with any of: AWS CLI
(`aws configure`), the `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` environment
variables, or an `~/.aws/credentials` file.

If buckets do not appear, check that credentials work (`aws s3 ls`), network
connectivity, and your IAM permissions for `ListBuckets`.

### Disconnecting and ejecting

The **remove** key disconnects the highlighted network mount, or ejects the
highlighted external volume so the device is safe to unplug. On any other row —
Home, `C:\`, an S3 bucket, an SSH host — it does nothing.

If a pane is inside the volume, XeFM moves it out first. If something else on
the machine is using the volume, the operating system refuses and XeFM says so
rather than forcing it.

## Choosing between them

- **Favorites** — instant, for a handful of directories you use constantly
- **History** — instant, for somewhere you were a moment ago
- **Jump to Path** — for a location you can type or paste
- **Drives** — for switching between volumes, drives, or S3 buckets, and
  for disconnecting or ejecting one
- **Connect to Server** — for mounting a NAS or file server in the
  first place

## See Also

- [Connect to Server](CONNECT_TO_SERVER_FEATURE.md) — mounting a NAS or file
  server from inside XeFM
- [S3 Integration](XEFM_USER_GUIDE.md#aws-s3-integration) (in User Guide)
