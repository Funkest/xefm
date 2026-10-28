# ゴミ箱への削除

[English](TRASH_FEATURE.md) \| 日本語

**File → Move to Trash…**（`delete_files`、`Delete` キーでも実行できます）はファイルをシステムの**ゴミ箱**（Windows ではごみ箱）へ移動するので、誤って削除しても元に戻せます。ほかの場所で削除したファイルと同じように、Finder（*戻す*）、ごみ箱、またはデスクトップのゴミ箱から復元してください。

| アクション | メニュー | 動作 |
|---|---|---|
| `delete_files` | **File → Move to Trash…**（Windows では **Move to Recycle Bin…**） | 選択項目（またはカーソル位置の項目）をゴミ箱へ移動 |
| `delete_permanently` | **File → Delete Permanently…** | ゴミ箱を使わずに完全に削除 |

`Delete` と `Shift-Delete` はどのプリセットでもこの 2 つを実行します。それ以外のキーはキーマッププリセットによって異なります。[キーマッププリセット](KEYMAP_PRESETS_FEATURE.ja.md#すべてのキーの一覧)を参照してください。何もマークしていないとき、メニューのコマンドと、AFX style 以外のプリセットのキーはカーソル位置の項目に対して動作します。AFX style では、`Delete` と `Shift-Delete` を含めてキーはマークした項目があるときだけ働きます。何もマークしていなければ何も起きないので、先に項目をマークするか、メニューを使ってください。

どちらも先に確認を求めます。ゴミ箱への移動は元に戻せるので、その確認ダイアログの既定のボタンは *Move to Trash* です。完全な削除の既定は *Cancel* です。**File** メニューと右クリックメニューの両方に、どちらのコマンドもあります。

## ゴミ箱がない場所

ゴミ箱がない場所もあります。

- SSH や S3 上のファイル
- アーカイブ内のファイル
- Windows では、USB ドライブやネットワークドライブ（Windows 自身も完全に削除する場所）

そうした場所では `delete_files` は完全に削除し、何かが起こる前に、確認ダイアログで *There is no Trash here, so these are deleted for good*（ここにはゴミ箱がないので、完全に削除されます）と示されます。

macOS では、クラウドストレージのフォルダー（OneDrive、Google Drive、Dropbox など）が、ファイルをオンラインだけに置き、開いたときにダウンロードすることがあります。サービスによっては、そうしたファイルをゴミ箱に入れられず、Finder も代わりに完全な削除を提案します。XeFM も同じで、まずゴミ箱を試し、オンラインだけのファイルが入らなかったときは、完全に削除するかどうかを尋ねます。元に戻せるようにしたいときは、先にファイルをダウンロードしてから、もう一度削除してください。サービスが削除したファイルを、オンラインの独自のごみ箱に残していることもあります。

## どのゴミ箱か

| システム | 削除したファイルの行き先 |
|---|---|
| macOS | Finder から削除したときと同じゴミ箱。ドライブごとに専用のゴミ箱があり、*戻す* で元の場所に戻せます。 |
| Windows | 固定（内蔵）ドライブのごみ箱 |
| Linux とそのほかの Unix デスクトップ | デスクトップのゴミ箱（`~/.local/share/Trash`、またはほかのドライブの最上位にある `.Trash` フォルダー）。GNOME Files、Dolphin、`gio trash` のいずれからも読めます |

フォルダーは丸ごと 1 つの項目としてゴミ箱に入ります。

## 設定

```python
CONFIRM_TRASH = True     # ask before moving to the Trash
CONFIRM_DELETE = True    # ask before deleting for good
DELETE_TO_TRASH = True   # False: delete_files deletes for good, like delete_permanently
```
