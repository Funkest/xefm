# ファイルリストのレイアウト

[English](FILE_LIST_LAYOUTS_FEATURE.md) \| 日本語

**レイアウト**は、ファイルリストの各行に何を表示するかを決めます。どの列を、どの順に並べ、各値をどう書き、文字の横にどんな小さな印を付けるかです。XeFM に付属するレイアウトは **Default** の 1 つで、名前、拡張子、サイズ、日付を並べ、名前の後ろにタグを色付きの点で表示します。`config.py` で別のレイアウトを定義できます。作業ツリー向けに Git の状態を中心にしたもの、名前とサイズだけの幅の狭いもの、日付を「3 days ago」のように表示するものなどです。

レイアウトが表示する値を**属性**と呼びます。名前、拡張子、サイズ、日付、タグ、フォルダーの合計サイズは組み込みです。`config.py` や拡張パッケージで、Git の状態や行数などの独自の属性を追加できます。

> **プレビュー。** `ATTRIBUTES`、`LAYOUTS`、`LAYOUT_RULES` は、どのリリースでもまだ変わる可能性があります。設定でこれらを使うと、XeFM はそのことをログに 1 行出します。[カスタマイズ](CUSTOMIZATION_FEATURE.ja.md)を参照してください。

## レイアウトを選ぶ

**View → Layout ▸** にすべてのレイアウトが並びます。選択はアクティブなペインの現在のタブに属します。タブはそれぞれ自分の選択を持ち、新しいタブは開いた元のタブの選択を引き継ぎ、XeFM はセッションをまたいで覚えています。`choose_layout` アクションは同じ選択をダイアログで開きます。コマンドパレットからも使えます。

すべてのタブは **Automatic** で始まります。Automatic では、開いたフォルダーごとに `config.py` の `LAYOUT_RULES` がレイアウトを選びます（後述）。手でレイアウトを選ぶと、もう一度 **Automatic** を選ぶまで、そのタブはそのレイアウトに固定されます。規則がなければ、Automatic は **Default** と同じです。

## フォルダーのサイズ

サイズの列は、フォルダーについては `<DIR>` と表示します。フォルダーにどれだけ入っているかを知るには、その下のすべてを数える必要があるためです。**View → Calculate Folder Sizes**（`calculate_folder_sizes`）はそれを数え、合計をサイズの列に表示します。

- 選択項目があれば、選択したフォルダー
- なければ、カーソル位置のフォルダー
- カーソルがファイルの上にあれば、ペイン内のすべてのフォルダー

数える処理はバックグラウンドで進み、終わったものから合計が表示されます。フォルダーを離れると止まります。合計はそのフォルダーにいる間は残ります。途中で中身が変わったフォルダーは、もう一度計算するまで `<DIR>` に戻ります。

## 列でソートする

ソートダイアログ（`sort`）は、自身のソートキーの後に、ペインのレイアウトの列のうちソートキーにないものを並べます。既定のレイアウトでは **Total size**、Git の状態を表示するレイアウトではその列です。このような列でソートすると、次のようになります。

- 並ぶのは**このフォルダーだけ**です。別のフォルダーへ移ると、ペインは前のソートに戻ります。戻ってきたら、もう一度選んでください。
- ペインがすでに持っている値を使います。値のない行（サイズを計算していないフォルダーなど）は、昇順でも降順でも最後になります。
- 自動で埋まる列は、値が届いている途中はグレー表示です。すべての行に値がそろうと選べるようになります。

**View → Reverse Sort** で、ほかのソートと同じく順序を逆にできます。ステータスバーには「(this folder)」付きで表示されます。

## 自分で定義する

**Tools → Edit Configuration…**（設定ファイルを編集）を開きます。以下の 3 つのテーブルは、ファイル内でそれぞれの上にあるコメントに、例付きで説明があります。

### `ATTRIBUTES` — エントリについて XeFM が知ることのできる値

値は 1 つの関数 `read(directory, entries)` がバックグラウンドで計算します。`entries` は 1 つのフォルダーの行、`directory` はそのフォルダーで、関数はエントリごとに 1 つの値を同じ順で返します。XeFM はフォルダー全体を一度に渡すので、`git status` のようにフォルダー全体に一度に答えられる情報源は、ファイルごとではなく 1 回だけ呼ばれます。

```python
import subprocess

def line_count(directory, entries):
    def count(entry):
        with open(entry.path, 'rb') as f:
            return sum(1 for _ in f)
    return [count(e) for e in entries]

def git_status(directory, entries):
    try:
        def git(*args):
            return subprocess.run(['git', *args], cwd=str(directory), check=True,
                                  capture_output=True, text=True).stdout
        prefix = git('rev-parse', '--show-prefix').strip()
        items = git('status', '--porcelain', '-z', '--', '.').split('\0')
    except (OSError, subprocess.CalledProcessError):
        return [None] * len(entries)        # not a Git working tree
    codes, skip = {}, False
    for item in items:
        if skip or len(item) < 4:
            skip = False
            continue
        code, path = item[:2], item[3:]
        skip = code[0] in 'RC'              # a rename's old path follows
        if path.startswith(prefix):
            # the entry here the change is in: a file, or the folder holding it
            name = path[len(prefix):].split('/')[0]
            codes.setdefault(name, code.strip()[:1])
    return [codes.get(e.path.name) for e in entries]

class Config:
    ATTRIBUTES = {
        'lines': {'label': 'Lines', 'type': 'count', 'read': line_count},
        'git': {
            'label': 'Git status', 'type': 'enum', 'read': git_status,
            'values': {
                'M': {'label': 'Modified',  'color': 'yellow'},
                'A': {'label': 'Added',     'color': 'green'},
                '?': {'label': 'Untracked', 'color': 'muted'},
            },
        },
    }
```

| キー | 意味 |
|---|---|
| `read` | 関数 `read(directory, entries)`。`entries` と同じ順で、エントリごとに 1 つの値を返します。 |
| `label` | ソートダイアログに表示する名前。 |
| `type` | `text`、`count`、`size`（バイト数）、`time`（タイムスタンプ）、`enum`（`values` のどれか）、`tags`。値の書き方とソートのしかたが決まります。 |
| `values` | `enum` の場合の、各値の意味と表示色。 |
| `where` | 問い合わせるストレージ：`local`（既定）、`archive`、`ssh`、`s3`。ファイルごとの呼び出しは、ディスクなら軽く、S3 では 1 件ごとにリクエストになります。 |
| `compute` | `auto`（既定）または `on_request`。 |

属性を定義しただけでは、どこにも表示されません。表示するのはレイアウトです。画面上のレイアウトが属性を表示すると、その値は**フォルダーのすべての行**についてバックグラウンドで計算されます。そのため、定義はフォルダー 1 つ分にすぐ答えられるものにしてください。それができないもの（たとえば、すべてのファイルを丸ごと読むもの）は `'compute': 'on_request'` とします。その場合は、頼んだときだけ計算されます。**View → Compute Values**（`compute_values`）で、選択項目またはカーソル位置の項目について計算します。このときは 1 回の呼び出しに 1 エントリずつ渡すので、値は 1 つずつ表示され、フォルダーを離れると止まります。

値は届くまで空欄です。関数が失敗したり、長さの違うリストを返したりしても、失われるのはその呼び出しの値だけで、そのことをログペインに 1 回だけ出します。

自分の関数（ソートキー、フィルター、アクション）からは、XeFM がすでに持っている値を `entry.attr('git')` で読めます。値を計算することも待つこともありません。値が届くまでは `None` です。

### `LAYOUTS` — 行の描き方

```python
from xefm.user_api import Cell

GIT_MARK = {'M': Cell('●', color='yellow'),
            'A': Cell('+', color='green'),
            '?': Cell('?', color='muted')}

def git_mark(value, entry):
    return GIT_MARK.get(value, '')

class Config:
    LAYOUTS = {
        'git': {
            'label': 'Git',
            'columns': [
                {'attr': 'name', 'markers': [
                    'tags',
                    {'attr': 'git', 'format': git_mark, 'side': 'before',
                     'max_width': 1},
                ]},
                'ext',
                'size',
                {'attr': 'mtime', 'format': 'relative', 'priority': 1},
            ],
        },
        'compact': {'label': 'Name and size', 'columns': ['name', 'size']},
    }
```

列は属性の名前か、次のキーを持つ辞書で書きます。

| キー | 意味 |
|---|---|
| `attr` | 表示する属性。 |
| `format` | 書き方。書式の名前（後述）か、自分の関数。 |
| `width` | 幅（文字数）。各書式に既定の幅があります。 |
| `align` | `left` または `right`。数値と日付は右寄せです。 |
| `priority` | ペインの幅が足りないとき、優先度を持つ列が低いものから外れます。優先度のない列は残ります。 |
| `markers` | この列の文字の横に描く小さな印（後述）。 |

どのレイアウトにも `name` 列があり、ほかの列が残した幅を使います。`ext` を書かなければ、拡張子は名前の一部として表示されます。組み込みの `name`、`ext`、`size`、`mtime`、`tags`、`total_size`（ファイルのサイズ、またはフォルダーの計算済みの合計）は、どのレイアウトでも使えます。

**書式**

| 型 | 書式（最初のものが既定） |
|---|---|
| `size` | `compact`（`12.3K`）、`bytes`（`12,345`） |
| `time` | `short`、`full`（既定ではこの 2 つを `DATE_FORMAT` が選びます）、`iso`、`relative`（`5 min ago`）、`recent`（今日なら `13:24`、今年なら `10/21`、それより前は `2024`） |
| `enum` | `letter`（値そのもの）、`word`（`values` のラベル）。どちらもその値の色で表示 |
| `tags` | `dots`、`names` |
| `count` | `number` |
| `text` | `text` |

自分の関数は `(value, entry)` を受け取り、文字列を返します。色を付けるときは `Cell` を、複数ならそのリストを返します。値の計算中は `value` が `None` です。`Cell` の `color` には `'muted'`、`'accent'`、`'accent2'`、`'text'`、色の名前（`'red'`、`'green'`、`'yellow'`、`'blue'`、`'purple'`、`'orange'`、`'gray'`）、`(r, g, b)` のどれかを指定します。`bold` や `italic` も指定できます。選択、カーソル、非アクティブなペインの減光はこの上にかかるので、色の指定で行が読めなくなることはありません。

**マーカー**は、属している列の文字の横に描く印です。タグの点が名前の後ろにあるのと同じです。属性の名前か、`attr`、`format`、`side`（`'after'` が既定、または `'before'`）、`max_width`（指定しなければ 3 文字分）を持つ辞書で書きます。表示するものがない行では、マーカーは場所を取りません。名前の列では、マーカーが使う分だけ名前が短くなります。それ以外の列では、値がそろって並ぶよう、マーカーの場所をすべての行で空けておきます。

**既定のレイアウトを置き換える。** レイアウトに `'default'` という名前を付けると組み込みのものを置き換えます。打ち間違いで置き換わらないよう、`'override': True` が必要です。

### `LAYOUT_RULES` — フォルダーに使うレイアウト

`(条件, レイアウト)` の組のリストです。上から順に読み、最初に当てはまったものが **Automatic** のタブで使われます。条件はパスのパターンか、フォルダーのパスを受け取る関数です。関数はバックグラウンドスレッドで動くので、ディスクを見ても構いません。

```python
def in_git_tree(path):
    return any((p / '.git').exists() for p in (path, *path.parents))

class Config:
    LAYOUT_RULES = [
        ('s3://*', 'compact'),
        (in_git_tree, 'git'),
    ]
```

### 拡張パッケージから

拡張パッケージは属性とレイアウトを提供できます（`[contributes.attributes]`、`[contributes.layouts]`。[拡張パッケージ](EXTENSIONS_FEATURE.ja.md)を参照）。規則は提供できません。フォルダーにどのレイアウトを使うかはユーザーが決めることなので、拡張パッケージを入れてもフォルダーの見た目が勝手に変わることはありません。

## 関連項目

- [ソートダイアログ](SORT_DIALOG_FEATURE.ja.md)
- [ファイルのタグ](FILE_TAGS_FEATURE.ja.md)
- [カスタマイズ](CUSTOMIZATION_FEATURE.ja.md)
- [メニューバー](MENU_BAR_FEATURE.ja.md)
