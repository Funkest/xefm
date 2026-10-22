# TLS Verification — Implementation

XeFM verifies HTTPS through the operating system on macOS and Windows, in the
app and the TUI alike (#676). `xefm/tls.py` holds the switch, and
`xefm.app.main()` calls it before anything else.

## Why not OpenSSL's default

Python's `ssl` verifies a server with OpenSSL against a static PEM file, and it
does not check revocation.

- **macOS app bundle.** python.org's Python looks for
  `/Library/Frameworks/Python.framework/Versions/3.14/etc/openssl/cert.pem`, which
  is outside the app. On a Mac without python.org's Python the file is missing,
  so every fetch failed with `CERTIFICATE_VERIFY_FAILED` (reproduced on a clean
  macOS 12 in Tart). Where the file exists, it is a symlink to that
  installation's `certifi`, which the user may never update.
- **Revocation.** The eMudhra intermediate compromise (October 2026, Mozilla bug
  2083449) left certificates that a static PEM accepts and the OS rejects.
  `/etc/ssl/cert.pem` was considered first and still trusted them.
- **Windows.** Python reads the Windows certificate store, but OpenSSL does the
  verifying. Windows fetches roots on demand, the first time its own verifier
  needs one, so Python sees only the roots something else has already used.

## What it does

`use_os_trust_store()` calls `truststore.inject_into_ssl()` on `darwin` and
`win32`. That replaces `ssl.SSLContext` process-wide, and urllib3's own
reference to it as well. Every client that builds a context afterwards
verifies through Security.framework or CryptoAPI:

- `urllib`, used by extension installs and PuiKit's remote images in Markdown
- urllib3 under boto3

Linux has no OS verifier to hand off to. `truststore` there would only be
OpenSSL with the system paths again, so Linux keeps Python's default.

`truststore` is a requirement on macOS and Windows (`requirements.txt`, with a
`sys_platform` marker). If it is missing, a pip install made before the
requirement existed, XeFM logs a warning and keeps OpenSSL.

## S3

botocore passes its CA bundle (certifi) through `load_verify_locations`. On
macOS, `truststore` adds such certificates as anchors alongside the system's
(`SecTrustSetAnchorCertificatesOnly(False)`), so S3 trusts certifi's roots too.
The OS still checks revocation on those chains. Checked 2026-10-22:

- an anonymous `list_objects_v2` succeeds
- a urllib3 pool given `ca_certs=certifi.where()` still refuses the revoked
  eMudhra intermediate

## Tests

- `test/test_tls.py` covers the platforms and a missing package, using a
  stand-in module.
- A real injection would leak across tests in a pytest worker, because three
  tests run the real `main()`. `test/conftest.py`'s `restore_ssl` undoes it
  with `truststore.extract_from_ssl()` after every test.

## Packaging

- **macOS and Windows app bundles:** pick `truststore` up from
  `requirements.txt`.
- **Homebrew formula (crftwr/homebrew-tap):** needs a `truststore`
  `resource` block.
