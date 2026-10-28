"""The incremental-search query language — one matcher for the pane and the
dialogs (#349).

A query is whitespace-separated tokens. A token matches a candidate string when
the token, wrapped in ``*`` for "contains" semantics, matches it as an
``fnmatch`` glob, *or* when the token's Migemo regex does (romaji finds
Japanese — see :mod:`xefm.migemo_search`). Tokens combine with AND, so typing
more words narrows; :func:`hit` also offers OR for the pane's non-incremental
callers.

The wrapping is what keeps a bare word a substring search, and it is why a glob
keeps working while staying asymmetric: ``*.py`` wraps to ``*.py*``, i.e.
"contains ``.py``" rather than "ends with ``.py``". The file pane's incremental
search has behaved this way since it was written; the filter-list dialogs now
share the behavior rather than each growing their own dialect.

Compile once per query, match many times: building a token's Migemo regex is
the expensive step (#332 §3.3) while matching with the compiled result is
cheap. So callers hoist :func:`compile_query` out of their row loop — including
the loop that runs again for each streamed batch of rows
(``FilterListDialog.add_items``).
"""

from __future__ import annotations

import fnmatch
import functools
import re
from typing import Sequence

from xefm import migemo_search
from xefm import name_key

#: One compiled token: its "contains"-wrapped, lowercased glob paired with the
#: Migemo regex unioned into it (``None`` where Migemo doesn't apply — disabled,
#: too short, a glob, or no engine).
Token = tuple[str, "re.Pattern | None"]


def compile_query(pattern: str) -> list[Token]:
    """``pattern``'s whitespace-separated tokens, each compiled once for reuse
    across every candidate — see the module docstring on why this is hoisted."""
    tokens: list[Token] = []
    for token in pattern.split():
        # Normalize the query once here rather than every candidate in `hit`:
        # the pane hands in names that are already NFC (xefm.name_key), so a
        # pasted NFD pattern is the only side left that could disagree.
        token = name_key.nfc(token)
        glob = token.lower()
        if not glob.startswith('*'):
            glob = '*' + glob
        if not glob.endswith('*'):
            glob = glob + '*'
        tokens.append((glob, migemo_search.get_regex(token)))
    return tokens


def hit(tokens: Sequence[Token], text: str, *, match_all: bool = True) -> bool:
    """Whether ``text`` passes a compiled query.

    ``match_all`` combines the tokens with AND (the narrowing a filter field
    wants); ``False`` makes it OR. An empty query passes everything under AND
    and nothing under OR — the vacuous truth an empty filter field wants, and
    why the dialogs need no separate "no filter" branch.
    """
    lowered = text.lower()
    hits = (fnmatch.fnmatch(lowered, glob)
            or (regex is not None and migemo_search.search_nfc(regex, text))
            for glob, regex in tokens)
    return all(hits) if match_all else any(hits)


#: How well a token hit a label, best first: at the very start, at the start of
#: a word (after a space, ``/``, ``_``, ``-``, ``.`` or any other non-word
#: character), or somewhere inside a word.
TIER_LABEL_START, TIER_WORD_START, TIER_INSIDE = 0, 1, 2


def rank(tokens: Sequence[Token], text: str) -> tuple[int, int]:
    """A sort key for a ``text`` that passed :func:`hit` — smaller is a better
    match — so a filter list can put its best matches first (#742).

    Each token's best occurrence is graded by where it starts (the ``TIER_*``
    above). The row takes its *worst* token's tier, since every token has to
    match; between rows of one tier the one whose tokens all match earlier
    comes first. Sort with a stable sort, so equal keys keep the list's own
    order — and an empty query, which ranks every row alike, changes nothing.

    Only the label is ranked: the lists match nothing else, so ranking cannot
    find a row that :func:`hit` would not. Ranking on more than the label is
    sketched in ``doc/dev/FILTER_LIST_RANKING_IMPLEMENTATION.md``.
    """
    folded = name_key.nfc(text).lower()
    tier = position = 0
    for glob, regex in tokens:
        token_tier, token_pos = _best_occurrence(glob, regex, folded)
        tier = max(tier, token_tier)
        position = max(position, token_pos)
    return tier, position


def _best_occurrence(glob: str, regex: "re.Pattern | None",
                     folded: str) -> tuple[int, int]:
    """``(tier, start)`` of a token's best occurrence in ``folded`` — the
    lowercased NFC label — or ``(TIER_INSIDE, len(folded))`` when its position
    cannot be told (a hit that only the raw, un-normalized text gave)."""
    best = (TIER_INSIDE, len(folded))
    for start in _starts(glob, regex, folded):
        if start == 0:
            tier = TIER_LABEL_START
        elif not folded[start - 1].isalnum():
            tier = TIER_WORD_START
        else:
            tier = TIER_INSIDE
        best = min(best, (tier, start))
    return best


def _starts(glob: str, regex: "re.Pattern | None", folded: str):
    """Every position where the token begins a match in ``folded``: the glob
    without the "contains" stars :func:`compile_query` wrapped it in, and the
    Migemo regex's non-ASCII hits, the same ones :func:`hit` counts."""
    core = _core_regex(glob.strip('*'))
    if core is None:
        yield 0
    else:
        for start in range(len(folded)):
            if core.match(folded, start):
                yield start
    if regex is not None:
        for m in regex.finditer(folded):
            if m.end() > m.start() and not m.group().isascii():
                yield m.start()


@functools.lru_cache(maxsize=64)
def _core_regex(core: str) -> "re.Pattern | None":
    """``core`` — a token's glob without its "contains" stars — as a regex that
    matches *from* a given position, or ``None`` for an empty core (a token of
    stars alone, which matches anywhere and so starts at 0)."""
    if not core:
        return None
    # fnmatch anchors its translation at the end (``\\Z``, or ``\\z`` from
    # Python 3.14); without the anchor, ``match(text, pos)`` finds the core
    # starting at ``pos`` whatever follows it.
    pattern = fnmatch.translate(core)
    if pattern.endswith(('\\Z', '\\z')):
        pattern = pattern[:-2]
    return re.compile(pattern)


def dead_end(pattern: str, *, migemo: bool = True) -> bool:
    """Whether a query that found nothing can be called a *dead end* — no
    character typed onto it could find anything either.

    Adding to a token only ever narrows, so a query with no hits is normally
    finished: the file pane's incremental search refuses the keystroke rather
    than let the pattern run on past its last match (#370). Two kinds of "no
    hits" are not finished, and this answers ``False`` for both:

    - **A query with no tokens.** Whitespace alone matches nothing the pane
      would show, but the very next character makes it a real query.
    - **A token that can still widen** — see :func:`_undecided`.

    ``migemo=False`` says the caller's candidates hold nothing Migemo could
    match however the query grows — every one of them is ASCII, and Migemo
    counts a hit only where the matched span is not
    (:func:`migemo_search.has_hit`). That settles the short romaji tokens the
    length gate would otherwise leave open, which is why searching a directory
    of ASCII names stops at the first character that misses.
    """
    tokens = pattern.split()
    return bool(tokens) and not any(_undecided(t, migemo) for t in tokens)


def _undecided(token: str, migemo: bool = True) -> bool:
    """Whether another character typed onto ``token`` could find *more* than it
    finds now — the two places where "a query only narrows" does not hold.

    A token under Migemo's length gate is the everyday one: ``ni`` searches
    plain text while ``nih`` also finds 日本, so a half-typed romaji reading
    must survive to its third character (:func:`migemo_search.under_gate`).
    A token ending inside an unclosed ``[`` is the pedantic one: fnmatch reads
    the bracket literally until the class is closed, so ``a[`` matches names
    containing "a[" while ``a[bc]`` matches "ab".
    """
    if migemo and migemo_search.under_gate(token):
        return True
    start = token.rfind('[')
    return start != -1 and ']' not in token[start + 1:]
