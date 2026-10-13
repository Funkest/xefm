"""Directory sync plans — what applying a directory diff in bulk would do.

The directory diff viewer compares two trees and lets the user reconcile them
one node at a time. A *sync plan* is the bulk step (#560): from the finished
comparison and a mode, every node that differs gets an action, the user may
change any of them, and the result is a list of copies and deletions for
:meth:`xefm.file_operations.FileOperationService.sync` to run.

Two modes, both one-way from the *source* side (the viewer's active side) to
the *target*:

========  =================================  ==========================
Mode      New and changed files              Extra on the target
========  =================================  ==========================
Update    copied source → target             kept
Mirror    copied source → target             deleted
========  =================================  ==========================

Every node's action is a default the user can cycle (:meth:`SyncPlan.cycle`):
a file can be skipped, sent the other way, or — for one only on the target —
deleted in Update too. A file whose target copy is **newer** defaults to skip:
the plan would otherwise replace newer work with older. A name that is a file
on one side and a directory on the other is always skipped; neither may be
copied over the other.

Storage-agnostic and free of UI: it reads the viewer's :class:`TreeNode` s and
returns paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional

from xefm.file_operations import compare_mtimes

UPDATE = "update"
MIRROR = "mirror"

#: Copy source → target.
COPY = "copy"
#: Copy target → source: the odd file the user sends back the other way.
BACK = "back"
#: Delete on the target.
DELETE = "delete"
#: Leave alone.
SKIP = "skip"
#: A directory present on both sides: its own action is "decide each node
#: below" — the only other choice for it is skipping the whole subtree.
DESCEND = "descend"

MODE_LABELS = {UPDATE: "Update", MIRROR: "Mirror"}

# The verdict names, as directory_diff_viewer.DifferenceType values — compared
# by value so this module does not import the widget.
_IDENTICAL = "identical"
_DIFFERENT = "content_different"
_PENDING = "pending"


@dataclass
class Operations:
    """What a plan comes to. ``copies`` are ``(source, destination,
    overwrite)``; ``deletes`` are paths on the target. The counts are for the
    confirmation, by what the user would want to know before saying yes."""
    copies: list = field(default_factory=list)
    deletes: list = field(default_factory=list)
    new: int = 0            # copied to where nothing was
    replaced: int = 0       # copied over an existing file
    back: int = 0           # sent target → source
    skipped: int = 0        # differing, and left alone
    newer_kept: int = 0     # of skipped: the target was newer
    mismatched: int = 0     # a file on one side, a directory on the other

    @property
    def empty(self) -> bool:
        return not self.copies and not self.deletes


class SyncPlan:
    """A mode, a direction, and the user's changes to the defaults.

    ``source`` is ``"left"`` or ``"right"``. Changes are kept by the node's
    path relative to the compared roots, not by the node, so they survive the
    rescan that follows a per-file merge or copy made while the plan is open.
    """

    def __init__(self, mode: str, source: str, left_root, right_root):
        self.mode = mode
        self.source = source
        self.left_root = left_root
        self.right_root = right_root
        self.overrides: dict[str, str] = {}

    # --- sides ---------------------------------------------------------------

    @property
    def target(self) -> str:
        return "right" if self.source == "left" else "left"

    def _src(self, node):
        return node.left_path if self.source == "left" else node.right_path

    def _tgt(self, node):
        return node.right_path if self.source == "left" else node.left_path

    def _src_mtime(self, node):
        return node.left_mtime if self.source == "left" else node.right_mtime

    def _tgt_mtime(self, node):
        return node.right_mtime if self.source == "left" else node.left_mtime

    def target_newer(self, node) -> bool:
        """The target's copy of a differing file is clearly newer — by the same
        rule "Overwrite older" and the viewer's details line use."""
        return compare_mtimes(self._src_mtime(node), self._tgt_mtime(node)) < 0

    # --- actions -------------------------------------------------------------

    def choices(self, node) -> list:
        """The actions ``node`` can take, its default first. Empty for a node
        with nothing to do: identical, or not compared yet."""
        src, tgt = self._src(node), self._tgt(node)
        if node.type_mismatch:
            return [SKIP]
        if src is not None and tgt is None:
            return [COPY, SKIP]
        if tgt is not None and src is None:
            return ([DELETE, SKIP, BACK] if self.mode == MIRROR
                    else [SKIP, BACK, DELETE])
        verdict = _verdict(node)
        if node.is_directory:
            return [] if verdict == _IDENTICAL else [DESCEND, SKIP]
        if verdict != _DIFFERENT:
            return []
        if self.target_newer(node):
            return [SKIP, COPY, BACK]
        return [COPY, SKIP, BACK]

    def own_action(self, node) -> Optional[str]:
        """``node``'s action ignoring its ancestors: the user's choice if it is
        still one of the node's choices, else the default."""
        choices = self.choices(node)
        if not choices:
            return None
        chosen = self.overrides.get(_rel_path(node))
        return chosen if chosen in choices else choices[0]

    def action(self, node) -> Optional[str]:
        """What will happen to ``node``: skipped when a directory above it is
        skipped, else its own action."""
        cur = node.parent
        while cur is not None and cur.depth > 0:
            if self.own_action(cur) == SKIP:
                return SKIP if self.choices(node) else None
            cur = cur.parent
        return self.own_action(node)

    def cycle(self, node) -> Optional[str]:
        """Move ``node`` to its next action and return it. Back at the default,
        the override is dropped rather than stored."""
        choices = self.choices(node)
        if len(choices) < 2:
            return self.own_action(node)
        current = self.own_action(node)
        nxt = choices[(choices.index(current) + 1) % len(choices)]
        key = _rel_path(node)
        if nxt == choices[0]:
            self.overrides.pop(key, None)
        else:
            self.overrides[key] = nxt
        return nxt

    def is_default(self, node) -> bool:
        return _rel_path(node) not in self.overrides

    # --- operations ----------------------------------------------------------

    def operations(self, root) -> Operations:
        """Walk the tree under ``root`` and turn every action into a copy or a
        deletion. A node on one side only is taken whole — a directory copied
        or deleted as one target — so nothing below it is visited; a directory
        on both sides is descended unless skipped."""
        ops = Operations()
        for node in self._walk(root):
            act = self.own_action(node)
            if act is None or act == DESCEND:
                continue
            if node.type_mismatch:
                ops.mismatched += 1
                continue
            if act == SKIP:
                ops.skipped += 1
                if self._src(node) is not None and self._tgt(node) is not None \
                        and self.target_newer(node):
                    ops.newer_kept += 1
                continue
            if act == DELETE:
                ops.deletes.append(self._tgt(node))
                continue
            if act == COPY:
                src, dst = self._src(node), self._tgt(node)
                dest = dst if dst is not None else \
                    self._dest_dir(node, self.target) / node.name
                ops.copies.append((src, dest, dst is not None))
                if dst is not None:
                    ops.replaced += 1
                else:
                    ops.new += 1
            elif act == BACK:
                src, dst = self._tgt(node), self._src(node)
                dest = dst if dst is not None else \
                    self._dest_dir(node, self.source) / node.name
                ops.copies.append((src, dest, dst is not None))
                ops.back += 1
        return ops

    def _walk(self, node) -> Iterator:
        """Every node whose action counts: a skipped two-sided directory stops
        the walk below it (and counts once, as itself); a one-sided node is
        not descended."""
        for child in node.children:
            yield child
            if self.own_action(child) == DESCEND:
                yield from self._walk(child)

    def _dest_dir(self, node, side: str):
        """The directory on ``side`` that mirrors ``node``'s parent. The parent
        is the root or a directory on both sides — a node is only reached
        through those (see :meth:`_walk`)."""
        parent = node.parent
        if parent is None or parent.depth == 0:
            return self.left_root if side == "left" else self.right_root
        return parent.left_path if side == "left" else parent.right_path

    # --- display -------------------------------------------------------------

    def glyph(self, node) -> Optional[str]:
        """The verdict gutter's text for ``node`` while the plan is open — an
        arrow pointing the way the copy goes — or None to keep the verdict."""
        act = self.action(node)
        if act is None or act == DESCEND:
            return None
        to_right = " → ", " ← "
        if act == COPY:
            return to_right[0] if self.source == "left" else to_right[1]
        if act == BACK:
            return to_right[1] if self.source == "left" else to_right[0]
        if act == DELETE:
            return " × "
        return " · "


def _verdict(node) -> str:
    return getattr(node.difference_type, "value", node.difference_type)


def _rel_path(node) -> str:
    parts: list[str] = []
    cur = node
    while cur is not None and cur.depth > 0:
        parts.append(cur.name)
        cur = cur.parent
    return "/".join(reversed(parts))


def is_settled(root) -> bool:
    """Every node compared — no verdict still pending. A plan made earlier
    would miss differences the comparison has not reached yet."""
    stack = list(root.children)
    while stack:
        node = stack.pop()
        if _verdict(node) == _PENDING:
            return False
        stack.extend(node.children)
    return True
