# Extension Packages — Implementation

Issue #583, from discussion #543 (§§2–7 plus additions A–H). The pre-PR check
in §8 is a separate piece of work.

## Modules

- `xefm/extensions.py` — the manifest, the static check, the installed set,
  install/uninstall/sync, loading into a config, settings, and the
  `ctx.extension` handle.
- `xefm/extension_cli.py` — `xefm ext check|install|uninstall|list|enable|disable|sync|settings`.
  `xefm.app.main` dispatches `argv[1] == "ext"` here before the UI's argparse
  runs, so no backend is opened.
- `XeFMApp.install_extension` / `show_extensions` — the in-app install, with a
  summary-and-confirm box, and the load report.

## The static check (`check_manifest`)

The check never imports package code. A reference `pkg.mod:name` is resolved
like this:

1. Find `pkg/mod.py` or `pkg/mod/__init__.py` under the package root.
2. `ast.parse` it.
3. Look for a top-level binding of `name`. `_top_level_names` covers `def`,
   `class`, assignments and imports, and descends into top-level `if`/`try`
   blocks.

Each finding is a `Problem(severity, where, message)`. `where` is the manifest
field, with TOML-style quoting.

Unknown sections, keys and contribution kinds are errors, not warnings. The
point is that an assistant can correct its output from the message.

Machine-dependent checks are warnings, and only when `machine=True`:

- a program missing from `PATH`;
- a host package that cannot be imported.

Checks that involve other installed packages:

- a duplicate id;
- the same top-level module name in two packages (the vendoring collision in
  addition C, option 2);
- the same derived settings class name in two packages.

A top-level name in `sys.stdlib_module_names`, `xefm` or `puikit` is refused
outright.

Keys are validated against `xefm.config`'s `_MODIFIER_ALIASES`, `_NAMED_KEYS`
and `_PUNCT_NAMES`, the same tables `KeyBindings` parses with.

### The code lint (`lint_code`)

The check also lints every `.py` file in the package, skipping `_vendor/` and
dot-paths. It uses `ast.walk` over each file's syntax tree:

- **Error:** an `Attribute` whose name starts with `_` but not `__`, unless it
  is on `self` or `cls`. This is the `user_api` firewall.
- **Error:** an absolute import of an `xefm` module outside `PUBLIC_MODULES`
  (`xefm.user_api`, `xefm.path_base`).
- **Warning:** a call to `print`.
- **Warning:** `sys.path`.

These findings use `where = "code:<rel path>:<line>"`, and `Problem.__str__`
prints them without the manifest prefix.

## The authoring skill and the scaffold

The user asked for an AI-agent skill whose instructions, followed as written,
satisfy every extension requirement. Three pieces make that hold.

- **The skill:** `xefm/skills/xefm-extension-authoring/SKILL.md`. It ships as
  package data (`pyproject.toml`, `MANIFEST.in`). The macOS and Windows bundle
  scripts copy the whole `xefm/` tree, so the skill reaches every channel.
  `xefm ext skill [--install DIR]` prints its path or copies it into
  `~/.claude/skills/`.
- **The scaffold:** `scaffold(id, parent)`, behind `xefm ext new`, writes a
  package with zero findings. It has a manifest, a thin `actions.py` over a
  plain `logic.py`, `settings.py`, `tests/`, and a `pytest.ini` with
  `pythonpath = .`. A root `conftest.py` would do the same job, but it would be
  a top-level module name shared by every package, and the collision check
  would refuse it.
- **The checker:** it enforces everything the skill states as a rule, and the
  skill's workflow ends at "`xefm ext check` is clean".

`test/test_extension_skill.py` keeps the three in step. It asserts that:

- the scaffold has no findings, and its generated test passes when run in a
  subprocess;
- the skill's example manifest passes, with each reference stubbed;
- the contribution kinds, events and public modules the skill lists equal the
  checker's;
- every `ctx.*`, `PaneApi` and `EntryInfo` name the skill cites exists;
- every `xefm ext` subcommand the skill uses exists.

If the API or the checker changes, these tests fail until the skill is updated.

## Loading

`ConfigManager.load_config` runs these steps in order:

1. Run `config.py`.
2. `_copy_missing_fields` from the template.
3. `_load_extensions()`, which calls `extensions.load(config, Layout(config_dir), namespace=vars(config_module))`.

The order means "config.py wins" compares against the user's own entries and
the template defaults alike. Reload goes through the same path.
`prepare_user_extensions` already purges modules under `~/.xefm/extensions/`
from `sys.modules`, so a package's edited code reloads too.

For each package directory (sorted; dot-directories skipped), `load` does:

1. Skip it if `extensions.toml` lists it as disabled. A directory that
   `extensions.toml` does not list is a *local* package and is loaded (the
   promotion path in G).
2. Run `check_manifest(machine=False)`. On errors, skip the package and report
   the first error, with a count and a pointer to `xefm ext check`.
3. Apply the backend, platform and `host_packages` gates.
4. `_apply`:
   - Resolve every contribution first: `_import_ref` appends the package root
     to `sys.path` and imports.
   - Then fold the results into copies of the config's tables, skipping keys
     the config already has.
   - An exception during resolution skips the whole package, before any table
     is touched.
5. Apply key suggestions only when `KEY_BINDINGS` has no entry for the action
   (an empty list counts: the user unbound it on purpose) and every key is
   free. "Free" is judged by `_bound_keys`: every key in `KEY_BINDINGS`, plus
   the registry defaults of `FILER` actions the config does not mention.

Actions and hooks are wrapped by `_in_extension`, which:

- refuses to run, with a warning naming the program, while a
  `requires.programs` entry is missing;
- otherwise sets `ctx._extension` to the package's `ExtensionHandle` for the
  duration of the call, and restores the previous value afterwards.

`ActionContext.extension` reads `ctx._extension`. The wrapped function keeps
its docstring (`functools.wraps`), so `user_api._build_action` still takes the
help text from it.

The result is a `LoadReport` with `loaded`, `skipped` (label and reason) and
`warnings`. `XeFMApp._report_extensions` logs it at startup and on every reload,
and also hands the app's state manager to `ExtensionHandle` for
`ctx.extension.state`.

## Settings (addition A, revised)

The discussion sketched a `settings_base(id)` base class. The user chose plain
classes instead:

- A settings class in `config.py` is an ordinary top-level class, found by name
  in the executed module's namespace.
- The name is `config_class_name(manifest)`: `settings.config_class` if the
  manifest gives one, otherwise the id split on `-`, `.` and `_`, PascalCased,
  plus `Config`.

`_load_settings` builds an object for each loaded package that has
`settings.defaults`:

1. Copy the upper-case attributes of the defaults class, inherited ones
   included.
2. Overlay the user class's own upper-case attributes.
3. Skip, with a warning, any attribute the defaults class lacks. The warning
   lists the names that do exist.

It also warns about any class in the config module whose name ends in `Config`
(other than `Config`) and that no discovered package claims. Without that
warning, a misspelled class name would pass silently.

Because `config.py` never references the package, uninstalling one leaves a
harmless class behind. Nothing needs a stub.

`settings_template` prints a commented class with every default; it backs
`xefm ext settings <id>`.

## The installed set

`~/.xefm/extensions.toml` holds one `[extensions."<id>"]` table each, with
`version`, `source`, `directory` and `enabled`. Python only reads TOML, so
`write_installed` writes this fixed shape itself, escaping strings, and replaces
the file atomically.

`install(source)`:

1. `fetch` the source:
   - A directory is used in place.
   - A zip is extracted with `_safe_extract`, which refuses members that
     resolve outside the target.
   - A `github:owner/repo[@ref]` source or a github.com URL becomes a codeload
     zip URL.
   - Any other `https://` URL is fetched as is.
   - The manifest root is the extracted top, or its single child directory
     (GitHub zips wrap everything in `repo-ref/`).
2. Check the package against the others already installed.
3. Copy it to `.<id>.installing` and swap it into place.

A directory with the same id that `extensions.toml` does not list is a local
package and is never overwritten. A reinstall keeps the entry's `enabled`
flag.

`uninstall` deletes `extension-data/<id>/` only when asked; the CLI asks
interactively. `sync` reinstalls every listed package whose directory is
missing.

## Decisions on the discussion's open questions

1. **Native wheels XeFM doesn't ship:** out of scope for v1. `host_packages`
   covers what the build already has.
2. **Name:** "extension". Packages live in the existing `~/.xefm/extensions/`,
   as G proposes.
3. **Catalog:** none in v1. Install is from a source only.
4. **Pre-PR check:** separate work.

Not done yet:

- `xefm.testing` fixtures (F).
- Enter on an extension zip offering to install it. The explicit action exists
  instead.
- The Microsoft Store dynamic-code policy check (§5). It matters only once a
  catalog exists.
- Rewriting vendored imports (C, option 1). Only the collision refusal is done.

## Tests

`test/test_extensions.py` covers:

- the check: precise fields, no import during the check, collisions,
  data-only packages;
- loading: config.py wins, all-or-nothing loading, gates, missing programs,
  `ctx.extension`;
- key suggestions;
- settings: derived and declared class names, overlay, typo warnings, an
  unclaimed `…Config` class, the template;
- install, uninstall and sync from a directory, a zip, and GitHub with a fake
  opener, plus refusal of a zip that escapes its folder;
- the CLI;
- `ConfigManager` integration;
- the in-app install.
