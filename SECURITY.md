# Security

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately
through GitHub instead: **Security ▸ Report a vulnerability** on this
repository
([direct link](https://github.com/crftwr/xefm/security/advisories/new)).

Include the XeFM version, how it was installed, the operating system, and the
steps that show the problem. You will get an answer in the advisory thread,
and the fix will be released before the details are made public.

## What counts

Problems in XeFM itself, for example:

- a file, folder name, archive, or remote server that makes XeFM run code,
  write outside the folder it was asked to, or leak data;
- credentials (SSH, S3, network shares) stored or logged where they should not
  be;
- the desktop app packages (Microsoft Store, DMG, portable zip) or the PyPI
  package containing something they should not.

## What does not

- **Extensions and `config.py` run with your own permissions, by design.**
  There is no sandbox: installing an extension is like running a script. A
  problem in a third-party extension goes to its author. (Official packages in
  [crftwr/xefm-extensions](https://github.com/crftwr/xefm-extensions) are
  covered here.)
- Programs XeFM starts for you (your editor, diff tool, terminal, external
  programs you configured).
