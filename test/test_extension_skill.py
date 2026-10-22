"""The XeFM agent skill, the scaffold and the checker agree (#583, #639).

The promise is that an agent following ``xefm/skills/xefm`` ends up with a
package that meets XeFM's requirements, and with a ``config.py`` edit that
names only settings and actions XeFM has. The extension half holds only while
three things stay in step, so each is pinned here:

- the scaffold ``xefm ext new`` writes passes the check with no findings, and
  its own test passes;
- every rule the skill states is one the checker enforces (the code lint), and
  every API name the skill cites exists;
- the skill's own example manifest passes the check, and its lists of
  contribution kinds and events are the checker's.

Run with: python -m pytest test/test_extension_skill.py -v
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import unittest.mock
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import xefm  # noqa: E402
from xefm import extension_cli  # noqa: E402
from xefm import extensions as ext  # noqa: E402
from xefm import user_api  # noqa: E402

#: The router agents load first, and the two references it hands off to.
#: ``SKILL`` is the extensions reference, which most tests below read.
ROUTER = (ext.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
SKILL = (ext.SKILL_DIR / "references" / "extensions.md").read_text(encoding="utf-8")
CONFIG = (ext.SKILL_DIR / "references" / "config.md").read_text(encoding="utf-8")


def _section(title: str) -> str:
    start = SKILL.index(title)
    end = SKILL.find("\n## ", start + 1)
    return SKILL[start:end if end != -1 else None]


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class Scaffold(_Tmp):
    def test_passes_the_check_with_no_findings_at_all(self):
        root = ext.scaffold("hello-xefm", self.tmp)
        manifest, problems = ext.check_package(root)
        self.assertEqual(problems, [])
        self.assertEqual(manifest.id, "hello-xefm")

    def test_its_own_tests_pass(self):
        root = ext.scaffold("hello-xefm", self.tmp)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
            cwd=root, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_package_name_follows_the_id(self):
        self.assertEqual(ext.package_name_for("hello-xefm"), "hello_xefm")
        self.assertEqual(ext.package_name_for("a.b-c"), "a_b_c")
        self.assertEqual(ext.package_name_for("7zip"), "ext_7zip")
        root = ext.scaffold("7zip", self.tmp)
        self.assertEqual(ext.errors(ext.check_package(root)[1]), [])

    def test_refuses_a_bad_id_or_an_existing_folder(self):
        with self.assertRaises(ext.InstallError):
            ext.scaffold("Bad Id", self.tmp)
        ext.scaffold("dup", self.tmp)
        with self.assertRaises(ext.InstallError):
            ext.scaffold("dup", self.tmp)

    def test_cli(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = extension_cli.main(["new", "cli-made", "--dir", str(self.tmp)])
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "cli-made" / ext.MANIFEST).is_file())


class CodeLint(_Tmp):
    def lint(self, code: str, name="mod.py"):
        path = self.tmp / "pkg" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(code), encoding="utf-8")
        return ext.lint_code(self.tmp)

    def test_private_names_are_errors(self):
        (problem,) = self.lint("def a(ctx):\n    return ctx._app\n")
        self.assertEqual(problem.severity, "error")
        self.assertEqual(str(problem).split(": ")[1], "pkg/mod.py:2")
        self.assertIn("'._app' is private", problem.message)

    def test_self_and_dunders_are_fine(self):
        self.assertEqual(self.lint('''
            class A:
                def __init__(self):
                    self._x = 1
                    print.__name__
        ''')[1:], [])
        problems = self.lint("class A:\n    def f(self):\n        return self._x.__doc__\n")
        self.assertEqual(problems, [])

    def test_internal_xefm_imports_are_errors(self):
        problems = self.lint('''
            import xefm.app
            from xefm.config import config_manager
            from xefm.user_api import API_VERSION
            from xefm.path_base import ReadOnlyPathImpl
            from . import sibling
        ''')
        self.assertEqual([p.severity for p in problems], ["error", "error"])
        self.assertIn("'xefm.app' is internal", problems[0].message)

    def test_only_the_public_names_of_a_public_module(self):
        problems = self.lint('''
            from xefm.user_api import md_code_block, run_guarded
            from xefm.path_base import ReadOnlyPathImpl, UriPathImpl
            from xefm.user_api import *
        ''')
        self.assertEqual([p.severity for p in problems], ["error", "error"])
        self.assertIn("'run_guarded' is not part of xefm.user_api's public API",
                      problems[0].message)
        # The message lists what is allowed, so the fix needs no search.
        self.assertIn("md_code_block", problems[0].message)
        self.assertIn("'UriPathImpl' is not part of xefm.path_base", problems[1].message)

    def test_names_read_through_the_module_are_checked_too(self):
        problems = self.lint('''
            import xefm.user_api
            import xefm.user_api as ua
            from xefm import user_api
            from xefm import path_base as pb

            ok = (xefm.user_api.API_VERSION, ua.md_escape, user_api.TaskOutcome,
                  pb.ReadOnlyPathImpl, user_api.__doc__)
            bad = (xefm.user_api.load_user_entries, ua.hooks, user_api.Path,
                   pb.UnsupportedPathImpl)
        ''')
        self.assertEqual(len(problems), 4, problems)
        self.assertTrue(all(p.severity == "error" for p in problems))
        self.assertEqual(sorted(p.message.split("'")[1] for p in problems),
                         ["Path", "UnsupportedPathImpl", "hooks", "load_user_entries"])

    def test_from_xefm_import_an_internal_module_is_an_error(self):
        (problem,) = self.lint("from xefm import user_api, config\n")
        self.assertIn("'xefm.config' is internal", problem.message)

    def test_every_public_name_exists(self):
        for module in ext.PUBLIC_MODULES:
            for name in ext.public_names(module):
                self.assertTrue(hasattr(sys.modules[module], name), f"{module}.{name}")

    def test_ctx_extension_is_an_error_naming_its_replacement(self):
        (problem,) = self.lint("def a(ctx):\n    return ctx.extension.state\n")
        self.assertEqual(problem.severity, "error")
        self.assertIn("use xefm.user_api.extension(__name__)", problem.message)

    def test_print_and_sys_path_are_warnings(self):
        problems = self.lint('''
            import sys
            sys.path.append("x")
            print("hi")
        ''')
        self.assertEqual(sorted(p.severity for p in problems), ["warning", "warning"])

    def test_vendored_code_is_not_judged(self):
        self.assertEqual(self.lint("print(1)\nx._y\n", name="_vendor/lib/a.py"), [])


class SkillMatchesTheChecker(_Tmp):
    def test_frontmatter(self):
        head = ROUTER.split("---")[1]
        self.assertIn("name: xefm\n", head)
        self.assertEqual(ext.SKILL_DIR.name, "xefm")   # the folder is the name
        description = re.search(r"description: (.*)", head).group(1)
        # One skill for both jobs: it has to trigger on either.
        for word in ("config.py", "extension", "xefm ext check"):
            self.assertIn(word, description)

    def test_the_router_names_references_that_exist(self):
        cited = set(re.findall(r"`(references/[\w.-]+)`", ROUTER))
        self.assertEqual(cited, {"references/config.md", "references/extensions.md",
                                 "references/actions.md",
                                 "references/config-template.md"})
        for ref in cited:
            self.assertTrue((ext.SKILL_DIR / ref).is_file(), ref)

    def test_the_example_manifest_passes(self):
        """Every reference the example makes is given a stub, so what is being
        tested is the manifest the skill teaches, not the stubs."""
        toml = re.search(r"## 2\. The manifest\s+```toml\n(.*?)```", SKILL, re.S).group(1)
        root = self.tmp / "hello-xefm"
        root.mkdir()
        (root / ext.MANIFEST).write_text(toml, encoding="utf-8")
        manifest = ext.read_manifest(root)
        for _, ref in manifest.references():
            module, name = ref.split(":")
            path = root.joinpath(*module.split(".")).with_suffix(".py")
            path.parent.mkdir(parents=True, exist_ok=True)
            for parent in path.relative_to(root).parents:
                if str(parent) != ".":
                    (root / parent / "__init__.py").touch()
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"{name} = None\n")
        problems = ext.check_manifest(manifest, machine=False)
        self.assertEqual(ext.errors(problems), [])

    def test_contribution_kinds_and_events_are_the_checker_s(self):
        kinds = re.search(r"Contribution kinds: (.*?)\.\n", SKILL, re.S).group(1)
        self.assertEqual(set(re.findall(r"`(\w+)`", kinds)),
                         set(ext.CONTRIBUTION_TABLES) | {"key_suggestions"})
        events = re.search(r"- Events: (.*?)\.\n", SKILL, re.S).group(1)
        self.assertEqual(set(re.findall(r"`(\w+)`", events)), set(user_api.EVENTS))

    def test_the_public_modules_are_the_checker_s(self):
        section = _section("## 3. The code")
        for module in ext.PUBLIC_MODULES:
            self.assertIn(f"`{module}`", section)

    def test_every_import_the_docs_show_is_public(self):
        """What the skill and the user docs tell an author to import must pass
        the check that author's package will face. (``references/config.md``
        is about ``config.py`` itself, which the template already has importing
        helpers such as ``xefm_tool``; the check is for extension code.)"""
        texts = [SKILL]
        for doc in ("CUSTOMIZATION_FEATURE.md", "EXTENSIONS_FEATURE.md",
                    "VIRTUAL_FOLDERS_FEATURE.md"):
            texts.append((Path(xefm.__file__).parent.parent / "doc" / doc)
                         .read_text(encoding="utf-8"))
        seen = 0
        for text in texts:
            for module, names in re.findall(r"from (xefm\.\w+) import ([\w, ]+)", text):
                self.assertIn(module, ext.PUBLIC_MODULES)
                for name in (n.strip() for n in names.split(",")):
                    self.assertIn(name, ext.public_names(module), f"{module}.{name}")
                    seen += 1
        self.assertGreater(seen, 0)

    def test_the_skill_names_the_public_lists(self):
        section = _section("## 3. The code")
        for module in ext.PUBLIC_MODULES:
            listed = re.search(rf"- `{re.escape(module)}\.__all__` — (.*?)\n(?!  )",
                               section, re.S).group(1)
            self.assertEqual(set(re.findall(r"`(\w+)`", listed)),
                             set(ext.public_names(module)), module)

    def test_every_ctx_name_the_skill_cites_exists(self):
        # Lower-case names only: the skill also quotes ``ctx._app`` — as the
        # thing not to do.
        for name in set(re.findall(r"`ctx\.([a-z]\w*)", SKILL)):
            self.assertTrue(hasattr(user_api.ActionContext, name), f"ctx.{name}")
        for name in set(re.findall(r"extension\(__name__\)\.(\w+)", SKILL)):
            self.assertTrue(hasattr(ext.ExtensionHandle, name)
                            or name in ("id", "version"), f"extension(__name__).{name}")

    def _bullets(self, heading: str) -> set:
        block = SKILL.split(heading, 1)[1].lstrip("\n").split("\n\n", 1)[0]
        # Lower-case only: the block also names types (`EntryInfo`).
        return set(re.findall(r"`([a-z]\w*)", block))

    def test_every_pane_name_the_skill_cites_exists(self):
        for name in self._bullets("`PaneApi` (`ctx.pane`):"):
            self.assertTrue(hasattr(user_api.PaneApi, name), f"PaneApi.{name}")

    def test_every_entry_name_the_skill_cites_exists(self):
        para = SKILL.split("`EntryInfo`:", 1)[1].split("\n\n", 1)[0]
        for name in re.findall(r"`(\w+)`", para):
            if name in ("stat",):
                continue
            self.assertTrue(hasattr(user_api.EntryInfo, name)
                            or name in user_api.EntryInfo.__slots__, f"EntryInfo.{name}")

    def test_every_ext_subcommand_the_skill_uses_exists(self):
        parser = extension_cli._parser()
        commands = set(parser._subparsers._group_actions[0].choices)
        for command in set(re.findall(r"xefm ext (\w+)", SKILL)):
            self.assertIn(command, commands)

    def test_skill_install_copies_it(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = extension_cli.skill_main(["--install", str(self.tmp)])
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "xefm" / "SKILL.md").is_file())
        self.assertTrue((self.tmp / "xefm" / "references" / "config.md").is_file())

    def test_ext_skill_is_an_alias(self):
        with redirect_stdout(io.StringIO()):
            code = extension_cli.main(["skill", "--install", str(self.tmp)])
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "xefm" / "SKILL.md").is_file())

    def _legacy(self, name: str) -> Path:
        old = self.tmp / ext.LEGACY_SKILL_NAME
        old.mkdir()
        (old / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
        return old

    def test_install_removes_the_old_extension_only_skill(self):
        old = self._legacy(ext.LEGACY_SKILL_NAME)
        with redirect_stdout(io.StringIO()):
            extension_cli.skill_main(["--install", str(self.tmp)])
        self.assertFalse(old.exists())

    def test_install_keeps_a_same_named_folder_that_is_not_the_old_skill(self):
        old = self._legacy("someone-elses")
        with redirect_stdout(io.StringIO()):
            extension_cli.skill_main(["--install", str(self.tmp)])
        self.assertTrue(old.exists())


class ConfigReferenceMatchesXeFM(unittest.TestCase):
    """``references/config.md`` names settings and actions; each must be one
    XeFM has, or an agent writes an attribute XeFM silently ignores."""

    def test_every_setting_it_names_is_in_the_template(self):
        from xefm import _config
        names = set(re.findall(r"`([A-Z][A-Z0-9_]{2,})`", CONFIG))
        names |= set(re.findall(r"^\s+([A-Z][A-Z0-9_]{2,}) = ", CONFIG, re.M))
        self.assertIn("KEY_BINDINGS", names)       # the pattern found them
        for name in names:
            self.assertTrue(hasattr(_config.Config, name), name)

    def test_every_action_in_its_examples_exists(self):
        from xefm import actions
        tables = re.findall(r"KEY_BINDINGS = \{(.*?)\}\n", CONFIG, re.S)
        cited = {name for table in tables
                 for name in re.findall(r"^\s*'([a-z][\w.-]*)': [\[{]", table, re.M)}
        cited -= {"select-documents"}               # the example's own action
        self.assertIn("reload_config", cited)
        for name in cited:
            if "." in name:
                context = name.split(".", 1)[0]
                self.assertIn(name, actions.registry.names(context), name)
            else:
                self.assertIsNotNone(actions.registry.builtin(actions.FILER, name), name)

    def test_the_action_table_is_current(self):
        """references/actions.md is generated; a stale one teaches an agent
        names or keys XeFM no longer has."""
        done = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "tools"
                                 / "gen_skill_references.py"), "--check"],
            capture_output=True, text=True,
            env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent.parent)))
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_every_old_action_name_is_in_the_table(self):
        """An older config.py binds old names; an agent that cannot tell one
        from a typo either deletes it or binds the action twice."""
        from xefm import actions
        table = (ext.SKILL_DIR / "references" / "actions.md").read_text(encoding="utf-8")
        for context in actions.CONTEXTS:
            for action in actions.registry.actions(context):
                for alias in action.aliases:
                    row = f"| `{alias}` | `{action.name}` |"
                    self.assertEqual(table.count(row), 1, row)

    def test_the_skill_no_longer_sends_agents_to_the_docs_for_names(self):
        """The clean room could not follow those links, and neither can an
        agent with no web access: the names have to be in the skill."""
        self.assertNotIn("KEY_BINDINGS_FEATURE.html", CONFIG)
        self.assertIn("references/actions.md", CONFIG)

    def test_the_keymap_presets_it_names_exist(self):
        from xefm import keymap_presets
        for name in re.findall(r"`KEY_PRESET = '(\w+)'", CONFIG) + ["afx", "orthodox"]:
            self.assertEqual(keymap_presets.canonical(name), name)



class Distribution(_Tmp):
    """The skill reaches agents as a release zip any Agent Skills client can
    unpack, and through a doc an agent can follow by itself."""

    REPO = Path(__file__).resolve().parent.parent

    def test_the_zip_holds_one_skill_folder(self):
        import zipfile
        path = ext.write_skill_zip(self.tmp / ext.skill_zip_name())
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            for member in ("xefm/SKILL.md", "xefm/references/config.md",
                           "xefm/references/extensions.md"):
                self.assertIn(member, names)
            self.assertTrue(all(n.startswith("xefm/") for n in names))
            text = archive.read("xefm/SKILL.md").decode()
        self.assertIn("name: xefm\n", text.split("---")[1])

    def _assert_stamped(self, files: dict):
        version = ext.skill_version()
        head = files["xefm/SKILL.md"].split("---")[1]
        self.assertIn(f'metadata:\n  xefm-version: "{version}"\n', head)
        self.assertIn(f"packaged from **XeFM {version}**", files["xefm/SKILL.md"])
        self.assertIn(f"Generated from XeFM {version}'s",
                      files["xefm/references/actions.md"])
        for name, text in files.items():
            self.assertNotIn(ext.SKILL_VERSION_TOKEN, text, name)

    def test_the_zip_states_the_version_it_describes(self):
        """#690: a skill out in the world can be told apart from a newer one."""
        import zipfile
        path = ext.write_skill_zip(self.tmp / "s.zip")
        with zipfile.ZipFile(path) as archive:
            self._assert_stamped({n: archive.read(n).decode() for n in archive.namelist()})

    def test_install_states_the_version_it_describes(self):
        with redirect_stdout(io.StringIO()):
            extension_cli.skill_main(["--install", str(self.tmp)])
        self._assert_stamped({
            f"xefm/{f.relative_to(self.tmp / 'xefm').as_posix()}": f.read_text(encoding="utf-8")
            for f in (self.tmp / "xefm").rglob("*.md")})

    def test_the_source_carries_no_version(self):
        """Only the token: a version written into the tree is one more place
        a bump has to remember."""
        self.assertIn(f'xefm-version: "{ext.SKILL_VERSION_TOKEN}"', ROUTER)
        self.assertNotIn(xefm.__version__, ROUTER)

    def test_the_version_check_comes_first(self):
        """Read before the work starts, not after a long SKILL.md."""
        self.assertLess(ROUTER.index("## Which XeFM this describes"),
                        ROUTER.index("## Ground rules"))

    def test_a_checkout_off_the_release_tag_is_a_dev_build(self):
        def git(stdout):
            return unittest.mock.patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, stdout, ""))
        with git(f"v{xefm.__version__}\n"):
            self.assertEqual(ext.skill_version(), xefm.__version__)
        with git(""):
            self.assertEqual(ext.skill_version(), f"{xefm.__version__}+dev")
        with unittest.mock.patch("subprocess.run", side_effect=FileNotFoundError):
            self.assertEqual(ext.skill_version(), xefm.__version__)

    def test_an_install_without_a_checkout_is_the_release(self):
        with unittest.mock.patch.object(ext, "SKILL_DIR", self.tmp / "a" / "b" / "xefm"):
            self.assertEqual(ext.skill_version(), xefm.__version__)

    def test_the_asset_name_carries_the_version(self):
        self.assertEqual(ext.skill_zip_name("1.8.1"), "xefm-1.8.1-skill.zip")
        self.assertEqual(ext.skill_zip_name(), f"xefm-{xefm.__version__}-skill.zip")

    def test_the_wheel_takes_every_skill_file(self):
        """package-data globs do not recurse: each depth needs its pattern."""
        text = (self.REPO / "pyproject.toml").read_text(encoding="utf-8")
        line = re.search(r'^xefm = \[(.*)\]', text, re.M).group(1)
        patterns = set(re.findall(r'"([^"]+)"', line))
        package = ext.SKILL_DIR.parent.parent
        for file in ext.SKILL_DIR.rglob("*"):
            if file.is_file():
                depth = len(file.relative_to(package / "skills").parts)
                self.assertIn("skills" + "/*" * depth, patterns, file)

    def test_cli_zip_and_install(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(extension_cli.main(
                ["skill", "--zip", str(self.tmp / "s.zip")]), 0)
        self.assertTrue((self.tmp / "s.zip").is_file())
        with self.assertRaises(SystemExit):   # no client's directory is assumed
            with redirect_stdout(io.StringIO()), \
                    unittest.mock.patch("sys.stderr", io.StringIO()):
                extension_cli.main(["skill", "--install"])

    def test_the_names_agree(self):
        """One asset name, spelled the same in the code, the Makefile, and the
        URL and command the install doc gives an agent."""
        makefile = (self.REPO / "Makefile").read_text(encoding="utf-8")
        self.assertIn("SKILL_ZIP := dist/" + ext.skill_zip_name("$(XEFM_VERSION)"),
                      makefile)
        doc = (self.REPO / "doc" / "AGENT_SKILL_FEATURE.md").read_text(encoding="utf-8")
        urls = re.findall(r"https://github\.com/crftwr/xefm/releases/\S+?\.zip", doc)
        self.assertEqual(urls, ["https://github.com/crftwr/xefm/releases/download/"
                                "vX.Y.Z/" + ext.skill_zip_name("X.Y.Z")])
        self.assertIn("xefm skill --zip <temp>/" + ext.skill_zip_name("X.Y.Z"), doc)
        self.assertIn("name: xefm`", doc)
        self.assertIn(ext.SKILL_DIR.name + "/SKILL.md", doc)
        self.assertIn(ext.LEGACY_SKILL_NAME, doc)   # and says to remove the old one

    def test_the_old_page_points_at_the_new_one(self):
        """Agents were handed the old URL before the rename."""
        old = (self.REPO / "doc" / "EXTENSION_AUTHORING_SKILL_FEATURE.md").read_text(
            encoding="utf-8")
        self.assertIn("AGENT_SKILL_FEATURE.md#instructions-for-ai-agents", old)


if __name__ == "__main__":
    unittest.main()
