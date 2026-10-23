"""Check the Japanese translations of README.md and doc/*.md (#728).

English is the source of truth; each translation sits next to its source as
``NAME.ja.md`` (doc/dev/ is not translated). ``make check-docs`` runs this and
reports:

- a source with no translation yet (a warning; ``--strict`` makes it an error
  once every page is in)
- a translation with no source, or a pair missing the "English | 日本語" line
  that is GitHub's only language switcher (written ``English \\| [日本語](…)``:
  kramdown, which builds the Pages site, reads a bare ``|`` as a table)
- a link in a translation to an English page that has a translation — it
  should point at the ``.ja.md``
- a ``#anchor`` in a translation that matches no heading of its target; the
  translated headings have Japanese anchors, so links copied from the English
  page break silently
- ``**bold**`` that will not close: a closing ``**`` or ``*`` after
  punctuation (``)``, a backtick, ``」``) must be followed by a space or
  punctuation, which Japanese text, having no spaces, often is not
- a translation whose source changed after it did (stale): by last commit, or
  by modification time for a file with uncommitted changes

The exit status is 1 when anything other than a warning was found.
doc/dev/TRANSLATION.md holds the conventions and the glossary.
"""

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: A markdown link or image target: ``[text](target)``. Targets with spaces or
#: a "title" part are not matched; the docs have none.
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")

#: An HTML link target, as the docs write them: ``<a href="target">``.
HTML_HREF = re.compile(r'<a\s[^>]*href="([^"]+)"')

#: An explicit HTML anchor a link may aim at: ``<a id="x">``, ``<a name="x">``.
HTML_ID = re.compile(r'<a\s[^>]*(?:id|name)="([^"]+)"')

FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
INLINE_CODE = re.compile(r"`+[^`]*`+")
SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")

#: A run of ``*`` emphasis delimiters.
STARS = re.compile(r"\*+")


def sources() -> list[Path]:
    """README.md and doc/*.md — the pages that get a translation."""
    pages = [REPO_ROOT / "README.md"] + sorted((REPO_ROOT / "doc").glob("*.md"))
    return [p for p in pages if not is_translation(p)]


def is_translation(path: Path) -> bool:
    return path.name.endswith(".ja.md")


def translation_of(source: Path) -> Path:
    return source.with_name(source.name[:-3] + ".ja.md")


def source_of(translation: Path) -> Path:
    return translation.with_name(translation.name[:-6] + ".md")


def prose_lines(text: str) -> list[str]:
    """The lines outside fenced code blocks."""
    lines, fenced = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            lines.append(line)
    return lines


def links(text: str) -> list[str]:
    """Every link target in the prose, inline code spans left out."""
    found = []
    for line in prose_lines(text):
        line = INLINE_CODE.sub("", line)
        found += MD_LINK.findall(line) + HTML_HREF.findall(line)
    return found


def slug(heading: str) -> str:
    """The anchor GitHub gives a heading: rendered text, lowercased, with
    everything but letters, digits, ``_``, ``-`` and spaces dropped and the
    spaces turned into hyphens. Japanese letters survive; ``「」`` do not."""
    text = re.sub(r"<[^>]+>", "", heading)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.replace("`", "").replace("*", "")
    text = re.sub(r"[^\w\- ]", "", text.lower())
    return text.replace(" ", "-")


def anchors(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    """The anchors a link into ``path`` may use, duplicates numbered as
    GitHub numbers them (``name``, ``name-1``, ...)."""
    if path not in cache:
        found, seen = set(), {}
        for line in prose_lines(path.read_text(encoding="utf-8")):
            found.update(HTML_ID.findall(line))
            m = HEADING.match(line)
            if not m:
                continue
            base = slug(m.group(2))
            n = seen.get(base, 0)
            seen[base] = n + 1
            found.add(base if n == 0 else f"{base}-{n}")
        cache[path] = found
    return cache[path]


def punctuation(ch: str) -> bool:
    """A Unicode punctuation character as CommonMark counts one (P or S)."""
    return unicodedata.category(ch)[0] in "PS"


def stuck_emphasis(line: str) -> bool:
    """Whether a ``*`` / ``**`` pair in ``line`` will render as literal stars.

    The runs of each length are taken to pair up left to right. CommonMark
    lets a run open only before a letter or after a space or punctuation, and
    close only after a letter or before a space or punctuation. Japanese has
    no spaces, so ``**[設定](x.md)**を`` stays literal where
    ``**[設定](x.md)** を`` is bold.
    """
    line = INLINE_CODE.sub("`", line)
    seen: dict[int, int] = {}
    for m in STARS.finditer(line):
        before = line[m.start() - 1] if m.start() else " "
        after = line[m.end()] if m.end() < len(line) else " "
        if before.isspace() and after.isspace():
            continue  # a bullet or a lone star, not emphasis
        n = len(m.group())
        opening = seen.get(n, 0) % 2 == 0
        seen[n] = seen.get(n, 0) + 1
        if opening:
            flanking = not after.isspace() and (
                not punctuation(after) or before.isspace() or punctuation(before))
        else:
            flanking = not before.isspace() and (
                not punctuation(before) or after.isspace() or punctuation(after))
        if not flanking:
            return True
    return False


def changed_at(path: Path) -> float:
    """When ``path`` last changed: its mtime when it has uncommitted changes,
    else its last commit's time."""
    rel = str(path.relative_to(REPO_ROOT))
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", rel],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
    if dirty.strip():
        return path.stat().st_mtime
    stamp = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", rel],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
    return float(stamp.strip() or 0)


def check(strict: bool) -> int:
    errors: list[str] = []
    warnings: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}

    def rel(path: Path) -> str:
        return str(path.relative_to(REPO_ROOT))

    translations = [REPO_ROOT / "README.ja.md"] + sorted((REPO_ROOT / "doc").glob("*.ja.md"))
    translations = [t for t in translations if t.exists()]

    for source in sources():
        if not translation_of(source).exists():
            warnings.append(f"{rel(source)}: no translation yet")

    for ja in translations:
        en = source_of(ja)
        if not en.exists():
            errors.append(f"{rel(ja)}: no English source {en.name}")
            continue
        en_text = en.read_text(encoding="utf-8")
        ja_text = ja.read_text(encoding="utf-8")

        en_line = f"English \\| [日本語]({ja.name})"
        ja_line = f"[English]({en.name}) \\| 日本語"
        if en_line not in en_text:
            errors.append(f"{rel(en)}: missing the line '{en_line}'")
        if ja_line not in ja_text:
            errors.append(f"{rel(ja)}: missing the line '{ja_line}'")

        for target in links(ja_text):
            if SCHEME.match(target):
                continue
            file_part, _, anchor = target.partition("#")
            dest = (ja.parent / file_part).resolve() if file_part else ja
            if file_part.endswith(".md") and not is_translation(dest):
                if dest != en and translation_of(dest).exists():
                    errors.append(
                        f"{rel(ja)}: links to {file_part}; use "
                        f"{translation_of(Path(file_part)).as_posix()}")
                    continue
            if anchor and dest.suffix == ".md" and dest.exists():
                if anchor not in anchors(dest, anchor_cache):
                    errors.append(f"{rel(ja)}: no heading for #{anchor} in {rel(dest)}")

        for line in prose_lines(ja_text):
            if stuck_emphasis(line):
                errors.append(f"{rel(ja)}: emphasis will not close (add a space after it): "
                              f"{line.strip()[:60]}")

        if changed_at(en) > changed_at(ja):
            errors.append(f"{rel(ja)}: stale — {en.name} changed after it")

    for line in warnings:
        print(f"{'error' if strict else 'warning'}: {line}")
    for line in errors:
        print(f"error: {line}")
    failed = bool(errors) or (strict and bool(warnings))
    print(f"{len(translations)} translated, {len(warnings)} untranslated, "
          f"{len(errors)} error(s)")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true",
                        help="treat a page with no translation as an error")
    return check(parser.parse_args().strict)


if __name__ == "__main__":
    sys.exit(main())
