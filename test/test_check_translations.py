"""tools/check_translations.py, the `make check-docs` check (#728).

The anchors and the emphasis rule are the two places the check reimplements
someone else's rendering — GitHub's heading ids and CommonMark's flanking
rules — so they are pinned here against the cases the translations hit.
"""

import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_translations as ct  # noqa: E402


class TestSlug:
    def test_english_heading(self):
        assert ct.slug("Upgrading and uninstalling") == "upgrading-and-uninstalling"

    def test_code_and_punctuation_drop_out(self):
        assert ct.slug("Why not `xefm --backend gui`?") == "why-not-xefm---backend-gui"
        assert ct.slug("Windows — the portable zip") == "windows--the-portable-zip"

    def test_japanese_letters_survive_and_brackets_go(self):
        assert ct.slug("インストール") == "インストール"
        assert ct.slug("「サーバーへ接続」の使い方（macOS）") == "サーバーへ接続の使い方macos"

    def test_link_text_is_kept(self):
        assert ct.slug("[Archives](ARCHIVE_FEATURE.md) and more") == "archives-and-more"


class TestAnchors:
    def test_duplicates_are_numbered_and_code_is_skipped(self, tmp_path):
        page = tmp_path / "page.md"
        page.write_text("# Title\n## Setup\n```\n# not a heading\n```\n## Setup\n"
                        '<a id="kept"></a>\n', encoding="utf-8")
        assert ct.anchors(page, {}) == {"title", "setup", "setup-1", "kept"}


class TestStuckEmphasis:
    def test_bold_link_straight_before_japanese_stays_literal(self):
        assert ct.stuck_emphasis("**[設定](x.md)**を参照")
        assert ct.stuck_emphasis("あ**`code`**い")

    def test_a_space_or_punctuation_after_it_closes(self):
        assert not ct.stuck_emphasis("**[設定](x.md)** を参照")
        assert not ct.stuck_emphasis("**作者の X（Twitter）**：リンク")
        assert not ct.stuck_emphasis("（**太字**）")

    def test_letters_on_both_sides_are_fine(self):
        assert not ct.stuck_emphasis("これは**太字**です")
        assert not ct.stuck_emphasis("*「保護」* と表示")

    def test_bullets_and_arithmetic_are_not_emphasis(self):
        assert not ct.stuck_emphasis("- item")
        assert not ct.stuck_emphasis("2 * 3 * 4")


def test_links_skip_code():
    text = "[a](A.md) `[b](B.md)`\n```\n[c](C.md)\n```\n<a href=\"D.md#x\">d</a>\n"
    assert ct.links(text) == ["A.md", "D.md#x"]
