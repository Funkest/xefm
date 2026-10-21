# WIDE_CHARS implementation

`WIDE_CHARS` (#611) makes chosen East Asian *Ambiguous* symbols count as two
columns, for terminal fonts that draw them full-width while the terminal
advances one column. User-facing description:
[CONFIGURATION_FEATURE.md](../CONFIGURATION_FEATURE.md#symbols-your-terminal-font-draws-full-width-advanced).

## Where the work is

The counting is PuiKit's: `puikit.text.set_wide_chars(chars)` (PuiKit 1.12).
Every width in the toolkit and in XeFM goes through `puikit.text.char_width` /
`display_width`, XeFM's `text_layout.get_display_width` included, so one
switch reaches layout, truncation, columns and text fields alike. PuiKit's
`docs/box_drawing.md` covers the rendering side:

- The VT engine blanks the second column first, then draws the glyph at its
  lead, then re-anchors the cursor. The spill lands on a space, and the order
  also holds on a terminal set to "ambiguous = wide".
- curses already places every glyph absolutely over a pre-painted run.
- The GUI backends give the glyph two cells.

XeFM's part is `config.apply_wide_chars(config)`:

- reads `WIDE_CHARS` with `getattr`. It is deliberately **not** in the
  `_config.py` template: an advanced setting a few users need, documented
  rather than spelled out in every generated `config.py`.
- accepts a string or a list of one-character strings. `validate_config`
  reports any other shape, and `apply_wide_chars` then ignores it.
- logs the characters PuiKit left alone (ASCII, already 0 or 2 columns).
- logs a warning and does nothing on a PuiKit without `set_wide_chars`. It is
  a soft dependency, so the requirements floor need not move for it.

`XeFMApp.__init__` calls it right after the config is loaded, before any
widget is built or measured. A reload does not call it again: widgets keep the
widths they measured until they lay out again, so a change applied mid-session
would show half old and half new. Like fonts and layout ratios, it takes
effect on the next launch.

## Why not "all Ambiguous characters are wide"

The frames, scrollbars, shadows and progress bars are drawn with Ambiguous
characters (box drawing, block elements). Widening the whole class would break
every one of them, which is exactly what a user sees after switching Windows
Terminal to `"compatibility.ambiguousWidth": "wide"`. A named set, chosen per
font, widens only the symbols that need it.

## Tests

`test/test_wide_chars.py`:

- string and list forms, and that nothing changes when the setting is absent
  or empty;
- skipped characters reported;
- a wrong shape reported by validation and ignored;
- the template not carrying the setting.

PuiKit's own tests cover the width counts and the VT emission order.
