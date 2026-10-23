"""Key sequences: bindings of more than one key, such as ``'g g'`` (#587).

``KEY_BINDINGS`` names a sequence as its keys separated by spaces
(``'go_home': ['g h']``), and :class:`~xefm.config.KeyBindings` parses it and
answers, for the keys pressed so far, which action they complete and whether a
longer sequence still begins with them (:meth:`KeyBindings.sequence_lookup`).
This module holds the state between those keys.

The rule when one binding is a prefix of another (``g`` alone and ``g g``)
follows ``KEY_SEQUENCE_TIMEOUT``:

- a number of seconds: the shorter one runs once that long passes with no
  further key — Vim's ``timeoutlen``;
- ``None``: no timeout; the shorter one runs only when the next key does not
  continue the sequence.

Either way, a key that continues no sequence first runs what was pending (if
it was a binding of its own) and is then handled as usual, and ``Esc`` drops
the pending keys. A prefix that is not a binding of its own never runs
anything; with no timeout it waits for the next key.

The caller feeds each key event and acts on the answer; the sequencer knows
nothing about panes or viewers, so any key-consuming surface can use one.
"""

from __future__ import annotations

from typing import Callable, Optional

#: The default for ``KEY_SEQUENCE_TIMEOUT``: Vim's ``timeoutlen``.
DEFAULT_TIMEOUT = 1.0

#: What :meth:`KeySequencer.feed` answers.
WAIT = "wait"      # the key was taken; nothing to do until the next one
ACT = "act"        # the key completed a sequence: run the action given
PASS = "pass"      # handle the key as usual, after running the action given (if any)


class KeySequencer:
    """The keys pressed so far in one context, and the timer that ends them.

    ``keys`` returns the current :class:`~xefm.config.KeyBindings` (the app
    rebuilds it when the keymap changes); ``timeout`` returns the configured
    ``KEY_SEQUENCE_TIMEOUT``. ``call_later(seconds, fn)`` schedules ``fn`` on
    the UI thread, ``on_timeout(action)`` runs what a timeout completes, and
    ``on_change()`` is told whenever the pending keys change, so a status line
    can show them.
    """

    def __init__(self, keys: Callable, context: str, *, timeout: Callable[[], Optional[float]],
                 call_later: Callable, on_timeout: Callable[[str], None],
                 on_change: Callable[[], None] = lambda: None):
        self._keys = keys
        self._context = context
        self._timeout = timeout
        self._call_later = call_later
        self._on_timeout = on_timeout
        self._on_change = on_change
        self._pending: list = []
        #: The action the pending keys complete by themselves, run if nothing
        #: longer follows.
        self._fallback: Optional[str] = None
        #: Bumped on every change, so a timer armed for older keys does nothing.
        self._generation = 0

    @property
    def pending(self) -> bool:
        return bool(self._pending)

    def pending_text(self) -> str:
        """The pending keys as a user reads them: ``g`` or ``z Shift-H``."""
        return " ".join(_label(event) for event in self._pending)

    def cancel(self) -> None:
        """Drop the pending keys without running anything — Esc, a modal
        layer opening, or the keymap changing under them."""
        if self._pending:
            self._reset()

    def feed(self, event, has_selection: bool = False) -> tuple:
        """One key event. Returns ``(WAIT, None)``, ``(ACT, action)`` or
        ``(PASS, action_or_None)``; see the module docstring."""
        if self._pending and getattr(event, "key", None) == "escape":
            self._reset()
            return WAIT, None
        keys = self._pending + [event]
        exact, longer = self._keys().sequence_lookup(keys, has_selection, self._context)
        if longer:
            self._pending = keys
            self._fallback = exact
            self._arm()
            return WAIT, None
        if not self._pending:
            # One key that begins nothing longer: the caller's usual lookup.
            return PASS, None
        if exact is not None:
            self._reset()
            return ACT, exact
        fallback = self._fallback
        self._reset()
        return PASS, fallback

    def _arm(self) -> None:
        self._generation += 1
        generation = self._generation
        self._on_change()
        seconds = self._timeout()
        if seconds is None:
            return

        def expire() -> None:
            if generation != self._generation or not self._pending:
                return
            fallback = self._fallback
            self._reset()
            if fallback is not None:
                self._on_timeout(fallback)

        self._call_later(max(0.0, float(seconds)), expire)

    def _reset(self) -> None:
        self._pending = []
        self._fallback = None
        self._generation += 1
        self._on_change()


def _label(event) -> str:
    """One key event as the status line shows it."""
    char = getattr(event, "char", None)
    mods = set(getattr(event, "modifiers", ()) or ())
    if char and char.isprintable() and not char.isspace() and not mods & {"ctrl", "alt", "cmd"}:
        return char
    name = str(getattr(event, "key", "") or "?")
    shown = [m.capitalize() if m != "cmd" else "Cmd" for m in ("ctrl", "alt", "shift", "cmd")
             if m in mods]
    return "-".join(shown + [name.capitalize() if len(name) > 1 else name.upper()])
