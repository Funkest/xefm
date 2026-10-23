# SFTP 対応 機能ガイド

[English](SFTP_SUPPORT_FEATURE.md) \| 日本語

## 概要

XeFM はシームレスな SFTP（SSH File Transfer Protocol）対応を備えていて、リモートサーバー上のファイルを、ローカルのディレクトリのようにブラウズ、検索、管理できます。XeFM はサーバーごとに 1 つの SSH 接続を開いて、すべての操作をその上で実行し、標準的なファイル操作をすべてサポートします。

## クイックスタート

### 前提条件

1. リモートサーバーへの **SSH アクセス**
2. `~/.ssh/config` の **SSH の設定**（省略可能ですが推奨）
3. パスワードなしで認証するための **SSH 鍵**（省略可能）
4. **`ssh` コマンド** — OpenSSH クライアントです。macOS と Linux には入っています。Windows では、Windows に組み込まれた OpenSSH クライアントが使えるほか、`PATH` にあるほかのクライアント（Git for Windows、MSYS2、Cygwin）も使えます。

### 基本的な使い方

標準的な SSH の URL 形式で SFTP の場所に移動します。

```
ssh://hostname/path/to/directory
ssh://user@hostname/path/to/directory
ssh://hostname:port/path/to/directory
```

**例：**
```
ssh://myserver/home/user/projects
ssh://admin@192.168.1.100/var/log
ssh://server.example.com:2222/opt/data
```

### すばやくアクセスする方法

**方法 1：Jump to Path ダイアログ**
1. **Jump to Path**（`jump_to_path`）を開きます
2. `ssh://hostname/path` を入力します
3. Enter を押します

**方法 2：お気に入り**
1. 設定ファイル `~/.xefm/config.py` で、SFTP のパスをお気に入りに追加します
2. `J` を押してお気に入りを開きます
3. SFTP のブックマークを選びます

**方法 3：コマンドライン**
```bash
python3 -m xefm --left ssh://server/path --right ~/local/path
```

## SSH の設定

### 推奨する設定

接続を簡単にするために、`~/.ssh/config` を作成または編集します。

```ssh-config
Host myserver
    HostName server.example.com
    User myusername
    Port 22
    IdentityFile ~/.ssh/id_rsa
    
Host devbox
    HostName 192.168.1.100
    User developer
    Port 2222
    
Host prod-*
    User admin
    IdentityFile ~/.ssh/prod_key
    StrictHostKeyChecking yes
```

**利点：**
- 詳細をすべて書く代わりに、`ssh://myserver/path` のような短い名前を使えます
- 認証の設定を 1 か所にまとめられます
- すべての SSH ツールで設定が一貫します

### SSH 鍵による認証

**SSH 鍵を生成する**（まだ持っていない場合）：
```bash
ssh-gen -t rsa -b 4096 -C "your_email@example.com"
```

**鍵をサーバーにコピーする：**
```bash
ssh-copy-id user@hostname
```

**接続をテストする：**
```bash
ssh user@hostname
```

SSH 鍵による認証が動作すれば、XeFM は自動的にそれを使います。

## 機能

### ファイル操作

標準的なファイル操作は、すべて SFTP のパスで動作します。

- **コピー**（`C`）：ローカルとリモートの間でファイル／ディレクトリをコピーします
- **移動**（`M`）：リモートサーバー上でファイル／ディレクトリを移動します
- **削除**（`K`）：リモートのファイル／ディレクトリを削除します
- **リネーム**（`R`）：リモートのファイル／ディレクトリをリネームします
- **ディレクトリの作成**（何も選択していないときの `M`）：リモートサーバー上にディレクトリを作成します
- **ファイルの表示**（`V`）：リモートのテキストファイルをシンタックスハイライト付きで表示します

### ストレージをまたいだ操作

XeFM は、異なる種類のストレージの間の操作をシームレスに扱います。

**ローカル ↔ SFTP：**
```
Copy: ~/local/file → ssh://server/remote/path
Move: ssh://server/data → ~/backup/
```

**SFTP ↔ S3：**
```
Copy: ssh://server/logs → s3://bucket/archive/
Move: s3://bucket/data → ssh://server/processing/
```

**SFTP ↔ アーカイブ：**
```
Copy: ssh://server/file.txt → local-archive.zip
Extract: ssh://server/archive.tar.gz → ~/extracted/
```

### 検索機能

**ファイル名検索**（`find_files`）：
- 名前のパターンでファイルを検索します
- ワイルドカードが使えます：`*.py`、`test_*.txt`
- 検索の進行に合わせて結果がリアルタイムに表示されます
- ディレクトリを再帰的にたどります

**内容検索**（`G`）：
- 正規表現のパターンでファイルの内容を検索します
- テキストファイルを自動的に判別します
- マッチした行を前後の文脈とともに表示します
- 大きなファイルも効率的にストリーミングで処理します

**検索の例：**
```
*.log          # Find all log files
config.*       # Find config files with any extension
test_.*\.py    # Find Python test files
```

### 性能の最適化

XeFM には、SFTP の操作のための最適化がいくつか入っています。

1. **サーバーごとに 1 つの接続**
   - ログインは一度だけで、その後の一覧、コピー、リネームはすべてその接続を再利用します
   - 接続が切れた場合は、次に使うときに開き直されます

2. **ディレクトリの一覧を 1 往復で取得**
   - 一覧と一緒に、すべてのファイルのサイズ、日時、種類が返ってきます
   - 転送では多数のリクエストを同時に送り続けるので、遠い回線でも途切れなく使えます

3. **賢いキャッシュ**
   - ディレクトリの一覧とファイルのメタデータをキャッシュします
   - TTL を設定できます（既定：30 秒）
   - 変更があると自動的にキャッシュを無効にします

4. **最適化された検索**
   - メモリ効率のためにファイルの内容をストリーミングで処理します
   - 可能な場合は並行して処理します
   - 操作はキャンセルできます

### テキストビューアー

リモートのテキストファイルを、完全なシンタックスハイライト付きで表示できます。

1. SFTP 上のテキストファイルに移動します
2. `Enter` または `V` を押してビューアーを開きます
3. 矢印キーでスクロールします
4. `/` を押してファイル内を検索します
5. `q` を押してビューアーを閉じます

**対応する形式：** Python、JavaScript、JSON、YAML、Markdown、シェルスクリプトのほか、`pygments` がインストールされていれば 20 種類以上。

## 設定

### SFTP 固有の設定項目

`~/.xefm/config.py` に追加します。

```python
# SFTP cache TTL for successful results (seconds)
SSH_CACHE_TTL = 30

# SFTP cache TTL for cached errors (seconds)
SSH_CACHE_ERROR_TTL = 300
```

### SFTP のお気に入りのディレクトリ

よく使う SFTP のパスをお気に入りに追加します。

```python
FAVORITES = [
    {'name': 'Local Projects', 'path': '~/projects'},
    {'name': 'Dev Server', 'path': 'ssh://devbox/var/www'},
    {'name': 'Production Logs', 'path': 'ssh://prod-web1/var/log/nginx'},
    {'name': 'Backup Server', 'path': 'ssh://backup/mnt/backups'},
    {'name': 'S3 Bucket', 'path': 's3://my-bucket/data'},
]
```

`j` キーで開きます。リストは設定だけから作られるので、どれかを選ぶまで、これらのどこにも接続は開かれません。

## 高度な使い方

### サーバーごとに 1 つの接続

XeFM はサーバーごとに 1 つの `ssh`（`sftp` コマンドが実行するのと同じ `ssh <server> -s sftp`）を実行し、すべての操作をその上で送ります。SSH の接続共有（`ControlMaster`）には依存しないので、Windows に組み込まれた OpenSSH でも動作します。`~/.ssh/config` にあるそのホストの設定（`HostName`、`User`、`ProxyJump`、`ProxyCommand`、鍵）は、`ssh` そのものと同じように適用されます。そこで設定したポートフォワーディングは、XeFM の接続では使われません。

### 一括操作

複数のファイルを選択して、一括で操作できます。

1. `Space` でファイルを選択します
2. `A` でディレクトリ内のすべてのファイルを選択します
3. 操作のキー（コピーは `C`、削除は `K` など）を押します
4. 操作を確認します
5. 完了まで進捗バーを見守ります

進捗バーは、どちらの方向でも実際にバイトが転送されるのに合わせて進むので、遅延の大きい回線での遅い転送が 0% で止まっているように見えることはもうありません。**ESC** を押すとキャンセルできます。転送はバックグラウンドで最後まで続くことなく 0.5 秒ほどで止まり、途中まで転送したファイルは削除されます。

**例：複数のディレクトリをバックアップする**
```
1. Navigate to ssh://server/data
2. Select directories with Space
3. Press C (Copy)
4. Navigate to ~/backup
5. Press Enter to confirm
```

### SFTP でのサブシェル

`subshell` を実行すると、SFTP の環境変数が設定されたサブシェルモードに入ります。

```bash
# Environment variables available:
echo $XEFM_LEFT_DIR    # May be ssh://server/path
echo $XEFM_RIGHT_DIR   # May be local path
echo $XEFM_THIS_DIR    # Current pane (SFTP or local)

# Use with standard tools:
scp $XEFM_THIS_DIR/file.txt user@other:/path/
rsync -av $XEFM_THIS_DIR/ backup/
```

`exit` と入力すると XeFM に戻ります。

## トラブルシューティング

### 接続の問題

**問題：「Connection refused」または「Connection timeout」**

解決方法：
1. SSH でアクセスできるか確認します：`ssh user@hostname`
2. サーバーのファイアウォールの設定を確認します
3. ポートが正しいか確認します（既定：22）
4. サーバーで SSH サービスが動いているか確認します

**問題：「Permission denied (publickey)」**

解決方法：
1. SSH 鍵が追加されているか確認します：`ssh-add -l`
2. 鍵をサーバーにコピーします：`ssh-copy-id user@hostname`
3. SSH の設定の IdentityFile が正しいか確認します
4. まずパスワード認証を試します

**問題：「Host key verification failed」**

解決方法：
1. ホスト鍵を手動で受け入れます：`ssh user@hostname`
2. または古い鍵を削除します：`ssh-keygen -R hostname`
3. `~/.ssh/known_hosts` を更新します

### 性能の問題

**問題：ディレクトリの一覧が遅い**

解決方法：
1. ネットワークの遅延を確認します：`ping hostname`
2. 設定でキャッシュの TTL を長くします
3. SSH の圧縮を使います。`~/.ssh/config` に追加します：
   ```
   Compression yes
   CompressionLevel 6
   ```

**問題：検索が遅い**

解決方法：
1. 可能な場合は、内容検索の代わりにファイル名検索を使います
2. 検索の範囲を特定のディレクトリに絞ります
3. より具体的なパターンを使って結果を減らします
4. ネットワークの帯域幅を確認します

### キャッシュの問題

**問題：ディレクトリの一覧が更新されない**

解決方法：
1. ディレクトリから一度出て入り直し、一覧を取り直します
2. 設定で SSH_CACHE_TTL を短くします
3. XeFM を再起動して、すべてのキャッシュをクリアします

**問題：削除したファイルが表示されたままになる**

解決方法：
- ディレクトリから一度出て入り直し、一覧を取り直します
- TTL が切れると、キャッシュは自動的に無効になります

## ベストプラクティス

### セキュリティ

1. パスワードの代わりに **SSH 鍵を使います**
2. **鍵のアクセス権を制限します：** `chmod 600 ~/.ssh/id_rsa`
3. サーバーごとに**別の鍵を使います**
4. SSH の設定で **StrictHostKeyChecking を有効にします**
5. SSH 鍵を**定期的に更新します**

### 性能

1. 接続の設定には **SSH の設定ファイルを使います**
2. 遅い接続では**圧縮を有効にします**
3. **キャッシュの TTL は適度な長さにします**（30 ～ 60 秒）
4. 内容検索が必要ないときは**ファイル名検索を使います**
5. ファイルを 1 つずつ操作する代わりに **一括操作を使います**

### 作業の流れ

1. よくアクセスするサーバーは**お気に入りに追加します**
2. SSH の設定で**短いホスト名を使います**
3. 転送しやすいように **ローカルとリモートのペインを並べておきます**
4. ファイルをすばやく見つけるには**検索を使います**
5. 大きな操作では**進捗を確認します**

## 制限

### 現在の制限

1. **SFTP 上のアーカイブは読み取り専用：** リモートのアーカイブの中のファイルは変更できません
2. **シンボリックリンクは作成できない：** シンボリックリンクは読めますが、作成はできません
3. **アクセス権は変更できない：** ファイルに chmod はできません（サブシェルモードを使ってください）
4. **所有者は変更できない：** ファイルに chown はできません（サブシェルモードを使ってください）

### 回避策

**アクセス権を変更するには：**
```bash
# Press X to enter sub-shell
chmod 755 $XEFM_THIS_DIR/script.sh
exit
```

**高度な操作には：**
```bash
# Use sub-shell with standard tools
rsync -av --progress $XEFM_THIS_DIR/ backup/
tar czf archive.tar.gz $XEFM_THIS_DIR/*
```

## 例

### 例 1：Web サイトをデプロイする

```
1. Left pane: ~/projects/website (local)
2. Right pane: ssh://webserver/var/www/html
3. Select the updated files in the left pane
4. Copy them across (`copy_files`)
5. Confirm overwrite
6. Watch progress bar
```

### 例 2：ログをダウンロードする

```
1. Left pane: ssh://server/var/log
2. Right pane: ~/logs/backup
3. Search for logs (`find_files`), pattern: *.log
4. Select every file in the results (`toggle_select_files`)
5. Copy them across (`copy_files`)
6. Files copied to local backup
```

### 例 3：古いファイルを整理する

```
1. Navigate to: ssh://server/tmp
2. Search for old files (`find_files`), pattern: *.tmp
3. Review results
4. Select the files to delete
5. Delete them (`delete_files`)
6. Confirm deletion
```

### 例 4：ディレクトリを比較する

```
1. Left pane: ~/local/config
2. Right pane: ssh://server/etc/app
3. Use external diff tool: x
4. Select "Beyond Compare" or "diff"
5. Review differences
```

## 関連ドキュメント

- **[ユーザーガイド](XEFM_USER_GUIDE.ja.md)** - XeFM の完全なドキュメント
- **[設定](CONFIGURATION_FEATURE.ja.md)** - 設定のオプション
- **[AWS S3 対応](S3_SUPPORT_FEATURE.ja.md)** - クラウドストレージとの連携
- **[アーカイブのブラウズ](ARCHIVE_FEATURE.ja.md)** - アーカイブ対応

## 技術的な詳細

実装の詳細とアーキテクチャについては、次を参照してください。
- **[SSH System](../doc/dev/SSH_SYSTEM.md)** - SFTP セッション、リクエストのパイプライン化、一括 stat のキャッシュ、既定のディレクトリの解決
- **[Path Polymorphism System](../doc/dev/PATH_POLYMORPHISM_SYSTEM.md)**
