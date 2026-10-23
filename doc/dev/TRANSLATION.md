# Translations of README and the user docs

README.md and the user docs in `doc/*.md` are also published in Japanese
(#728). English is the source of truth; a Japanese page is a translation of
it, never a page of its own with extra or different content. `doc/dev/` stays
English only.

## Files

Each translation sits next to its source with `.ja` before the extension:

```
README.md                  README.ja.md
doc/XEFM_USER_GUIDE.md     doc/XEFM_USER_GUIDE.ja.md
doc/ARCHIVE_FEATURE.md     doc/ARCHIVE_FEATURE.ja.md
doc/dev/...                (not translated)
```

Images are shared: `images/...` links are copied unchanged. The `.<lang>.md`
naming extends to another language if one is ever added.

### No front matter

GitHub renders YAML front matter as a table at the top of the file, so a
translation carries none. The Pages layout (`_layouts/default.html`) derives
the language from the path instead: a page whose source ends in `.ja.md` is
Japanese.

### The switcher line

GitHub has no language switcher of its own, so each page of a translated pair
carries one on the line after its title:

```markdown
# Archive Support

English \| [日本語](ARCHIVE_FEATURE.ja.md)
```

```markdown
# アーカイブ

[English](ARCHIVE_FEATURE.md) \| 日本語
```

The pipe is escaped because kramdown, which builds the Pages site, reads any
line with a bare `|` as a one-row table; GitHub shows `\|` as a plain `|`.
It goes *after* the `#` title, not above it: GitHub Pages takes a page's
`<title>` from a heading at the very start of the file, and a line above it
would leave the page untitled. In README.md, wrap it in
`<!-- pypi-exclude-start -->` / `<!-- pypi-exclude-end -->` so it stays off
PyPI. The Pages layout removes this line and shows its own switcher in the
header instead.

## On the Pages site

The layout, for a page that has a counterpart:

- emits `<html lang="ja">` or `lang="en"`, and `<link rel="alternate"
  hreflang>` for both pages plus `x-default` for the English one
- shows "English | 日本語" in the header, linking to the counterpart
- on the English top page only, redirects to `README.ja.html` when the
  browser's first `en`/`ja` preference in `navigator.languages` is `ja`. A
  language picked in the header switcher is saved in `localStorage`
  (`xefm-lang`) and wins over the browser's preference from then on. No other
  page redirects, so a shared link keeps its language.

A page with no translation gets none of this and stays English.

## Keeping translations current

- **Change both in one commit.** When README.md or a `doc/*.md` with a
  translation changes, update its `.ja.md` in the same commit (CLAUDE.md has
  the rule).
- **Links go to translations.** A link in a `.ja.md` points to the other page's
  `.ja.md` when that exists, and to the English page otherwise. Anchors change
  with the headings: `#installation` in English is `#インストール` in Japanese.
- **`make fix-docs`** does that for you. Translate with every link copied
  from the English page as it is; `tools/check_translations.py --fix` turns
  `X.md` into `X.ja.md` wherever the translation exists, maps each `#anchor`
  to the Japanese heading at the same position, and adds a missing switcher
  line to either page. That mapping is why a translation keeps its source's
  headings one for one — same count, same order, same levels. Run it again
  whenever a page gains its translation, so the pages already translated link
  to it.
- **`make check-docs`** (`tools/check_translations.py`) reports pages with no
  translation (a warning until every page is in — `--strict` makes it an
  error), a pair missing its switcher line, links to an English page that has
  a translation, anchors that match no heading in their target, and
  translations whose source changed after them (by last commit; uncommitted
  changes count as newer than any commit, so a pair edited together passes).

## Style

- です・ます調. Plain, direct sentences; don't add politeness the English
  doesn't have.
- A half-width space between Japanese text and Latin letters or digits
  (`XeFM の設定`, `3 つ`) except next to full-width punctuation.
- Full-width `、。（）「」`; half-width `:` and `()` inside code or Latin-only text.
- Long-vowel marks as in Microsoft's Japanese style guide: マネージャー,
  フォルダー, ユーザー, サーバー, ビューアー, フィルター; but ディレクトリ,
  メモリ, エントリ.

### Not translated

XeFM's interface is English only, so anything the reader has to find on screen
or type stays exactly as in the English page:

- key names and bindings — `Enter`, `Shift-F`, `Ctrl-SPACE`
- menu, dialog and button labels — **Tools → Edit Configuration…**, **Run anyway**
- action names, config names and values, theme names — `copy`, `KEY_BINDINGS`, **Dracula**
- code, commands, file names, paths, URLs, environment variables
- product names — XeFM, PuiKit, Spotlight, Windows Terminal
- code blocks, comments in them included — a reader copies them into
  `config.py` as they are

Where a label needs explaining, add the Japanese after it once:
**Tools → Edit Configuration…**（設定ファイルを編集）.

## Glossary

Use these renderings everywhere, so one English term reads as one Japanese
term across the docs. Add a row when a new recurring term comes up.

| English | 日本語 | Notes |
|---|---|---|
| action | アクション | the config/extension concept |
| active pane / this pane | アクティブなペイン | |
| archive | アーカイブ | |
| background job | バックグラウンドジョブ | |
| bucket (S3) | バケット | |
| clipboard | クリップボード | |
| command palette | コマンドパレット | |
| configuration, config | 設定 | `config.py` stays as is |
| content search | 内容検索 | searching inside files |
| context menu | コンテキストメニュー | |
| desktop app / desktop mode | デスクトップアプリ / デスクトップモード | |
| dialog | ダイアログ | |
| directory | ディレクトリ | keep directory vs folder as the English has it |
| dual-pane | 2 画面 | "dual-pane interface" → 2 画面表示 |
| event hook | イベントフック | |
| extension | 拡張機能 | |
| extension package | 拡張パッケージ | |
| external program | 外部プログラム | |
| favorite (directory) | お気に入り | |
| feature guide | 機能ガイド | |
| file association | ファイルの関連付け | |
| file manager | ファイルマネージャー | |
| filename search | ファイル名検索 | |
| filter | フィルター | |
| flat view | フラット表示 | |
| folder | フォルダー | |
| folder tab | フォルダータブ | |
| incremental search | インクリメンタルサーチ | |
| key binding | キーバインド | |
| keymap preset | キーマッププリセット | |
| menu bar | メニューバー | |
| other pane / opposite pane | 反対側のペイン | |
| pane | ペイン | |
| path scheme | パススキーム | `ssh://`, `s3://` |
| Preview (API status) | プレビュー | |
| quick view | クイックビュー | |
| remote | リモート | |
| select / selection | 選択 / 選択項目 | |
| server | サーバー | |
| setting | 設定項目 | one entry in `config.py` |
| skill (AI agent) | スキル | |
| AI coding agent | AI コーディングエージェント | |
| sort order | ソート順 | |
| stable (API) | 安定版 | |
| status bar | ステータスバー | |
| sub-shell | サブシェル | |
| tag (file tag) | タグ | |
| terminal app / terminal mode | ターミナルアプリ / ターミナルモード | |
| theme | テーマ | |
| trash | ゴミ箱 | |
| troubleshooting | トラブルシューティング | |
| user guide | ユーザーガイド | |
| viewer | ビューアー | |
| virtual folder | 仮想フォルダー | |
| visual effects | 視覚効果 | |
| wide characters | 全角文字 | |
