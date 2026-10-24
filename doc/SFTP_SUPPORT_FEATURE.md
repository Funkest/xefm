# SFTP Support Feature Guide

English \| [日本語](SFTP_SUPPORT_FEATURE.ja.md)

## Overview

XeFM provides seamless SFTP (SSH File Transfer Protocol) support, allowing you to browse, search, and manage files on remote servers as if they were local directories. XeFM opens one SSH connection per server and runs every operation over it, and supports all standard file operations.

## Quick Start

### Prerequisites

1. **SSH access** to the remote server
2. **SSH config** (optional but recommended) in `~/.ssh/config`
3. **SSH keys** (optional) for passwordless authentication
4. **The `ssh` command** — the OpenSSH client. macOS and Linux have it; on
   Windows, the OpenSSH client built into Windows works, as does any other on
   your `PATH` (Git for Windows, MSYS2, Cygwin).

### Basic Usage

Navigate to an SFTP location using the standard SSH URL format:

```
ssh://hostname/path/to/directory
ssh://user@hostname/path/to/directory
ssh://hostname:port/path/to/directory
```

**Examples:**
```
ssh://myserver/home/user/projects
ssh://admin@192.168.1.100/var/log
ssh://server.example.com:2222/opt/data
```

### Quick Access Methods

**Method 1: Jump to Path Dialog**
1. Open **Jump to Path** (`jump_to_path`)
2. Enter: `ssh://hostname/path`
3. Press Enter

**Method 2: Favorites**
1. Add SFTP paths to favorites in config: `~/.xefm/config.py`
2. Open **Go → Go to Favorite…** (`favorites`)
3. Select your SFTP bookmark

**Method 3: Command Line**
```bash
python3 -m xefm --left ssh://server/path --right ~/local/path
```

## SSH Configuration

### Recommended Setup

Create or edit `~/.ssh/config` to simplify connections:

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

**Benefits:**
- Use short names: `ssh://myserver/path` instead of full details
- Centralized authentication configuration
- Consistent settings across all SSH tools

### SSH Key Authentication

**Generate SSH key** (if you don't have one):
```bash
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
```

**Copy key to server:**
```bash
ssh-copy-id user@hostname
```

**Test connection:**
```bash
ssh user@hostname
```

Once SSH key authentication works, XeFM will use it automatically.

## Features

### File Operations

All standard file operations work on SFTP paths:

- **Copy** (`copy_files`): Copy files/directories between local and remote
- **Move** (`move_files`): Move files/directories on remote server
- **Delete** (`delete_files`): Delete remote files/directories
- **Rename** (`rename`): Rename remote files/directories
- **Create Directory** (`create_directory`): Create directories on remote server
- **View Files** (`view_file`): View remote text files with syntax highlighting

These are the **File** menu's items; their keys depend on your keymap preset —
see [Keymap Presets](KEYMAP_PRESETS_FEATURE.md#every-key-side-by-side).

### Cross-Storage Operations

XeFM seamlessly handles operations between different storage types:

**Local ↔ SFTP:**
```
Copy: ~/local/file → ssh://server/remote/path
Move: ssh://server/data → ~/backup/
```

**SFTP ↔ S3:**
```
Copy: ssh://server/logs → s3://bucket/archive/
Move: s3://bucket/data → ssh://server/processing/
```

**SFTP ↔ Archive:**
```
Copy: ssh://server/file.txt → local-archive.zip
Extract: ssh://server/archive.tar.gz → ~/extracted/
```

### Search Functionality

**Filename Search** (`find_files`):
- Search for files by name pattern
- Supports wildcards: `*.py`, `test_*.txt`
- Real-time results as search progresses
- Works recursively through directories

**Content Search** (`find_in_files`):
- Search file contents using regex patterns
- Automatically detects text files
- Shows matching lines with context
- Efficient streaming for large files

**Example searches:**
```
*.log          # Find all log files
config.*       # Find config files with any extension
test_.*\.py    # Find Python test files
```

### Performance Optimizations

XeFM includes several optimizations for SFTP operations:

1. **One connection per server**
   - You log in once; every listing, copy and rename after that reuses the connection
   - A dropped connection is reopened the next time you use it

2. **Directory listings in one round trip**
   - A listing brings back every file's size, date and type with it
   - Transfers keep many requests in flight, so a long link stays busy

3. **Intelligent Caching**
   - Caches directory listings and file metadata
   - Configurable TTL (default: 30 seconds)
   - Automatic cache invalidation on modifications

4. **Optimized Search**
   - Streams file content for memory efficiency
   - Parallel processing where possible
   - Cancellable operations

### Text Viewer

View remote text files with full syntax highlighting:

1. Navigate to a text file on SFTP
2. Press `Enter`, or use **File → View File** (`view_file`), to open the viewer
3. Use arrow keys to scroll
4. Search within the file (`isearch`)
5. Press `Esc` to close the viewer

**Supported formats:** Python, JavaScript, JSON, YAML, Markdown, Shell scripts, and 20+ more with `pygments` installed.

## Configuration

### SFTP-Specific Settings

Add to `~/.xefm/config.py`:

```python
# SFTP cache TTL for successful results (seconds)
SSH_CACHE_TTL = 30

# SFTP cache TTL for cached errors (seconds)
SSH_CACHE_ERROR_TTL = 300
```

### Favorite SFTP Directories

Add frequently-used SFTP paths to favorites:

```python
FAVORITES = [
    {'name': 'Local Projects', 'path': '~/projects'},
    {'name': 'Dev Server', 'path': 'ssh://devbox/var/www'},
    {'name': 'Production Logs', 'path': 'ssh://prod-web1/var/log/nginx'},
    {'name': 'Backup Server', 'path': 'ssh://backup/mnt/backups'},
    {'name': 'S3 Bucket', 'path': 's3://my-bucket/data'},
]
```

Open them with **Go → Go to Favorite…** (`favorites`). The list is drawn from the config alone — no connection is
opened to any of these until you select one.

## Advanced Usage

### One connection per server

XeFM runs one `ssh` per server — the same `ssh <server> -s sftp` the `sftp`
command runs — and sends every operation over it. It does not depend on SSH
connection sharing (`ControlMaster`), so the OpenSSH built into Windows works
too. Anything in your `~/.ssh/config` for the host (`HostName`, `User`,
`ProxyJump`, `ProxyCommand`, keys) applies as it would to `ssh` itself; port
forwards configured there are left out of XeFM's connection.

### Batch Operations

Select multiple files and perform batch operations:

1. Select files (`toggle_select_down`)
2. Or select every file in the directory (`toggle_select_files`)
3. Run the operation (`copy_files` to copy, `delete_files` to delete, etc.)
4. Confirm operation
5. Watch progress bar for completion

The progress bar fills as the bytes actually move, in both directions, so a slow
transfer over a high-latency link does not look stalled at 0%. Press **ESC**
to cancel: the transfer stops within about half a second rather than running to
completion in the background, and the partly-transferred file is removed.

**Example: Backup multiple directories**
```
1. Navigate to ssh://server/data
2. Open ~/backup in the other pane
3. Select the directories
4. Copy them across (`copy_files`)
5. Press Enter to confirm
```

### Sub-shell with SFTP

Run `subshell` to enter sub-shell mode with SFTP environment variables:

```bash
# Environment variables available:
echo $XEFM_LEFT_DIR    # May be ssh://server/path
echo $XEFM_RIGHT_DIR   # May be local path
echo $XEFM_THIS_DIR    # Current pane (SFTP or local)

# Use with standard tools:
scp $XEFM_THIS_DIR/file.txt user@other:/path/
rsync -av $XEFM_THIS_DIR/ backup/
```

Type `exit` to return to XeFM.

## Troubleshooting

### Connection Issues

**Problem: "Connection refused" or "Connection timeout"**

Solutions:
1. Verify SSH access works: `ssh user@hostname`
2. Check firewall settings on server
3. Verify correct port (default: 22)
4. Check SSH service is running on server

**Problem: "Permission denied (publickey)"**

Solutions:
1. Verify SSH key is added: `ssh-add -l`
2. Copy key to server: `ssh-copy-id user@hostname`
3. Check SSH config has correct IdentityFile
4. Try password authentication first

**Problem: "Host key verification failed"**

Solutions:
1. Accept host key manually: `ssh user@hostname`
2. Or remove old key: `ssh-keygen -R hostname`
3. Update `~/.ssh/known_hosts`

### Performance Issues

**Problem: Slow directory listings**

Solutions:
1. Check network latency: `ping hostname`
2. Increase cache TTL in config
3. Use SSH compression: Add to `~/.ssh/config`:
   ```
   Compression yes
   CompressionLevel 6
   ```

**Problem: Search is slow**

Solutions:
1. Use filename search instead of content search when possible
2. Limit search scope to specific directories
3. Use more specific patterns to reduce results
4. Check network bandwidth

### Cache Issues

**Problem: Directory listing not updating**

Solutions:
1. Navigate out of and back into the directory to re-list it
2. Reduce SSH_CACHE_TTL in config
3. Restart XeFM to clear all caches

**Problem: Deleted files still showing**

Solution:
- Navigate out of and back into the directory to re-list it
- Cache will auto-invalidate after TTL expires

## Best Practices

### Security

1. **Use SSH keys** instead of passwords
2. **Restrict key permissions:** `chmod 600 ~/.ssh/id_rsa`
3. **Use different keys** for different servers
4. **Enable StrictHostKeyChecking** in SSH config
5. **Regularly rotate** SSH keys

### Performance

1. **Use SSH config** for connection settings
2. **Enable compression** for slow connections
3. **Keep cache TTL reasonable** (30-60 seconds)
4. **Use filename search** when content search isn't needed
5. **Batch operations** instead of individual file operations

### Workflow

1. **Add favorites** for frequently-accessed servers
2. **Use short hostnames** via SSH config
3. **Keep local and remote panes** for easy transfers
4. **Use search** to find files quickly
5. **Monitor progress** for large operations

## Limitations

### Current Limitations

1. **Read-only archives on SFTP:** Cannot modify files inside remote archives
2. **No symbolic link creation:** Can read symlinks but not create them
3. **No permission changes:** Cannot chmod files (use sub-shell mode)
4. **No ownership changes:** Cannot chown files (use sub-shell mode)

### Workarounds

**For permission changes:**
```bash
# Run subshell (Tools → Subshell Here) to enter the sub-shell
chmod 755 $XEFM_THIS_DIR/script.sh
exit
```

**For advanced operations:**
```bash
# Use sub-shell with standard tools
rsync -av --progress $XEFM_THIS_DIR/ backup/
tar czf archive.tar.gz $XEFM_THIS_DIR/*
```

## Examples

### Example 1: Deploy Website

```
1. Left pane: ~/projects/website (local)
2. Right pane: ssh://webserver/var/www/html
3. Select the updated files in the left pane
4. Copy them across (`copy_files`)
5. Confirm overwrite
6. Watch progress bar
```

### Example 2: Download Logs

```
1. Left pane: ssh://server/var/log
2. Right pane: ~/logs/backup
3. Search for logs (`find_files`), pattern: *.log
4. Select every file in the results (`toggle_select_files`)
5. Copy them across (`copy_files`)
6. Files copied to local backup
```

### Example 3: Clean Old Files

```
1. Navigate to: ssh://server/tmp
2. Search for old files (`find_files`), pattern: *.tmp
3. Review results
4. Select the files to delete
5. Delete them (`delete_files`)
6. Confirm deletion
```

### Example 4: Compare Directories

```
1. Left pane: ~/local/config
2. Right pane: ssh://server/etc/app
3. Run an external diff tool (`programs`)
4. Select "Beyond Compare" or "diff"
5. Review differences
```

## Related Documentation

- **[User Guide](XEFM_USER_GUIDE.md)** - Complete XeFM documentation
- **[Configuration](CONFIGURATION_FEATURE.md)** - Configuration options
- **[AWS S3 Support](S3_SUPPORT_FEATURE.md)** - Cloud storage integration
- **[Archive Browsing](ARCHIVE_FEATURE.md)** - Archive support

## Technical Details

For implementation details and architecture, see:
- **[SSH System](../doc/dev/SSH_SYSTEM.md)** - The SFTP session, request pipelining, bulk-stat caching, default-directory resolution
- **[Path Polymorphism System](../doc/dev/PATH_POLYMORPHISM_SYSTEM.md)**
