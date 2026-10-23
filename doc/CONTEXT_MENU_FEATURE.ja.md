# コンテキストメニュー

[English](CONTEXT_MENU_FEATURE.md) \| 日本語

ファイルリストには 2 つのコンテキストメニューがあります。1 つは**カーソル位置の項目**用、もう 1 つはペインが表示している**ディレクトリ**用です。どちらもマウスからもキーボードからも開けます。

| メニュー | キーボード | マウス |
|---|---|---|
| 項目 | `/`、または Menu キー | 行を右クリック |
| ディレクトリ | `?`（Shift-/）、または Shift + Menu キー | 最後の行より下の空白部分を右クリック |

キーボードから開くと、項目メニューはカーソル行のすぐ下に、ディレクトリメニューはペイン上部のパスバー（ディレクトリ名を表示している行）から垂れ下がる形で開きます。デスクトップアプリではシステム標準のメニューが、ターミナルでは XeFM が描画したメニューが使われます。いずれの場合も ↑/↓ と Enter で選び、Esc で閉じます。

**Menu キー**は、PC キーボードの右 Alt と Ctrl の間にあるキーです。Windows のデスクトップアプリと Windows のターミナル、そして PC キーボードをつないだ macOS で使えます。macOS や Linux のターミナルはこのキーを渡してくれないため、`/` と `?` がどこでも同じアクションを担っています。

## メニューの内容

**項目メニュー** — Open、View File、Select / Deselect、Rename…、Duplicate、Copy / Move to Other Pane、Copy to… / Move to…、Delete、Copy Name(s)、Copy Full Path(s)、Open as List、Add to Favorites…（その項目）、Show Hidden Files。Copy、Move、Delete は、それぞれのキーと同じく、選択されたファイルがあればそれらを対象にします。Select / Deselect は、次の行へ進む Space と違い、カーソルをその項目に残したままにします。

空のディレクトリには項目がないので、そこでは `/` を押すとディレクトリメニューが開きます。

**ディレクトリメニュー** — New Directory…、New File…、Add to Favorites…（このディレクトリ）、Copy Full Path、Open in Finder / Explorer、Subshell Here、Sort…、Show Hidden Files。

検索結果やインポートしたリストにはそれ自身のディレクトリがないため、ディレクトリに関する項目はグレー表示になります。Open in Finder / Explorer と Subshell Here はローカルのディレクトリが必要なので、`ssh://`、`s3://`、アーカイブの中ではグレー表示になります。

## ヘルプは F1 に移りました

以前は `?` でヘルプが開きました。現在の `?` はディレクトリメニューです（キーボードでは Shift-/、つまり項目メニューのキーに Shift を加えたもの）。ヘルプは **F1** にあります（**Help ▸ Keyboard Shortcuts…** からも開けます）。

この変更より前に書かれた設定には `'help': ['?']` と書かれたままで、そのとおりに動き続けます。自分で書いた行が新しい既定より優先されるためです。新しいキーに移るには、`'help': ['F1']` に書き換えてください。

## キーの変更

```python
KEY_BINDINGS = {
    'context_menu': ['/', 'APPS'],
    'context_menu_dir': ['?', 'Shift-APPS'],
    'help': ['F1'],
}
```

`APPS` は Menu キーの名前です。[キーバインド](KEY_BINDINGS_FEATURE.ja.md)を参照してください。
