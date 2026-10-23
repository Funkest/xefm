"""An extension's ``requires.python_packages``, synced with
~/.xefm/requirements.txt into one directory (#664 follow-up).

Run with: python -m pytest test/test_extension_python_packages.py -v
"""

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_extensions import _Home, _config  # noqa: E402
from test_python_packages import HOST, _FakePip, _wheel  # noqa: E402

from xefm import extension_cli  # noqa: E402
from xefm import extensions as ext  # noqa: E402
from xefm import python_packages as pp  # noqa: E402


MANIFEST = '''
    [extension]
    id = "{id}"
    version = "0.1.0"
    api_version = 1

    [requires]
    python_packages = %s
'''


def _manifest(*requirements):
    return MANIFEST % json.dumps(list(requirements))


class _Fixture(_Home):
    def setUp(self):
        super().setUp()
        self.pp_layout = pp.Layout(self.home)

    def needs(self, *requirements, ext_id=None):
        root, _ = self.installed_package(ext_id, manifest=_manifest(*requirements),
                                         code={})
        return ext.read_manifest(root).id

    def stamp(self, extensions, requirements=""):
        """A target directory as a sync of these extension lists left it."""
        self.pp_layout.target.mkdir(parents=True, exist_ok=True)
        (self.pp_layout.target / pp.STAMP).write_text(json.dumps(
            pp.make_stamp(requirements, HOST, extensions)), encoding="utf-8")


class Manifest(_Fixture):
    def test_plain_requirements_pass(self):
        root, _ = self.package(manifest=_manifest(
            "PyYAML>=6", "numpy[extra] >=1.26, <3 ; python_version >= '3.10'"), code={})
        self.assertEqual(ext.errors(ext.check_package(root)[1]), [])

    def test_options_urls_and_paths_are_refused(self):
        for line in ("--index-url https://evil.example/simple", "-e .", "./vendor/pkg",
                     "pkg @ https://example.com/pkg.whl", ""):
            with self.subTest(line=line):
                root, _ = self.package(manifest=_manifest(line), code={})
                bad = ext.errors(ext.check_package(root)[1])
                self.assertEqual([p.where for p in bad], ["requires.python_packages"])

    def test_the_install_summary_names_them(self):
        root, _ = self.package(manifest=_manifest("PyYAML>=6"), code={})
        self.assertIn("installs Python package from PyPI: PyYAML>=6",
                      ext.summarize(ext.read_manifest(root)))


class Requirements(_Fixture):
    def test_enabled_packages_only(self):
        a = self.needs("PyYAML>=6")
        b = self.needs("rawpy")
        ext.set_enabled(b, False, self.layout)
        self.assertEqual(ext.python_requirements(self.layout), {a: ["PyYAML>=6"]})

    def test_check_names_the_extension_that_changed(self):
        a = self.needs("PyYAML>=6")
        status = pp.check(self.pp_layout, HOST)
        self.assertEqual(status.state, pp.NEEDS_SYNC)
        self.assertIn("extensions' Python packages", status.reason)
        self.stamp({a: ["PyYAML>=6"]})
        self.assertEqual(pp.check(self.pp_layout, HOST).state, pp.IN_SYNC)
        self.stamp({a: ["PyYAML>=5"]})
        status = pp.check(self.pp_layout, HOST)
        self.assertEqual(status.state, pp.NEEDS_SYNC)
        self.assertIn(a, status.reason)

    def test_uninstalling_the_last_one_needs_a_sync_to_remove_them(self):
        self.stamp({"gone-ext": ["PyYAML"]})
        self.assertEqual(pp.check(self.pp_layout, HOST).state, pp.NEEDS_SYNC)


class Load(_Fixture):
    def test_not_loaded_until_synced(self):
        a = self.needs("PyYAML>=6")
        report = ext.load(_config(), self.layout)
        self.assertEqual(report.loaded, [])
        self.assertIn("Sync Python Packages", report.skipped[0][1])
        self.stamp({a: ["PyYAML>=6"]})
        report = ext.load(_config(), self.layout)
        self.assertEqual([m.id for m in report.loaded], [a])

    def test_a_sync_for_another_list_does_not_count(self):
        a = self.needs("PyYAML>=6")
        self.stamp({a: ["PyYAML>=5"]})
        self.assertEqual(ext.load(_config(), self.layout).loaded, [])

    def test_a_sync_for_another_platform_does_not_count(self):
        a = self.needs("PyYAML>=6")
        self.stamp({a: ["PyYAML>=6"]})
        stamp = json.loads((self.pp_layout.target / pp.STAMP).read_text())
        stamp["platform"] = "elsewhere"
        (self.pp_layout.target / pp.STAMP).write_text(json.dumps(stamp))
        self.assertEqual(ext.load(_config(), self.layout).loaded, [])


class Sync(_Fixture):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(pp, "host_distributions", return_value=dict(HOST))
        patcher.start()
        self.addCleanup(patcher.stop)

    def sync(self, popen):
        return pp.sync(self.pp_layout, python="py", popen=popen,
                       run=lambda *a, **k: subprocess.CompletedProcess(a, 0))

    def test_one_resolution_for_the_file_and_every_extension(self):
        a = self.needs("PyYAML>=6")
        b = self.needs("rawpy", "PyYAML")
        self.pp_layout.requirements.write_text("six\n", encoding="utf-8")
        fake = _FakePip(dists=[("PyYAML", "6.0.3", {"yaml/__init__.py": ""})])
        self.sync(fake)
        first, second = sorted([a, b])
        reqs = {a: "PyYAML>=6\n", b: "rawpy\nPyYAML\n"}
        self.assertEqual(fake.requirements,
                         f"-r {self.pp_layout.requirements}\n"
                         f"# extension {first}\n{reqs[first]}"
                         f"# extension {second}\n{reqs[second]}")
        self.assertTrue(pp.synced_for(self.pp_layout, a, ["PyYAML>=6"]))
        self.assertEqual(pp.check(self.pp_layout, HOST).state, pp.IN_SYNC)
        self.assertEqual(len(ext.load(_config(), self.layout).loaded), 2)

    def test_extensions_alone_are_enough_to_sync(self):
        a = self.needs("PyYAML")
        fake = _FakePip()
        self.sync(fake)
        self.assertEqual(fake.requirements, f"# extension {a}\nPyYAML\n")

    def test_a_clash_between_extensions_names_both(self):
        a = self.needs("PyYAML>=7")
        b = self.needs("PyYAML<6")
        fake = _FakePip(code=1, output=(
            "The conflict is caused by:",
            "    The user requested pyyaml>=7",
            "    The user requested pyyaml<6",
            "ERROR: ResolutionImpossible"))
        with self.assertRaises(pp.SyncError) as caught:
            self.sync(fake)
        message = str(caught.exception)
        self.assertIn("conflict with each other", message)
        self.assertIn(f"pyyaml>=7 (extension {', '.join(sorted([a, b]))})", message)


class Cli(_Fixture):
    def install(self, *argv, answer="y"):
        root, _ = self.package(manifest=_manifest("PyYAML"), code={})
        out = io.StringIO()
        with mock.patch.object(pp, "sync", return_value=pp.SyncResult([], [])) as sync, \
                mock.patch("builtins.input", return_value=answer), redirect_stdout(out):
            code = extension_cli.main(["install", *argv, str(root)], layout=self.layout)
        return code, sync, out.getvalue()

    def test_yes_installs_and_syncs(self):
        code, sync, out = self.install("-y")
        self.assertEqual(code, 0)
        sync.assert_called_once()
        self.assertIn("Python packages synced", out)

    def test_the_sync_is_asked_for(self):
        code, sync, out = self.install(answer="n")
        # "n" to the install question itself: nothing happens at all.
        self.assertEqual(code, 1)
        sync.assert_not_called()

    def test_declining_the_sync_says_how_to_do_it_later(self):
        answers = iter(["y", "n"])
        root, _ = self.package(manifest=_manifest("PyYAML"), code={})
        out = io.StringIO()
        with mock.patch.object(pp, "sync") as sync, \
                mock.patch("builtins.input", side_effect=lambda _: next(answers)), \
                redirect_stdout(out):
            code = extension_cli.main(["install", str(root)], layout=self.layout)
        self.assertEqual(code, 0)
        sync.assert_not_called()
        self.assertIn("xefm deps sync", out.getvalue())

    def test_disabling_says_a_sync_is_due(self):
        a = self.needs("PyYAML")
        self.stamp({a: ["PyYAML"]})
        out = io.StringIO()
        with redirect_stdout(out):
            extension_cli.main(["disable", a], layout=self.layout)
        self.assertIn("run `xefm deps sync`", out.getvalue())


@unittest.skipIf(subprocess.run([sys.executable, "-m", "pip", "--version"],
                                capture_output=True).returncode != 0, "no pip")
class RealPip(_Fixture):
    """Through the real pip, offline: requirements.txt points pip at a local
    wheel folder, and the extension asks for the project by name."""

    def test_an_extension_imports_what_it_asked_for(self):
        wheels = self.home / "wheels"
        wheels.mkdir()
        _wheel(wheels, "xefm_t664_ext_dep", "2.0", "xefm_t664_ext_dep")
        self.pp_layout.requirements.write_text(
            "--no-index\n--find-links ./wheels\n", encoding="utf-8")
        a = self.needs("xefm_t664_ext_dep>=2")
        pp.sync(self.pp_layout, python=sys.executable)
        self.addCleanup(sys.modules.pop, "xefm_t664_ext_dep", None)
        import xefm_t664_ext_dep
        self.assertEqual(xefm_t664_ext_dep.VALUE, 42)
        self.assertEqual([m.id for m in ext.load(_config(), self.layout).loaded], [a])


if __name__ == "__main__":
    unittest.main()
