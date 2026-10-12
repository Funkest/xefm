"""Helpers for testing XeFM's SSH layer without an SSH server.

``SSHConnection`` speaks SFTP to whatever its ``spawn`` hook starts. In
production that is ``ssh <host> -s sftp``; here it is OpenSSH's own
``sftp-server``, the program sshd would run on the far side of that ssh — so
these tests exercise the real protocol against the real server, minus only the
login.
"""

import os
import shutil
import sys

from xefm import ssh_connection as SC


def find_sftp_server():
    """Path of a local OpenSSH ``sftp-server``, or None."""
    candidates = ["/usr/lib/openssh/sftp-server", "/usr/lib/ssh/sftp-server",
                  "/usr/libexec/openssh/sftp-server", "/usr/libexec/sftp-server",
                  "/usr/lib/sftp-server"]
    if sys.platform == "win32":
        git = shutil.which("git")
        roots = [os.environ.get("ProgramFiles", r"C:\Program Files") + r"\Git"]
        if git:
            # <root>\cmd\git.exe or <root>\bin\git.exe
            roots.insert(0, os.path.dirname(os.path.dirname(git)))
        candidates = [os.path.join(r, "usr", "lib", "ssh", "sftp-server.exe")
                      for r in roots]
    return next((c for c in candidates if os.path.isfile(c)), None)


SFTP_SERVER = find_sftp_server()


def remote(local_path):
    """How ``sftp-server`` names a local path: as is on POSIX, and in the MSYS
    form (``/c/Users/...``) for Git for Windows' build."""
    path = str(local_path)
    if sys.platform == "win32":
        path = "/" + path[0].lower() + path[2:].replace("\\", "/")
    return path


def connect(hostname="test-host"):
    """An ``SSHConnection`` whose session runs over a local ``sftp-server``."""
    conn = SC.SSHConnection(hostname, {},
                            spawn=lambda cmd: SC._spawn_ssh([SFTP_SERVER]))
    conn.connect()
    return conn
