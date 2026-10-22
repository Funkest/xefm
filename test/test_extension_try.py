"""``xefm ext try`` and the event log it reads (#682).

The run itself starts XeFM in a pseudo-terminal, which is too slow for this
suite; what is pinned here is everything around it: the home holds the
package and none of the user's, no first-run dialog is left to take a key,
the script is refused before anything is installed, the recording is a valid
asciicast, and XeFM's event log carries the log pane's lines and exceptions.

Run with: python -m pytest test/test_extension_try.py -v
"""

import io
import json
import logging
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from xefm import event_log  # noqa: E402
from xefm import extension_cli  # noqa: E402
from xefm import extension_try as trial  # noqa: E402
from xefm import extensions as ext  # noqa: E402
from xefm import log_manager  # noqa: E402

try:
    import quality_loop.drive.keys  # noqa: F401
    HAVE_KEYS = True
except ImportError:
    HAVE_KEYS = False


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class Home(_Tmp):
    def setUp(self):
        super().setUp()
        self.package = ext.scaffold("hello-xefm", self.tmp)
        self.homes = []

    def tearDown(self):
        for home in self.homes:
            home.remove()
        super().tearDown()

    def make(self, **kw) -> trial.TryHome:
        home = trial.TryHome(self.package, keymap=kw.pop("keymap", "afx"), **kw)
        self.homes.append(home)
        return home

    def test_holds_the_package_and_nothing_of_the_user_s(self):
        home = self.make()
        self.assertTrue((home.xefm / "extensions" / "hello-xefm" / ext.MANIFEST).is_file())
        self.assertEqual(home.manifest.id, "hello-xefm")
        self.assertFalse((home.xefm / "config.py").exists())   # XeFM's template
        env = home.environment()
        self.assertEqual(env["HOME"], str(home.root))
        self.assertEqual(env["USERPROFILE"], str(home.root))
        self.assertNotIn(str(Path.home()), env["HOME"])

    def test_no_first_run_dialog_is_left_to_take_a_key(self):
        from xefm.state_manager import StateManager
        state = StateManager(self.make(keymap="orthodox").xefm / "state.db")
        self.assertIs(state.get_state("tips.enabled"), False)
        self.assertEqual(state.get_state("keymap.preset"), "orthodox")

    def test_a_config_can_be_given(self):
        config = self.tmp / "my_config.py"
        config.write_text("class Config:\n    pass\n", encoding="utf-8")
        home = self.make(config=config)
        self.assertEqual((home.xefm / "config.py").read_text(encoding="utf-8"),
                         config.read_text(encoding="utf-8"))

    def test_the_fixture_is_there(self):
        home = self.make()
        self.assertTrue((home.work / "a.txt").is_file())
        self.assertTrue((home.work / "folder").is_dir())

    def test_removed_when_it_cannot_be_made(self):
        before = set(Path(tempfile.gettempdir()).glob("xefm-try-*"))
        with self.assertRaises(trial.TryError):
            trial.TryHome(self.package, keymap="emacs")
        (self.package / ext.MANIFEST).write_text("[extension]\nid = 'Bad Id'\n",
                                                 encoding="utf-8")
        with self.assertRaises((ext.InstallError, ext.ManifestError)):
            trial.TryHome(self.package, keymap="afx")
        self.assertEqual(set(Path(tempfile.gettempdir()).glob("xefm-try-*")), before)

    def test_the_xefm_that_runs_is_the_terminal_one(self):
        argv = trial.xefm_argv(Path("/l"), Path("/r"))
        self.assertEqual(argv[argv.index("--backend") + 1], "tui")
        self.assertEqual(argv[-4:], ["--left", "/l", "--right", "/r"])


@unittest.skipUnless(HAVE_KEYS, "needs quality-loop")
class Script(_Tmp):
    def read(self, value):
        path = self.tmp / "steps.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return trial.read_script(path)

    def test_reads_steps(self):
        steps = self.read([{"intent": "palette", "keys": ["Ctrl-T"]},
                           {"keys": [{"text": "hi"}, {"pause": 1}, "Enter"],
                            "patience": 3}])
        self.assertEqual(steps[0].intent, "palette")
        self.assertEqual(len(steps[1].keys), 3)
        self.assertEqual(steps[1].patience, 3.0)

    def test_refuses_what_it_cannot_send(self):
        for bad in ({"keys": ["Ctrl-T"]},              # not a list
                    [{"intent": "no keys"}],
                    [{"keys": ["Hyper-X"]}],
                    [{"keys": ["Cmd-C"]}],               # a terminal has no Cmd
                    [{"keys": ["a"], "wait": 3}]):       # unknown field
            with self.subTest(bad=bad), self.assertRaises(trial.TryError):
                self.read(bad)

    def test_a_bad_script_installs_nothing(self):
        package = ext.scaffold("hello-xefm", self.tmp)
        script = self.tmp / "steps.json"
        script.write_text("[{\"keys\": [\"Cmd-Q\"]}]", encoding="utf-8")
        with unittest.mock.patch.object(trial, "TryHome") as home, \
                redirect_stderr(io.StringIO()) as err:
            code = extension_cli.main(["try", str(package), "--keys", str(script)])
        self.assertEqual(code, 1)
        home.assert_not_called()
        self.assertIn("Cmd", err.getvalue())


class Cli(_Tmp):
    def run_cli(self, *argv):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            return extension_cli.main(["try", str(self.tmp), *argv]), err.getvalue()

    def test_screens_and_record_need_keys(self):
        code, err = self.run_cli("--record", "x.cast")
        self.assertEqual(code, 2)
        self.assertIn("--keys", err)

    def test_size_is_cols_by_rows(self):
        code, err = self.run_cli("--size", "big")
        self.assertEqual(code, 2)
        self.assertIn("COLSxROWS", err)


class Recording(_Tmp):
    def test_is_an_asciicast_v2_with_chapters(self):
        path = self.tmp / "s.cast"
        rec = trial.Recording(path, rows=34, cols=120)
        snow = "❄".encode()
        rec.output(b"a" + snow[:1])      # a read that ends inside a character
        rec.output(snow[1:] + b"b")
        rec.marker("1: open")
        rec.close()
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual((lines[0]["version"], lines[0]["width"], lines[0]["height"]),
                         (2, 120, 34))
        text = "".join(e[2] for e in lines[1:] if e[1] == "o")
        self.assertEqual(text, "a❄b")
        self.assertEqual([e[1:] for e in lines if isinstance(e, list) and e[1] == "m"],
                         [["m", "1: open"]])
        times = [e[0] for e in lines[1:]]
        self.assertEqual(times, sorted(times))


class EventLog(_Tmp):
    def setUp(self):
        super().setUp()
        self.path = self.tmp / "events.jsonl"
        patcher = unittest.mock.patch.dict(os.environ, {event_log.EVENTS_ENV: str(self.path)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def events(self):
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def test_writes_one_json_line_per_event(self):
        event_log.write("message", source="info", text="Hello, ☃")
        (event,) = self.events()
        self.assertEqual((event["kind"], event["source"], event["text"]),
                         ("message", "info", "Hello, ☃"))
        self.assertIsInstance(event["t"], float)

    def test_nothing_without_the_variable(self):
        with unittest.mock.patch.dict(os.environ, {event_log.EVENTS_ENV: ""}):
            event_log.write("message", text="x")
        self.assertFalse(self.path.exists())

    def test_never_raises(self):
        with unittest.mock.patch.dict(os.environ,
                                      {event_log.EVENTS_ENV: str(self.tmp / "no" / "dir")}):
            event_log.write("message", text="x")

    def test_a_logged_exception_is_an_event(self):
        logger = logging.getLogger("EventLogTest")
        handler = log_manager._LogSinkHandler()
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        logger.propagate = False
        with redirect_stderr(io.StringIO()):
            try:
                raise ValueError("boom")
            except ValueError:
                logger.exception("Action failed")
            logger.error("no traceback here")
        (event,) = self.events()
        self.assertEqual((event["kind"], event["logger"], event["text"]),
                         ("exception", "EventLogTest", "Action failed"))
        self.assertIn("ValueError: boom", event["traceback"])


if __name__ == "__main__":
    unittest.main()
