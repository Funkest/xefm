# 仮想フォルダー

[English](VIRTUAL_FOLDERS_FEATURE.md) \| 日本語

> **安定版。ただし一部はプレビューです。** `PATH_SCHEMES` と、`ReadOnlyPathImpl` による仮想フォルダーの書き方は安定版の API（バージョン 1）です。5 つのメソッド、`self.key`、`self.child()`、`UriStatResult`、そして[オーバーライドしてよいもの](#オーバーライドしてよいもの)に挙げたオーバーライドがこれに当たります。組み込みスキームの置き換え、いくつかの調整用オーバーライド、書き込み可能にする方法（`UriPathImpl`）はプレビューで、まだ変わる可能性があります。

XeFM はローカルディスク、アーカイブ、S3、SSH をブラウズできます。**仮想フォルダー** を使うと、`config.py` で 5 つ目の種類を追加できます。Windows のレジストリ、ブックマークのデータベース、デバイスの一覧、REST API など、ディレクトリとファイルとして見せられるものなら何でも、ディレクトリのようにペインで開けます。カーソル、ソート、フィルター、インクリメンタルサーチ、Jump to Path もいつもどおりに使えます。

クラスを 1 つ書いて名前を付けるだけです。あとはすべてそれに従います。

```python
PATH_SCHEMES = {'notes': NotesPathImpl}
```

これで `notes://` が 1 つの場所になります。ペインで開いたり、[Jump to Path](NAVIGATION_DIALOGS_FEATURE.ja.md#jump-to-path) で移動したり、`FAVORITES` に入れたり、中に入って戻ってきたりできます。

---

## 5 つのメソッド

`ReadOnlyPathImpl` を継承し、5 つのメソッドを書きます。必要なのはそれだけです。パスの演算、親、名前、拡張子、glob、書き込みの拒否、そしてペインとステータスバーが必要とするものはすべて付いてきます。

```python
import io
from xefm.path_base import ReadOnlyPathImpl, UriStatResult

NOTES = {
    '':           ['work', 'home'],
    'work':       ['standup.md', 'roadmap.md'],
    'home':       ['shopping.md'],
}
BODIES = {
    'work/standup.md':  '- shipped the thing\n',
    'work/roadmap.md':  '# Q3\n',
    'home/shopping.md': 'milk\n',
}


class NotesPathImpl(ReadOnlyPathImpl):

    def exists(self):
        return self.key in NOTES or self.key in BODIES

    def is_dir(self):
        return self.key in NOTES

    def iterdir(self):
        for name in NOTES.get(self.key, []):
            yield self.child(name)

    def stat(self):
        return UriStatResult(size=len(BODIES.get(self.key, '')),
                             mtime=0.0, is_dir=self.is_dir())

    def open(self, mode='r', buffering=-1, encoding=None,
             errors=None, newline=None):
        return io.StringIO(BODIES.get(self.key, ''))


class Config:
    PATH_SCHEMES = {'notes': NotesPathImpl}
```

### 書く場所

**クラスと、クラスが読み込むものは、上の例のように `class Config:` より上のモジュールレベルに書きます。** クラス本体の中に書くと、*読み込み* は問題なく通り（何の警告も出ません）、その後、呼び出しのたびに失敗します。

```
Config warning: ... NameError: name 'NOTES' is not defined
```

クラス本体は、その中で定義された関数から見えるスコープではありません。Python は `NOTES` を、メソッド自身のローカル変数、次に外側の *関数*、そしてモジュールの順に探し、その間にあるクラス本体は飛ばします。`class Config:` の中に書くのは `PATH_SCHEMES = {...}` の行だけです。

| メソッド | 返すもの |
|---|---|
| `exists()` | このパスに何かがあるかどうか |
| `is_dir()` | 一覧できるかどうか |
| `iterdir()` | エントリ。`self.child(name)` として返します |
| `stat()` | サイズ、時刻、種類。`UriStatResult` で返します |
| `open(mode=…)` | 内容を読むためのファイルオブジェクト |

### `self.key`

URI のうち `notes://` より後の部分で、先頭と末尾のスラッシュは付きません。

| パス | `self.key` |
|---|---|
| `notes://` | `''` — ルート |
| `notes://work` | `'work'` |
| `notes://work/standup.md` | `'work/standup.md'` |

`self.child(name)` は現在のパスの子を作ります。URI を手で組み立てることも、親、名前、拡張子を割り出すこともありません。それは XeFM がキーから行います。

### `UriStatResult`

ファイル一覧、ソート順、詳細パネルには `UriStatResult(size=…, mtime=…, is_dir=…)` で十分です。`mtime` は Unix タイムスタンプです。時刻を持たないものなら `0.0` を渡してください。

---

## 書き込みは自動的に拒否されます

`ReadOnlyPathImpl` は、作成、名前の変更、削除、中へのコピー、`touch`、`chmod` など、あらゆる書き込みをわかりやすいメッセージとともに拒否します。また、それを前もって XeFM のほかの部分に伝えるので、実行できない操作は提示されません。理由は自分の言葉で書けます。

```python
class RegistryPathImpl(ReadOnlyPathImpl):
    READ_ONLY_MESSAGE = 'the registry is edited with regedit'
```

仮想フォルダーから *外へ* のコピーは、`open()` が動けばすぐに使えます。ファイルは、ほかのリモートファイルと同じく `open()` を通して読み込まれます。

---

## オーバーライドしてよいもの

5 つのメソッドのほかに、`ReadOnlyPathImpl` のサブクラスでは次のものを設定またはオーバーライドできます。クラスにあるそれ以外のもの（名前、親、比較、拒否の処理）は XeFM のものなので、手を加えないでください。

| メンバー | 役割 | 状態 |
|---|---|---|
| `READ_ONLY_MESSAGE` | 書き込みを拒否したときのメッセージ | 安定版 |
| `IS_REMOTE` | フォルダーがローカルディスクと同じくらい手軽に読めるなら `False` | 安定版 |
| `target()` | エントリがほかの実ファイルへの参照である場合、その実ファイル | 安定版 |
| `DISPLAY_PREFIX`、`get_display_title()` | 表示用のストレージの目印とタイトル。今はまだどこにも表示されません | プレビュー |
| `parse_uri(uri)` / `root_prefix()` | `scheme://key` より多くの情報（ホスト、バケット）を含む URI のため | プレビュー |
| `CAPABILITIES`、`SEARCH_STRATEGY` | XeFM が内容をどう読み、どう検索するか | プレビュー |
| `listdir_attrs()` | ディレクトリの一覧とそのサイズ・時刻を 1 回の呼び出しで取得 | プレビュー |
| `get_extended_metadata()` | ストレージ固有の詳細。今はまだどこにも表示されません | プレビュー |
| `forget_cached_metadata()` | フォルダーがキャッシュした内容を捨てる | プレビュー |
| `CONCURRENCY`、`READ_CONCURRENCY`、`WRITE_CONCURRENCY` | フォルダーが同時に受けられる要求の数 | プレビュー |

拡張機能がプレビューのオーバーライドを定義していると、`xefm ext check` がそれを示します。また、そのようなクラスが初めて定義されたときに、XeFM はログに 1 行を記録します。

**書き込み可能なフォルダー** は、代わりに `UriPathImpl` を継承し、書き込み操作も実装します。この方法はプレビューです。**`PathImpl` を直接継承する** ことはサポートしていません。`PathImpl` には何十もの抽象メソッドがあり、リリースのたびに新しいものが加わるので、そのようなクラスは警告付きで読み込まれ、XeFM のストレージインターフェースが拡張されるたびに壊れます。

---

## 実例：Windows のレジストリをブラウズする

これは、この機能が作られるきっかけになった用途です。レジストリをペインで見て回り、実際の編集は `regedit` に任せます。値は、その値を内容とするファイルとして、キーはディレクトリとして表示されます。

```python
# ~/.xefm/config.py
import io
import winreg

from xefm.path_base import ReadOnlyPathImpl, UriStatResult

HIVES = {
    'HKEY_CLASSES_ROOT':   winreg.HKEY_CLASSES_ROOT,
    'HKEY_CURRENT_USER':   winreg.HKEY_CURRENT_USER,
    'HKEY_LOCAL_MACHINE':  winreg.HKEY_LOCAL_MACHINE,
    'HKEY_USERS':          winreg.HKEY_USERS,
}


class RegistryPathImpl(ReadOnlyPathImpl):
    """reg://HKEY_CURRENT_USER/Software/... — keys as folders, values as files."""

    READ_ONLY_MESSAGE = 'the registry is browsed here and edited with regedit'

    def _open_key(self):
        """The open registry key for this path, or None if it is not one."""
        hive, _, subkey = self.key.partition('/')
        if hive not in HIVES:
            return None
        try:
            return winreg.OpenKey(HIVES[hive], subkey)
        except OSError:
            return None

    def _value(self):
        """This path read as a *value* under its parent key, or None."""
        parent, _, name = self.key.rpartition('/')
        hive, _, subkey = parent.partition('/')
        if hive not in HIVES:
            return None
        try:
            with winreg.OpenKey(HIVES[hive], subkey) as key:
                return winreg.QueryValueEx(key, name)[0]
        except OSError:
            return None

    # --- the five ---------------------------------------------------------

    def exists(self):
        return self.is_dir() or self._value() is not None

    def is_dir(self):
        if not self.key:
            return True                      # reg:// lists the hives
        key = self._open_key()
        if key is None:
            return False
        key.Close()
        return True

    def iterdir(self):
        if not self.key:
            for name in HIVES:
                yield self.child(name)
            return
        key = self._open_key()
        if key is None:
            return
        with key:
            n_subkeys, n_values, _ = winreg.QueryInfoKey(key)
            for i in range(n_subkeys):
                yield self.child(winreg.EnumKey(key, i))
            for i in range(n_values):
                name = winreg.EnumValue(key, i)[0]
                yield self.child(name or '(Default)')

    def stat(self):
        if self.is_dir():
            return UriStatResult(is_dir=True)
        return UriStatResult(size=len(str(self._value() or '')), is_dir=False)

    def open(self, mode='r', buffering=-1, encoding=None,
             errors=None, newline=None):
        return io.StringIO(str(self._value() or ''))


class Config:
    PATH_SCHEMES = {'reg': RegistryPathImpl}

    FAVORITES = [
        {'name': 'Registry',  'path': 'reg://'},
        {'name': 'Run keys',  'path': 'reg://HKEY_CURRENT_USER/Software/'
                                      'Microsoft/Windows/CurrentVersion/Run'},
    ]
```

これで、Jump to Path に `reg://HKEY_CURRENT_USER` と入力すると、ペインでレジストリが開きます。Enter でキーの中に入り、Backspace で戻り、**View → Filter…** で絞り込み、ビューアーで値の内容を表示できます。

キーを `regedit` に渡すには、アクションを割り当てます。[カスタマイズ](CUSTOMIZATION_FEATURE.ja.md#自分のアクションactions)を参照してください。

```python
import subprocess

def edit_in_regedit(ctx):
    entry = ctx.pane.focused
    if entry is not None and str(entry.path).startswith('reg://'):
        subprocess.Popen(['regedit', '/m'])

class Config:
    ACTIONS = {'edit-in-regedit': edit_in_regedit}
    KEY_BINDINGS = {'edit-in-regedit': ['Ctrl-E']}
```

---

## スキームの名前

`PATH_SCHEMES` のキーがスキームで、`://` を付けずに書きます。先頭は英字で、小文字の英字、数字、`+`、`-`、`.` だけを含められます。`reg`、`notes`、`ms-appx` はどれも使えますが、`Reg`、`reg://`、`1reg` は使えません。

クラスの中で繰り返し書く必要はありません。XeFM がキーから `SCHEME` を埋めます。自分で設定する場合は、登録するキーと一致していなければなりません。

`archive`、`s3`、`ssh`、`scp`、`ftp` は使用済みです。これらを置き換えることもできますが、明示的に指定する必要があります。打ち間違いで知らないうちに S3 が使えなくなることがないようにするためです。

```python
PATH_SCHEMES = {'s3': {'class': MyS3PathImpl, 'override': True}}
```

---

## うまくいかないとき

不正なエントリがあっても、失われるのはそのエントリだけで、ログペインに 1 行が記録されます。設定の残りは読み込まれます。メッセージには問題が示されます。

```
Config warning: PATH_SCHEMES['reg'] cannot be used: RegistryPathImpl does not
implement open, stat
Config warning: PATH_SCHEMES['Reg'] keys must be schemes: scheme 'Reg' must be
lowercase
Config warning: PATH_SCHEMES['s3'] would replace the built-in 's3://' backend
and was ignored — pass {'class': ..., 'override': True} if that is intended
```

メソッドの *中で* 発生した例外は、`config.py` の該当行を示すトレースバックとともに報告され、XeFM が落ちることはありません。

```
Config warning: Jump to Path 'notes://todo/' failed: NameError: name 'NOTES' is not defined
  ...
  File "/Users/you/.xefm/config.py", line 785, in exists
  NameError: name 'NOTES' is not defined
```

Jump to Path も同じメッセージをダイアログに表示するので、応答できないフォルダーは、入力したその場所でその旨を伝えます。

仮想フォルダーは設定のほかの部分と一緒に再読み込みされる（**Reload Configuration**）ので、試行錯誤は再起動なしで、編集して再読み込みするだけです。`PATH_SCHEMES` から削除したスキームは、次の再読み込みから解決されなくなります。

---

## 知っておきたいこと

**メソッドは、XeFM がディレクトリを一覧するところならどこででも実行されます。** ペインの一覧ではワーカースレッド、ちょっとした問い合わせでは UI スレッドです。ソートキーと同じように扱ってください。UI にはアクセスせず、際限なく待つこともしないでください。

**読み取り専用が安定版の方法です。** `PATH_SCHEMES` は `ReadOnlyPathImpl` を前提に設計されています。書き込み可能な仮想フォルダーを作るには、代わりに `UriPathImpl` の 9 つの書き込み操作を実装することになります。これは動作しますがプレビューです。ほかのストレージからそのようなフォルダーにコピーすると、ファイル全体がメモリに読み込まれ、進捗も表示されません。

**1 つの設定で両方のプラットフォームに。** ここにはウィジェットもバックエンドも出てこないので、仮想フォルダーはターミナルでもデスクトップのウィンドウでもまったく同じように動作します。

**このバージョンにないもの：** エントリ用の独自のアイコンや色、仮想フォルダー専用の詳細パネル、プログレスバー付きのバックグラウンド読み込み。どれも後から追加できるものです。

---

## 関連項目

- [`doc/CUSTOMIZATION_FEATURE.md`](CUSTOMIZATION_FEATURE.ja.md) — アクション、イベントフック、ソートキー、フィルターなど、同じ API のほかの部分
- [`doc/CONFIGURATION_FEATURE.md`](CONFIGURATION_FEATURE.ja.md) — `config.py` のそのほかすべて
- [`doc/dev/VIRTUAL_FOLDERS_IMPLEMENTATION.md`](dev/VIRTUAL_FOLDERS_IMPLEMENTATION.md)
- [`doc/dev/PATH_POLYMORPHISM_SYSTEM.md`](dev/PATH_POLYMORPHISM_SYSTEM.md) — その下にあるストレージ層
