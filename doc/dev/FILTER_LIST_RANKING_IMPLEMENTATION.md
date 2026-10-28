# Filter List Ranking — Implementation

The filter lists put their best matches first (#742). This page covers how a
row is ranked, where the ranking is applied, and a sketch for ranking on more
than the label if a list ever needs it.

User-facing description: [Navigation Dialogs](../NAVIGATION_DIALOGS_FEATURE.md#shared-controls).

## What is ranked

Only the **display label**, the same string the shared query already matches
(`search_match.hit(tokens, to_label(value))`). Ranking therefore never changes
*which* rows pass the filter, only their order — no list can lose a row it
used to show.

The label is one string even where it is built from several fields: a favorite
is `"{name}  —  {path}"`. A match in the name lands at or near the start of the
label and a match in the path lands further in, so the label alone tells them
apart well enough for #742 without the list knowing its own structure. That is
the reason for ranking the label rather than each list's fields: one rule, in
one place, the same in every list.

## The rank — `search_match.rank(tokens, text)`

A sort key, smaller is better, for a text that passed `hit`:

1. Each token's **best occurrence** is graded by where it starts in the
   lowercased NFC label:
   - `TIER_LABEL_START` (0) — at position 0;
   - `TIER_WORD_START` (1) — after a character that is not `isalnum()`
     (space, `/`, `_`, `-`, `.`, `—`, …);
   - `TIER_INSIDE` (2) — anywhere else.

   Among a token's occurrences the best `(tier, start)` wins, so `doc` in
   `"undoc doc"` grades as a word start.
2. The row's tier is its **worst** token's tier (every token has to match, so
   the row is only as good as its weakest), and its position the **latest**
   of the tokens' starts. The key is `(tier, position)`.
3. The caller sorts with a **stable** sort, so rows with equal keys keep the
   list's own order (config order, recency). An empty query gives every row
   `(0, 0)` and changes nothing.

Where a token starts:

- **Glob part:** the token's glob without the `*` that `compile_query` wrapped
  around it for "contains", translated by `fnmatch.translate` with the end
  anchor dropped (`\Z`, or `\z` from Python 3.14), then tried with
  `regex.match(label, pos)` at each position. The compiled core is cached
  (`_core_regex`). A token of stars alone starts at 0.
- **Migemo part:** the token's Migemo regex, counting only non-ASCII hits —
  the same rule `migemo_search.has_hit` applies.

A row that passed `hit` only on its un-normalized text (a decomposed label the
NFC pass does not find again) has no position. It gets `(TIER_INSIDE,
len(label))`, the last place, rather than disappearing.

## Where it is applied

- **`FilterListDialog`** (`xefm/filter_list_dialog.py`): every picker built on
  `show_filter_list` — favorites, drives, history, external programs, command
  palette, find by tag, connect, Filter history, extension pickers.
  - `_refilter` ranks the whole list and selects row 0, the best match.
  - `add_items` (rows streamed in by `load_more`) inserts each new row with
    `bisect_right` on `_ranks`, a sorted list parallel to `filtered`. Equal
    ranks go after the existing rows, so with no query a streamed row appends
    as it always did. The highlighted row keeps its value, unless it is row 0:
    a highlight still on the first row stays on the first row, which is now the
    best match. The scroll offset is kept.
  - `remove_selected` deletes the same index from `_ranks`.
- **`HistoryInputDialog`** (`xefm/history_input_dialog.py`): the history under
  a path field, sorted the same way in `_refilter`.

Not ranked, on purpose: the file pane's incremental search and the text and
diff viewers' search. There a row's position is the content itself, and the
search moves to the nearest match instead.

## Future: ranking on more than the label

If a list ever needs to weigh its fields separately (say, a favorite's name
above its path regardless of where in the label they fall), the step up is for
the list to hand the dialog **match fields** instead of relying on the label:

```python
show_filter_list(..., to_fields=lambda row: [(row.name, 0), (row.path, 1)])
```

- Each field is matched and ranked on its own with the same `rank`, and its
  weight becomes the most significant part of the key:
  `(field weight, tier, position)` of the best field.
- Tokens would still all have to match, but could be satisfied across fields
  (`work src` with `work` in the name and `src` in the path). The row's key
  then needs a rule for combining fields per token — the worst token's best
  field is the natural extension of today's "worst token" rule.
- Fields could include text that is **not shown** (an action's description, a
  favorite's aliases). That is the one change that would let a list find rows
  the label alone does not, so it would need the list to say so in its hint or
  detail line; a row that matches on hidden text with nothing visible
  highlighted is confusing.
- Without `to_fields` a list behaves exactly as now: the label is its single
  field. Today's behaviour is the special case, which keeps every existing call
  site unchanged.

Nothing needs this yet; it is written down so the label-only rule is a choice
with a known way out, not an accident.
