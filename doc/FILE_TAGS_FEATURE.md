# File Tags

XeFM reads and writes the tags your system already keeps, so a tag added in
XeFM shows up in Finder (or Dolphin, or the S3 console), and tags added there
show up in XeFM. There is no separate XeFM tag list to keep in sync.

## Tagging: B

Press **B**, the same key that adds a favorite. After the favorite rows, the
dialog lists tag rows. They act on the selected items, or on the item under the
cursor when nothing is selected:

```
Favorite: This directory: projects
Favorite: Under the cursor: notes.txt
Tag: ✓ Work
Tag:   Urgent · red
Tag: Edit tags… (notes.txt)
```

- **A tag row** toggles that tag. A ✓ means every item already has it, and
  choosing the row removes it. Otherwise the row adds it to every item. The
  rows list the tags you have used, plus tags XeFM has seen on files during
  this session.
- **Edit tags…** opens the tags all the items share as one line, such as
  `Work, Urgent`. Edit it and press Enter:
  - a name you remove is taken off every item;
  - a name you add is put on every item;
  - tags that only some of the items have are left alone.

**B** then **Enter** still adds the current directory to your favorites, since
that row stays first.

## Seeing tags

Each tagged file shows up to three dots after its name, in the tag's color, or
gray for a tag without a color. Finder's list shows only the colored ones,
and a tag without a color appears in **Get Info**. XeFM shows those too,
since it has no column for tag names. The dots are read in the background as rows
come into view, so a slow network folder never holds up the list.

Files on S3 and over SSH don't show dots: each lookup there is a separate
network request. Their tags still work through **B** and **Search Tags**.

## Finding by tag: View → Search Tags…

**View → Search Tags…** lists your tags. Pick `Work`, or type a tag name that
is not in the list, and the pane shows every file tagged *Work* in the current
directory and below, as a list you can work on like any other. Press Backspace
to go back. On macOS, Spotlight answers this instantly. Elsewhere, or when
Spotlight finds nothing, XeFM searches the folders, and you can press Esc to
stop.

The action is `find_by_tag`. It has no key in either keymap; bind one in
`KEY_BINDINGS`, or run it from the command palette.

To take a tag off the list, highlight it and press the remove key
(**Shift-Delete**). That only drops it from XeFM's list. Files keep the tag.

## Where tags are kept

| Where the files are | Tags used | Colors |
|---|---|---|
| macOS | Finder tags; Spotlight finds them too | yes, Finder's seven |
| Linux | `user.xdg.tags`, as in KDE's Dolphin | no |
| Windows | an NTFS stream `xefm.tags` on the file (see below) | kept |
| S3 | object tags: each tag is a key with an empty value | no |
| SSH | the remote system's own tags: Linux `user.xdg.tags`, macOS Finder tags | as the remote |
| inside archives | not supported | — |

A new tag named after a Finder color ("Red", "Blue", …) gets that color, as it
does in Finder. A tag that already has a color elsewhere keeps it.

**Windows** has no system-wide file tags. Explorer's "Tags" are stored inside
certain file types only, so XeFM keeps tags in a hidden stream on the file
itself. They follow the file when it is renamed or moved on an NTFS drive.
Other programs don't see them. They are lost when a file is copied to a FAT or
exFAT drive, a cloud folder or an archive, or by a tool that copies only the
file's contents. XeFM's own copies keep them.

**Linux** keeps tags in extended attributes, which ext4, btrfs and XFS support.
FAT, exFAT and many network shares do not, and XeFM says so if you try to tag a
file there. GNOME's Files app does not show these tags.

**SSH** uses the remote system's tools: `getfattr`/`setfattr` on Linux (from
the `attr` package) and `xattr` on macOS. If they are missing, XeFM names the
package to install.

**S3** tags are limited to 10 per object, a limit that includes tags other
tools have set. Tags that have a value (`owner=ops`) belong to someone else;
XeFM leaves them as they are.

## Copying and moving

When XeFM copies or moves a file, the copy gets the original's tags. This also
works across storage, for example from your Mac to an SSH host or from Linux to
S3, when both sides keep tags. A file that loses its tags on the way is still
copied, with a note in the log.

## See also

- [Navigation dialogs](NAVIGATION_DIALOGS_FEATURE.md) — favorites, J and B
- [Virtual Folders](VIRTUAL_FOLDERS_FEATURE.md) — lists of files from anywhere
