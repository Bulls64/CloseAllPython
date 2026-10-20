"""The desktop shortcut runs `--no-ui --all -y` without a console."""
import io
import unittest
from unittest import mock

from tests import fakewin  # noqa: F401  (installs the fake winapi)
from closeall import cli, shortcut
from tests.test_core import make_system


class WindowlessTests(unittest.TestCase):
    def setUp(self):
        self.system = make_system()
        self.system.add_process(700, r"C:\Tools\CloseAllPython.exe", created=777)    # the GUI the user has open
        self.system.add_window(70, 700, "CloseAllPython 1.9.1")
        self.prefs = {"language": "en", "close_timeout": 5}
        self.args = cli.parse_args(list(shortcut.ARGUMENTS), "en")
        self.shown = []

    def run_windowless(self):
        return cli.run_windowless(self.args, self.prefs, show=self.shown.append)

    def test_all_leaves_closeallpython_open(self):
        out = io.StringIO()
        self.assertEqual(cli.run_cli(self.args, self.prefs, out=out, err=io.StringIO()), 0)
        self.assertNotIn(700, [pid for pid, _ in self.system.terminated])
        self.assertIn(100, [pid for pid, _ in self.system.terminated])   # notepad is closed

    def test_close_pattern_can_still_target_it(self):
        args = cli.parse_args(["--no-ui", "--close", "CloseAllPython 1.9", "-y"], "en")
        cli.run_cli(args, self.prefs, out=io.StringIO(), err=io.StringIO())
        self.assertIn(700, [pid for pid, _ in self.system.terminated])

    def test_success_shows_nothing(self):
        self.assertEqual(self.run_windowless(), 0)
        self.assertEqual(self.shown, [])

    def test_failure_is_shown(self):
        self.system.add_process(800, r"C:\Apps\admin-tool.exe", created=888)
        self.system.add_window(80, 800, "Admin tool")
        real_open = self.system.module().open_process
        module = __import__("sys").modules["closeall.winapi"]

        def open_process(pid, access):
            if pid == 800 and access & module.PROCESS_TERMINATE:
                raise fakewin.FakeWinError(5)
            return real_open(pid, access)

        with mock.patch.object(module, "open_process", open_process):
            self.assertEqual(self.run_windowless(), 1)
        (text,) = self.shown
        self.assertIn("admin-tool", text)
        self.assertIn("access denied", text)
        self.assertIn("1 failed", text)

    def test_many_failures_are_shortened(self):
        problems = [f"line {i}" for i in range(30)]
        with mock.patch.object(cli, "run_cli", lambda *a, problems, **k: problems.extend(problems_src) or 1):
            problems_src = problems
            self.run_windowless()
        lines = self.shown[0].splitlines()
        self.assertIn("…", lines)
        self.assertIn("line 29", lines)
        self.assertLess(len([x for x in lines if x.startswith("line")]), 15)

    def test_entry_point_uses_the_message_box_without_console(self):
        with mock.patch.object(cli.sys, "stdout", None), \
                mock.patch.object(cli, "run_windowless", return_value=0) as windowless, \
                mock.patch.object(cli.settings_mod, "setup_logging"), \
                mock.patch.object(cli.settings_mod, "load_settings", return_value=self.prefs):
            self.assertEqual(cli.run(list(shortcut.ARGUMENTS)), 0)
        windowless.assert_called_once()


if __name__ == "__main__":
    unittest.main()


class SelfTestTests(unittest.TestCase):
    def test_option_stands_alone(self):
        self.assertTrue(cli.parse_args(["--self-test"], "en").self_test)
        for extra in (["--no-ui", "--all"], ["--update"]):
            with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
                cli.parse_args(["--self-test", *extra], "en")

    def test_hidden_from_help(self):
        self.assertNotIn("self-test", cli.build_parser("en").format_help())

    def test_results(self):
        def boom():
            raise RuntimeError("COM missing")

        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(cli.run_self_test(out, err, [("a", lambda: None), ("b", boom)]), 1)
        self.assertIn("ok   a", out.getvalue())
        self.assertIn("FAIL b", err.getvalue())
        self.assertIn("COM missing", err.getvalue())
        self.assertEqual(cli.run_self_test(io.StringIO(), io.StringIO(), [("a", lambda: None)]), 0)

    @unittest.skipUnless(__import__("sys").platform == "win32", "needs Windows")
    def test_real_self_test_from_source(self):
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, str(root / "closeallpython.py"), "--self-test"],
                                capture_output=True, text=True, timeout=120, cwd=root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("self-test: passed", result.stdout)
