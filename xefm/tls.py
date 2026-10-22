"""HTTPS verified by the operating system (#676).

Python's ``ssl`` verifies a server with OpenSSL against a static PEM file, and
OpenSSL does not check revocation. On macOS that file is wherever the Python
build was told to look — for the app bundle's python.org Python, a path
outside the app, missing on a Mac without that Python — and on Windows it is
the roots Windows happens to have fetched so far. A revoked intermediate (the
eMudhra compromise of October 2026) is accepted either way.

:func:`use_os_trust_store` hands verification to the OS instead, through
``truststore``: Security.framework on macOS, CryptoAPI on Windows. It replaces
``ssl.SSLContext`` process-wide, so every HTTPS client that builds its context
afterwards — ``urllib`` (extension installs, PuiKit's remote images), urllib3
under boto3 — verifies the same way. Linux has no OS verifier to defer to and
keeps OpenSSL with the distribution's CA bundle.
"""

import sys

from xefm.log_manager import getLogger

logger = getLogger("TLS")

#: The platforms whose OS verifies certificates itself.
_OS_VERIFIERS = ("darwin", "win32")


def use_os_trust_store() -> bool:
    """Verify HTTPS through the OS from here on. Call it first thing, before
    anything opens a connection: a context built earlier keeps OpenSSL's
    verification. True when it took effect."""
    if sys.platform not in _OS_VERIFIERS:
        return False
    try:
        import truststore
    except ImportError:
        logger.warning("truststore is not installed: HTTPS is verified by OpenSSL "
                       "against Python's CA file, without revocation checks — "
                       "pip install truststore")
        return False
    truststore.inject_into_ssl()
    return True
