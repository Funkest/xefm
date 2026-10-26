"""
SSH Connection Management for XeFM

Each host gets one ``ssh <host> -s sftp`` process — the same command ``sftp``
itself runs — and XeFM speaks the SFTP protocol to the server on the other end
of its stdin/stdout (:mod:`xefm.sftp_client`). Every operation on that host is
a request over that one session: no process per operation, and nothing that
needs ssh's connection sharing (ControlMaster), which the OpenSSH built into
Windows does not have (#532). See ``doc/dev/SSH_SYSTEM.md``.
"""

import atexit
import os
import posixpath
import stat as stat_module
import subprocess
import threading
import time
from typing import Callable, Dict, List, Optional

from xefm.log_manager import getLogger
from xefm.sftp_client import (
    FX_NO_SUCH_FILE, FX_PERMISSION_DENIED, SFTPClient, SFTPClosed, SFTPError,
    SFTPTimeout,
)
from xefm.ssh_cache import get_ssh_cache


# SSH-specific exception types
class SSHError(Exception):
    """Base exception for SSH-related errors"""
    pass


class SSHAuthenticationError(SSHError):
    """Exception raised when SSH authentication fails"""
    pass


class SSHConnectionTimeoutError(SSHError):
    """Exception raised when SSH connection times out"""
    pass


class SSHPathNotFoundError(SSHError):
    """Exception raised when a remote path does not exist"""
    pass


class SSHPermissionDeniedError(SSHError):
    """Exception raised when permission is denied for an operation"""
    pass


class SSHConnectionLostError(SSHError):
    """Exception raised when an active connection is lost"""
    pass


#: What a progress callback looks like: ``(bytes_done, bytes_total)``.
ProgressCallback = Callable[[int, int], None]


def ssh_command(hostname: str, port: Optional[str] = None,
                identity_file: Optional[str] = None) -> List[str]:
    """The ``ssh`` command line that opens an SFTP session to ``hostname``.

    The ``-o`` options are the ones ``sftp`` passes to the ``ssh`` it starts:
    no X11 or agent forwarding, no LocalCommand, and no port forwards from
    ``~/.ssh/config`` — a forward that cannot bind would otherwise be this
    session's problem. On top of those: never prompt (there is no terminal to
    prompt on), accept a host seen for the first time, and notice a dead
    link within about a minute rather than waiting on it forever.
    """
    return _ssh_options(port, identity_file) + ['-s', hostname, 'sftp']


def ssh_exec_command(hostname: str, remote_command: str, port: Optional[str] = None,
                     identity_file: Optional[str] = None) -> List[str]:
    """The ``ssh`` command line that runs ``remote_command`` (already quoted
    for the remote shell) on ``hostname`` — same options as the SFTP session,
    so it never prompts either. Used for what SFTP v3 cannot do, such as
    reading and writing extended attributes (file tags, #585)."""
    return _ssh_options(port, identity_file) + [hostname, remote_command]


def _ssh_options(port: Optional[str], identity_file: Optional[str]) -> List[str]:
    cmd = ['ssh',
           '-o', 'ForwardX11=no',
           '-o', 'ForwardAgent=no',
           '-o', 'PermitLocalCommand=no',
           '-o', 'ClearAllForwardings=yes',
           '-o', 'BatchMode=yes',
           '-o', 'StrictHostKeyChecking=accept-new',
           '-o', 'ServerAliveInterval=15',
           '-o', 'ServerAliveCountMax=4']
    if port and str(port) != '22':
        cmd.extend(['-p', str(port)])
    if identity_file:
        cmd.extend(['-i', identity_file])
    return cmd


def _spawn_ssh(cmd: List[str]) -> subprocess.Popen:
    """Start the ssh process with binary pipes on all three streams. On
    Windows it gets no console window of its own — there is nothing to show in
    one, and from the GUI app it would flash up."""
    kwargs = {}
    if os.name == 'nt':
        kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, bufsize=0, **kwargs)


def _entry(name: str, attrs: Dict, *, is_symlink: bool = False) -> Dict:
    """One file's record, in the shape ``list_directory`` and ``stat`` return.
    ``mode`` is the full ``st_mode``, type bits included."""
    mode = attrs.get('permissions', 0)
    is_dir = stat_module.S_ISDIR(mode)
    return {
        'name': name,
        'size': attrs.get('size', 0),
        'mtime': float(attrs.get('mtime', 0)),
        'mode': mode,
        'is_dir': is_dir,
        'is_file': stat_module.S_ISREG(mode),
        'is_symlink': is_symlink or stat_module.S_ISLNK(mode),
    }


class SSHConnection:
    """
    One SFTP session to a remote host, over one ``ssh`` process.

    Safe to share between threads: requests from several of them are in flight
    on the session at once (see :class:`xefm.sftp_client.SFTPClient`).
    """

    #: How long logging in may take, ProxyCommand and all, before XeFM gives up.
    CONNECT_TIMEOUT = 30.0

    #: How long one reply may take. A transfer can run far longer than this;
    #: each chunk of it cannot. A request that times out leaves the session in
    #: an unknown state, so the connection is dropped and the next use
    #: reconnects.
    REQUEST_TIMEOUT = 60.0

    def __init__(self, hostname: str, config: Dict[str, str], *,
                 spawn: Optional[Callable[[List[str]], subprocess.Popen]] = None):
        """
        Initialize SSH connection.

        Args:
            hostname: Remote hostname (Host entry from SSH config)
            config: SSH configuration dictionary with keys like:
                    'HostName', 'User', 'Port', 'IdentityFile', etc.
            spawn: Starts the process the session runs over, given the ssh
                   command line; :func:`_spawn_ssh` when None. Tests pass one
                   that starts a local ``sftp-server`` instead.
        """
        self.hostname = hostname
        self.config = config
        self.logger = getLogger("SSHCon")
        self._lock = threading.Lock()
        self._spawn = spawn

        self.actual_host = config.get('HostName', hostname)
        self.user = config.get('User', None)
        self.port = config.get('Port', '22')
        self.identity_file = config.get('IdentityFile', None)

        #: The directory the server starts a session in (normally the home
        #: directory), learned when connecting.
        self.default_directory = None

        self._process: Optional[subprocess.Popen] = None
        self._client: Optional[SFTPClient] = None
        self._stderr: List[bytes] = []
        self._cache = get_ssh_cache()

    def run_remote(self, remote_command: str, *, input: bytes | None = None,
                   timeout: float = 60.0) -> subprocess.CompletedProcess:
        """Run one shell command on the host, outside the SFTP session, and
        return its result (bytes). Each call is its own ssh process — a
        handshake, unless the user's ssh config multiplexes — so callers batch
        many files into one command."""
        cmd = ssh_exec_command(self.hostname, remote_command, self.port,
                               self.identity_file)
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        return subprocess.run(cmd, input=input, capture_output=True,
                              timeout=timeout, **kwargs)

    # --- connecting -------------------------------------------------------------

    def connect(self) -> bool:
        """
        Start the session: run ssh, then the SFTP version handshake.

        Returns:
            True if connection successful

        Raises:
            SSHAuthenticationError: If SSH authentication fails
            SSHConnectionTimeoutError: If connection times out
            SSHError: For other connection errors
        """
        with self._lock:
            if self._alive():
                return True
            self._teardown()
            cmd = ssh_command(self.hostname, self.port, self.identity_file)
            try:
                process = (self._spawn or _spawn_ssh)(cmd)
            except OSError as e:
                error_msg = f"Cannot run ssh to connect to {self.hostname}: {e}"
                self.logger.error(error_msg)
                raise SSHError(error_msg)
            self._process = process
            self._stderr = []
            threading.Thread(target=self._drain_stderr, args=(process,),
                             name="xefm-ssh-stderr", daemon=True).start()
            client = SFTPClient(process.stdout, process.stdin,
                                timeout=self.REQUEST_TIMEOUT)
            self._client = client
            try:
                client.start(timeout=self.CONNECT_TIMEOUT)
            except SFTPTimeout:
                self._teardown()
                error_msg = (f"Connection timeout to {self.hostname}: no answer "
                             f"in {self.CONNECT_TIMEOUT:g}s")
                self.logger.error(error_msg)
                raise SSHConnectionTimeoutError(error_msg)
            except (SFTPClosed, SFTPError) as e:
                raise self._login_failure(e)
            try:
                self.default_directory = client.realpath('.') or '/'
            except (SFTPError, SFTPTimeout, SFTPClosed) as e:
                self.logger.warning(f"No starting directory from {self.hostname}: {e}")
                self.default_directory = '/'
            self.logger.info(f"Connected to {self.hostname}, "
                             f"default directory: {self.default_directory}")
            return True

    def _drain_stderr(self, process: subprocess.Popen) -> None:
        """Keep ssh's stderr read, so it can never fill the pipe and stall ssh,
        and keep what it said for a failed login to report."""
        try:
            for line in iter(process.stderr.readline, b''):
                self._stderr.append(line)
                del self._stderr[:-50]
        except (OSError, ValueError):
            pass

    def _stderr_text(self) -> str:
        if self._process is not None:
            try:
                self._process.wait(timeout=2)  # let ssh finish saying why
            except subprocess.TimeoutExpired:
                pass
        time.sleep(0.05)  # the drain thread's last line
        return b''.join(self._stderr).decode('utf-8', 'replace').strip()

    def _login_failure(self, cause: Exception) -> SSHError:
        """The exception for a session that ended before it began — what ssh
        printed is the only account of why."""
        stderr = self._stderr_text()
        self._teardown()
        lower = stderr.lower()
        detail = stderr or str(cause)
        if 'permission denied' in lower or 'authentication failed' in lower:
            error = SSHAuthenticationError(
                f"SSH authentication failed for {self.hostname}. "
                "Please check your SSH keys and permissions.")
        elif ('timed out' in lower or 'connection refused' in lower
              or 'no route to host' in lower):
            error = SSHConnectionTimeoutError(
                f"Connection timeout to {self.hostname}. "
                "Host may be unreachable or not responding.")
        else:
            error = SSHError(f"Failed to connect to {self.hostname}: {detail}")
        self.logger.error(str(error))
        if stderr:
            self.logger.error(f"Detailed error: {stderr}")
        return error

    def _alive(self) -> bool:
        return (self._client is not None and self._client.alive
                and self._process is not None and self._process.poll() is None)

    def _teardown(self) -> None:
        """Close the session and make sure its ssh process is gone."""
        client, process = self._client, self._process
        self._client = None
        self._process = None
        if client is not None:
            client.close()
        if process is not None:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            for stream in (process.stdout, process.stderr):
                try:
                    stream.close()
                except (OSError, ValueError, AttributeError):
                    pass

    def disconnect(self):
        """End the session and its ssh process."""
        with self._lock:
            if self._client is not None:
                self._teardown()
                self.logger.info(f"Disconnected from {self.hostname}")

    def is_connected(self) -> bool:
        """Whether the session is still up. Costs nothing: the session notices
        on its own when ssh exits or the stream ends."""
        with self._lock:
            return self._alive()

    # --- running requests -------------------------------------------------------

    def _sftp(self) -> SFTPClient:
        client = self._client
        if client is None or not client.alive:
            raise SSHConnectionLostError(f"Not connected to {self.hostname}")
        return client

    def _call(self, what: str, path: str, fn, *, quiet_missing: bool = False):
        """Run ``fn(client)`` and turn what can go wrong into the SSH
        exceptions callers know. ``what`` and ``path`` word the message."""
        client = self._sftp()
        try:
            return fn(client)
        except SFTPError as e:
            if e.code == FX_NO_SUCH_FILE:
                error = SSHPathNotFoundError(f"Remote path not found: {path}")
                # Often a plain existence check: not worth an error line.
                (self.logger.debug if quiet_missing else self.logger.error)(str(error))
                raise error
            if e.code == FX_PERMISSION_DENIED:
                error = SSHPermissionDeniedError(f"Permission denied {what}: {path}")
                self.logger.error(str(error))
                raise error
            error_msg = f"Failed {what} {path}: {e.message or e}"
            self.logger.error(error_msg)
            raise SSHError(error_msg)
        except SFTPTimeout as e:
            # The reply may still come, or never: the session's state is
            # unknown, so it is not reused.
            with self._lock:
                self._teardown()
            error_msg = f"Timed out {what} {path} on {self.hostname}: {e}"
            self.logger.error(error_msg)
            raise SSHConnectionTimeoutError(error_msg)
        except SFTPClosed as e:
            error_msg = f"Connection to {self.hostname} lost {what} {path}: {e}"
            self.logger.error(error_msg)
            raise SSHConnectionLostError(error_msg)

    @staticmethod
    def _normalize(remote_path: str) -> str:
        """Collapse ``//``, ``/./`` and ``/a/../`` and trim a trailing slash,
        so equivalent paths share one cache entry."""
        return posixpath.normpath(remote_path) if remote_path else '/'

    # --- metadata ---------------------------------------------------------------

    def _resolve_links(self, client: SFTPClient, base: str,
                       items: List[tuple]) -> List[Dict]:
        """Records for ``(name, lstat attributes)`` pairs. A symlink is
        described by what it points to — a link to a directory is a directory
        to browse into — but stays flagged as a link; a broken one is described
        as the link itself. The targets are looked up all at once."""
        links = [i for i, (_n, a) in enumerate(items)
                 if stat_module.S_ISLNK(a.get('permissions', 0))]
        targets = {}
        if links:
            found = client.stat_many([posixpath.join(base, items[i][0]) for i in links])
            targets = {i: t for i, t in zip(links, found) if isinstance(t, dict)}
        return [_entry(name, targets.get(i, attrs), is_symlink=i in links)
                for i, (name, attrs) in enumerate(items)]

    def list_directory(self, remote_path: str) -> List[Dict[str, any]]:
        """
        List directory contents.

        Returns:
            List of file/directory entries with metadata. Each entry is a dict with:
                - name: filename
                - size: file size in bytes
                - mtime: modification time as Unix timestamp
                - mode: the full ``st_mode`` (type and permission bits)
                - is_dir: True if directory (or a symlink to one)
                - is_file: True if regular file (or a symlink to one)
                - is_symlink: True if symbolic link

        Raises:
            SSHPathNotFoundError: If directory does not exist
            SSHPermissionDeniedError: If permission is denied
            SSHConnectionLostError: If connection is lost
            SSHError: For other errors
        """
        remote_path = self._normalize(remote_path)
        cached = self._cache.get(operation='list_directory',
                                 hostname=self.hostname, path=remote_path)
        if cached is not None:
            return cached
        try:
            entries = self._call(
                'listing', remote_path,
                lambda c: self._resolve_links(c, remote_path, c.listdir(remote_path)),
                quiet_missing=True)
        except (SSHPathNotFoundError, SSHPermissionDeniedError) as error:
            # Remembered, so a path that is not there is not asked about again
            # for a while (the cache's error TTL).
            self._cache.put(operation='list_directory', hostname=self.hostname,
                            path=remote_path, error=error)
            raise
        # The listing already holds every entry's attributes: cache them under
        # the key stat() uses, so a stat of any of them is free.
        for entry in entries:
            self._cache.put(operation='stat', hostname=self.hostname,
                            path=posixpath.join(remote_path, entry['name']),
                            data=entry)
        self._cache.put(operation='list_directory', hostname=self.hostname,
                        path=remote_path, data=entries)
        return entries

    def stat(self, remote_path: str) -> Dict[str, any]:
        """
        Get file/directory metadata, in the shape :meth:`list_directory`
        returns. A symlink is described by its target and flagged as a link.

        Raises:
            SSHPathNotFoundError: If path does not exist
            SSHPermissionDeniedError: If permission is denied
            SSHConnectionLostError: If connection is lost
            SSHError: For other errors
        """
        remote_path = self._normalize(remote_path)
        cached = self._cache.get(operation='stat', hostname=self.hostname,
                                 path=remote_path)
        if cached is not None:
            return cached
        name = posixpath.basename(remote_path) or '/'
        try:
            entry = self._call(
                'reading', remote_path,
                lambda c: self._resolve_links(
                    c, posixpath.dirname(remote_path),
                    [(name, c.lstat(remote_path))])[0],
                quiet_missing=True)
        except (SSHPathNotFoundError, SSHPermissionDeniedError) as error:
            self._cache.put(operation='stat', hostname=self.hostname,
                            path=remote_path, error=error)
            raise
        self._cache.put(operation='stat', hostname=self.hostname,
                        path=remote_path, data=entry)
        return entry

    # --- contents ---------------------------------------------------------------

    def read_file(self, remote_path: str,
                  progress: Optional[ProgressCallback] = None, sink=None):
        """
        Read file contents — or, given a writable binary ``sink``, stream them
        into it and return how many bytes that was.

        ``progress(done, total)`` is called as the transfer runs — 0 first, the
        full size last — and is the cancel point: whatever it raises stops the
        transfer and is re-raised unchanged.

        Raises:
            SSHPathNotFoundError: If file does not exist
            SSHPermissionDeniedError: If permission is denied
            SSHConnectionLostError: If connection is lost
            SSHError: For other errors
        """
        return self._call('reading', remote_path,
                          lambda c: c.read_file(remote_path, progress, sink))

    def write_file(self, remote_path: str, data,
                   progress: Optional[ProgressCallback] = None,
                   size: Optional[int] = None):
        """
        Write file contents, creating or replacing the file. ``data`` is
        ``bytes`` or a readable binary stream (``size`` then scales the
        progress). ``progress`` works as for :meth:`read_file`; a cancelled
        upload leaves however much had arrived.

        Raises:
            SSHPermissionDeniedError: If permission is denied
            SSHConnectionLostError: If connection is lost
            SSHError: For other errors (e.g., disk full)
        """
        try:
            self._call('writing', remote_path,
                       lambda c: c.write_file(remote_path, data, progress, size))
        finally:
            # Written, partly written or cancelled: what was cached is stale.
            self._cache.invalidate_path(self.hostname, remote_path)

    # --- changes ----------------------------------------------------------------

    def delete_file(self, remote_path: str):
        """Delete a file (or a symlink)."""
        self._call('deleting', remote_path, lambda c: c.remove(remote_path))
        self._cache.invalidate_path(self.hostname, remote_path)

    def delete_directory(self, remote_path: str):
        """Delete a directory, which must be empty."""
        self._call('deleting directory', remote_path, lambda c: c.rmdir(remote_path))
        self._cache.invalidate_directory(self.hostname, remote_path)

    def create_directory(self, remote_path: str):
        """Create a directory; its parent must exist."""
        self._call('creating directory', remote_path, lambda c: c.mkdir(remote_path))
        self._cache.invalidate_path(self.hostname, remote_path)

    def rename(self, old_path: str, new_path: str):
        """Rename/move a file or directory, replacing ``new_path`` where the
        server allows it (OpenSSH does)."""
        self._call('renaming', f"{old_path} -> {new_path}",
                   lambda c: c.rename(old_path, new_path))
        self._cache.invalidate_path(self.hostname, old_path)
        self._cache.invalidate_path(self.hostname, new_path)


class SSHConnectionManager:
    """
    One :class:`SSHConnection` per host, reconnected when it has dropped and
    closed when it has been idle for a while.

    Singleton pattern ensures only one manager exists per application instance.
    """

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'SSHConnectionManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    atexit.register(cleanup_ssh_connections)
        return cls._instance

    def __init__(self):
        if SSHConnectionManager._instance is not None:
            raise RuntimeError("Use get_instance() to get SSHConnectionManager")
        self._connections: Dict[str, SSHConnection] = {}
        self._connection_lock = threading.Lock()
        self._last_used: Dict[str, float] = {}
        self._timeout = 300  # 5 minutes idle timeout
        self.logger = getLogger("SSHCon")

    def get_connection(self, hostname: str, config: Dict[str, str]) -> SSHConnection:
        """
        The connection for ``hostname``: the open one, or a new one if there
        is none or the old one has dropped.

        Raises:
            SSHAuthenticationError: If authentication fails
            SSHConnectionTimeoutError: If connection times out
            SSHError: For other connection errors
        """
        with self._connection_lock:
            conn = self._connections.get(hostname)
            if conn is not None:
                if conn.is_connected():
                    self._last_used[hostname] = time.time()
                    return conn
                self.logger.warning(f"Connection to {hostname} dropped, reconnecting")
                conn.disconnect()
                del self._connections[hostname]
                self._last_used.pop(hostname, None)
            conn = SSHConnection(hostname, config)
            conn.connect()  # This will raise specific exceptions on failure
            self._connections[hostname] = conn
            self._last_used[hostname] = time.time()
            return conn

    def close_connection(self, hostname: str):
        with self._connection_lock:
            conn = self._connections.pop(hostname, None)
            self._last_used.pop(hostname, None)
        if conn is not None:
            conn.disconnect()
            self.logger.info(f"Closed connection to {hostname}")

    def close_all(self):
        """Close all connections gracefully."""
        with self._connection_lock:
            conns = list(self._connections.items())
            self._connections.clear()
            self._last_used.clear()
        for hostname, conn in conns:
            try:
                conn.disconnect()
            except Exception as e:
                self.logger.error(f"Error disconnecting from {hostname}: {e}")

    def cleanup_idle_connections(self):
        """Close connections that have been idle beyond timeout."""
        now = time.time()
        with self._connection_lock:
            idle = [h for h, used in self._last_used.items() if now - used > self._timeout]
            conns = [(h, self._connections.pop(h)) for h in idle if h in self._connections]
            for h in idle:
                self._last_used.pop(h, None)
        for hostname, conn in conns:
            self.logger.info(f"Closing idle connection to {hostname}")
            try:
                conn.disconnect()
            except Exception as e:
                self.logger.error(f"Error disconnecting from {hostname}: {e}")

    def check_connection_health(self, hostname: str) -> bool:
        with self._connection_lock:
            conn = self._connections.get(hostname)
        return conn is not None and conn.is_connected()

    def get_active_connections(self) -> list:
        with self._connection_lock:
            return list(self._connections.keys())


def cleanup_ssh_connections():
    """
    Close every SSH connection — at exit, so no ssh process outlives XeFM.
    """
    try:
        SSHConnectionManager.get_instance().close_all()
    except Exception as e:
        getLogger("SSHCon").error(f"Error during SSH connection cleanup: {e}")
