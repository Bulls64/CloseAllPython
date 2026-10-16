import contextlib
import io
import os
import string
import tempfile
import unittest
from pathlib import Path

from tests import fakewin  # noqa: F401  (fake winapi first)
from tests.test_core import make_system
from closeall import cli, settings
from closeall.i18n import TEXT


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


class TranslationTests(unittest.TestCase):
    def test_languages_have_the_same_keys_and_placeholders(self):
        english = TEXT["en"]
        for language, table in TEXT.items():
            self.assertEqual(set(table), set(english), language)
            for key, text in table.items():
                self.assertEqual(placeholders(text), placeholders(english[key]), f"{language}:{key}")


class PluralTests(unittest.TestCase):
    def test_plural_and_number_format(self):
        from closeall.i18n import format_seconds, translate_n
        self.assertEqual(translate_n("en", "n_windows", 1), "1 window")
        self.assertEqual(translate_n("en", "n_windows", 0), "0 windows")
        self.assertEqual(translate_n("fr", "n_windows", 0), "0 fenêtre")
        self.assertEqual(translate_n("fr", "n_windows", 3), "3 fenêtres")
        self.assertEqual(format_seconds("fr", 1.25), "1,2")
        self.assertEqual(format_seconds("en", 5.0), "5")

    def test_plural_pairs_are_complete(self):
        for table in TEXT.values():
            for key in table:
                if key.endswith("_one"):
                    self.assertIn(key[:-4] + "_many", table)
                if key.endswith("_many"):
                    self.assertIn(key[:-5] + "_one", table)


class SettingsTests(unittest.TestCase):
    def test_strings_are_not_accepted_as_booleans(self):
        values = settings.parse_settings({"group_by_app": "false", "show_icons": False})
        self.assertTrue(values["group_by_app"])      # default kept, "false" is not a boolean
        self.assertFalse(values["show_icons"])

    def test_theme_and_migration_from_dark_mode(self):
        self.assertEqual(settings.parse_settings({})["theme"], "system")
        self.assertEqual(settings.parse_settings({"theme": "dark"})["theme"], "dark")
        self.assertEqual(settings.parse_settings({"theme": "blue"})["theme"], "system")
        self.assertEqual(settings.parse_settings({"dark_mode": True})["theme"], "dark")
        self.assertEqual(settings.parse_settings({"dark_mode": False})["theme"], "light")

    def test_invalid_values_fall_back_to_defaults(self):
        values = settings.parse_settings({"language": "de", "close_timeout": True})
        self.assertEqual(values["language"], "en")
        self.assertEqual(values["close_timeout"], settings.DEFAULT_SETTINGS["close_timeout"])
        self.assertEqual(settings.parse_settings({"close_timeout": 999})["close_timeout"], 5)
        self.assertEqual(settings.parse_settings([1, 2]), settings.DEFAULT_SETTINGS)

    def test_round_trip_is_atomic(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sub" / "settings.json"
            settings.save_settings({"language": "fr", "close_timeout": 10}, path)
            self.assertEqual(os.listdir(path.parent), ["settings.json"])
            loaded = settings.load_settings(path)
            self.assertEqual((loaded["language"], loaded["close_timeout"]), ("fr", 10))
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual(settings.load_settings(path), settings.DEFAULT_SETTINGS)


class ParseTests(unittest.TestCase):
    def parse(self, *argv):
        with contextlib.redirect_stderr(io.StringIO()):
            return cli.parse_args(list(argv), "en")

    def assertRejected(self, *argv):
        with self.assertRaises(SystemExit) as caught:
            self.parse(*argv)
        self.assertEqual(caught.exception.code, 2)

    def test_dangerous_or_inconsistent_arguments_are_rejected(self):
        self.assertRejected("--no-ui")                        # no implicit "close everything"
        self.assertRejected("--no-ui", "--close", "")
        self.assertRejected("--no-ui", "--close", "   ")
        self.assertRejected("--close", "chrome")              # needs --no-ui
        self.assertRejected("--no-ui", "--close", "a", "--all")
        self.assertRejected("--no-ui", "--all", "--timeout", "-1")

    def test_valid_arguments(self):
        args = self.parse("--no-ui", "--close", "chrome", "--yes", "--force", "--timeout", "3")
        self.assertEqual((args.close, args.yes, args.force, args.timeout), ("chrome", True, True, 3))
        self.assertFalse(self.parse().no_ui)


class FakeTty(io.StringIO):
    def isatty(self):
        return True


class RunCliTests(unittest.TestCase):
    def setUp(self):
        self.system = make_system()
        self.prefs = settings.parse_settings({})

    def run_cli(self, *argv, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        args = cli.parse_args(list(argv), "en")
        code = cli.run_cli(args, self.prefs, out=out, err=err, stdin=stdin or io.StringIO())
        return code, out.getvalue(), err.getvalue()

    def test_requires_confirmation_without_a_console(self):
        code, _, err = self.run_cli("--no-ui", "--close", "notepad")
        self.assertEqual(code, 2)
        self.assertIn("--yes", err)
        self.assertEqual(self.system.posted, [])

    def test_dry_run_changes_nothing(self):
        code, out, _ = self.run_cli("--no-ui", "--all", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("notepad", out)
        self.assertEqual((self.system.posted, self.system.terminated), ([], []))

    def test_all_skips_protected_and_own_terminal(self):
        code, out, err = self.run_cli("--no-ui", "--all", "--yes", "--force", "--timeout", "0")
        self.assertEqual(code, 0)
        self.assertIn("Skipped protected process 500", err)
        self.assertTrue(self.system.processes[500]["alive"])  # protected shell process
        self.assertTrue(self.system.processes[10]["alive"])   # explorer
        self.assertTrue(self.system.processes[50]["alive"])   # terminal running the CLI
        self.assertTrue(self.system.processes[300]["alive"])  # ApplicationFrameHost
        self.assertFalse(self.system.processes[100]["alive"])
        self.assertIn("3 force-stopped", out)

    def test_interactive_refusal(self):
        code, out, _ = self.run_cli("--no-ui", "--close", "notepad", stdin=FakeTty("n\n"))
        self.assertEqual(code, 1)
        self.assertIn("Aborted", out)
        self.assertEqual(self.system.posted, [])

    def test_interactive_french_yes(self):
        self.prefs["language"] = "fr"
        code, out, _ = self.run_cli("--no-ui", "--close", "notepad", "--graceful", stdin=FakeTty("oui\n"))
        self.assertEqual(code, 0)
        self.assertIn("Fermé 100", out)

    def test_survivor_gives_exit_code_1(self):
        code, _, err = self.run_cli("--no-ui", "--close", "editor", "--yes", "--graceful", "--timeout", "0")
        self.assertEqual(code, 1)
        self.assertIn("--force", err)

    def test_default_is_instant_force_without_close_request(self):
        code, out, _ = self.run_cli("--no-ui", "--close", "editor", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(self.system.posted, [])
        self.assertFalse(self.system.processes[200]["alive"])
        self.assertIn("1 force-stopped", out)

    def test_close_explorer_only_posts_to_explorer_windows(self):
        self.system.add_window(21, 10, "Documents", cls="CabinetWClass")
        code, out, _ = self.run_cli("--no-ui", "--close-explorer", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(self.system.posted, [21])
        self.assertEqual(self.system.terminated, [])
        self.assertIn("1 File Explorer window", out)

    def test_force_and_graceful_are_exclusive(self):
        with self.assertRaises(SystemExit):
            cli.parse_args(["--no-ui", "--all", "--force", "--graceful"], "en")

    def test_instant_force_setting_defaults_on_and_is_strict(self):
        self.assertTrue(settings.parse_settings({})["instant_force"])
        self.assertFalse(settings.parse_settings({"instant_force": False})["instant_force"])
        self.assertTrue(settings.parse_settings({"instant_force": "false"})["instant_force"])

    def test_no_match(self):
        code, out, _ = self.run_cli("--no-ui", "--close", "nothing-like-this", "--yes")
        self.assertEqual(code, 0)
        self.assertIn("No matching window", out)


if __name__ == "__main__":
    unittest.main()


class CrashReportTests(unittest.TestCase):
    """Failures must be visible: the windowed executable has no console."""

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.old_appdata = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self.folder

    def tearDown(self):
        if self.old_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self.old_appdata

    def test_report_is_written_next_to_the_settings(self):
        from closeall import crash
        path = crash.write_report("Traceback...\nValueError: boom\n")
        self.assertEqual(path, Path(self.folder) / "CloseAllPython" / "crash.txt")
        self.assertIn("ValueError: boom", path.read_text(encoding="utf-8"))

    def test_startup_failure_shows_the_reason(self):
        import sys
        import types
        from closeall import crash
        shown = []
        fake_gui = types.ModuleType("closeall.gui")

        def failing_main():
            raise RuntimeError("no display")

        fake_gui.main = failing_main
        real_box, real_gui = crash.message_box, sys.modules.get("closeall.gui")
        crash.message_box = lambda text, title="CloseAllPython": shown.append(text)
        sys.modules["closeall.gui"] = fake_gui
        import closeall
        real_attr = getattr(closeall, "gui", None)
        closeall.gui = fake_gui
        try:
            self.assertEqual(cli.run([]), 1)
        finally:
            crash.message_box = real_box
            if real_gui is None:
                sys.modules.pop("closeall.gui", None)
            else:
                sys.modules["closeall.gui"] = real_gui
            if real_attr is None:
                del closeall.gui
            else:
                closeall.gui = real_attr
        self.assertEqual(len(shown), 1)
        self.assertIn("RuntimeError: no display", shown[0])
        self.assertIn("crash.txt", shown[0])
