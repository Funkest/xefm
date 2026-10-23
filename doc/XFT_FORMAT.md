# The .xft Format

English \| [日本語](XFT_FORMAT.ja.md)

An `.xft` file is **a tree of references to places**: groups that hold
other groups or references, and references that point at a file or folder
somewhere (a local path, or a URI such as `ssh://…` or `s3://…`). XeFM
browses it like an archive. See [Tree Files](TREE_FILES_FEATURE.md) for what
that looks like.

The format is meant to be written by programs, such as a duplicate finder, a
search tool or a catalogue script, and read by XeFM. Its first producer is
[similar-files](https://github.com/crftwr/similar-files) (`--format tree`).
This page is the specification.

The format was called `.xefml` until #613 shortened the name to fit the
four-character extension column XeFM's file list shows. XeFM still reads a
`.xefml` file and a `"format": "xefml"` document; write `.xft` and `"xft"`. Producers write it from this description and
need nothing from XeFM's code.

## The file

- UTF-8 JSON, one object. The extension is `.xft`.
- **Replace it whole.** A producer that writes the file more than once
  writes a temporary file next to it and renames it over the old one
  (`os.replace`), so a reader never sees half a file.

```json
{
  "format": "xft",
  "version": 1,
  "title": "Similar videos in /Users/me/Movies",
  "generator": {"name": "similar-files", "version": "0.2.0"},
  "final": false,
  "complete": false,
  "generation": 7,
  "written": 1760340000.5,
  "progress": {"done": 120, "total": 400},
  "nodes": [
    {
      "name": "trip.mp4 (1)",
      "extra": {"method": "video", "threshold": 0.8, "members": 1},
      "children": [
        {"name": "trip.mp4", "target": "/Users/me/Movies/trip.mp4",
         "attrs": {"size": 734003200, "mtime": 1700000000.0},
         "extra": {"role": "anchor", "similarity": 1.0}},
        {"name": "trip-small.mp4", "target": "/Volumes/NAS/trip-small.mp4",
         "attrs": {"size": 120000000, "mtime": 1700100000.0},
         "extra": {"role": "member", "similarity": 0.93}}
      ]
    }
  ]
}
```

## Top level

| Key | Required | Meaning |
|---|---|---|
| `format` | yes | Always `"xft"`. |
| `version` | yes | `1`. A reader refuses a version it does not know. |
| `nodes` | yes | The top-level nodes. |
| `title` | no | What the tree is, in a few words. |
| `generator` | no | `{"name", "version"}` of the producing program. |
| `final` | no, default `true` | `false` while the producer may still rewrite the file. Every write but the last says `false`. |
| `complete` | no, default `final` | On a final file, `false` when the producer stopped before it had looked at everything, such as a cancelled scan. |
| `generation` | no | Counts the writes, starting at 1, so a reader can tell a new snapshot from the one it has. |
| `written` | no | When the file was written, in seconds since the epoch. |
| `progress` | no | `{"done", "total"}` of a producer still working. `total` is `0` when not known. |

## Nodes

A node is an object with a `name` and **at least one of** `children` and
`target`:

| Key | Meaning |
|---|---|
| `name` | The label shown. A `/` or `\` in it reads as `_`. Names should be unique among siblings. A reader makes duplicates unique by adding ` [2]`, ` [3]`, … in order, comparing names as a case-insensitive file system does. |
| `children` | A list of nodes. A node with children is a **group**, shown as a folder. |
| `target` | An absolute path or a URI: the place this node stands for. A node with a target is a **reference**. |
| `attrs` | What the producer recorded about the target: `size` (bytes), `mtime` (seconds since the epoch), `is_dir`. A reader shows these instead of reading the target, which may be on another machine. All are optional. |
| `extra` | The producer's own data, such as a similarity or a role. A reader may show what it understands and ignores the rest. |
| `final` | On a group, `true` when it cannot change any more even though the file as a whole is still provisional. Identical-file groups are final as soon as they are written. |

A node with both `children` and `target` is a group that is also a place: it
opens as a folder, and the pane-sync actions (`sync_current_to_other`,
`sync_other_to_current`) reveal its target.

`line` on a reference is **reserved** for a position in a text file (a search
hit). It is not defined yet.

## Provisional files

While `final` is `false`, every group may still change when the file is next
written. Members can join or leave it, and its first entry can change. A
reader should:

- say that the tree is provisional, with `progress`;
- read the file again when it changes;
- find a group again by the **target of its anchor** (the reference with
  `extra.role` `"anchor"`, or else its first reference) rather than by its
  name, which can change.

Producers write identical-content groups once and mark them `"final": true`.

## Versioning

New optional keys can be added to version 1. Readers ignore keys they don't
know. Any change that would make a version 1 reader show something wrong
gets a new `version`.
