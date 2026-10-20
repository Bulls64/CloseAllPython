import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from closeall import cli, i18n, shortcut


class FakeLink:
    def __init__(self, path):
        self.path, self.saved = path, False

    def Save(self):
        self.saved = True
        Path(self.path).write_bytes(b"lnk")


class FakeShell:
    def __init__(self, desktop, fail=None):
        self.desktop, self.fail, self.links = desktop, fail, []

    def SpecialFolders(self, name):
        assert name == "Desktop"
        return str(self.desktop)

    def CreateShortcut(self, path):
        if self.fail:
            raise self.fail
        link = FakeLink(path)
        self.links.append(link)
        return link


class LauncherTests(unittest.TestCase):
    def test_arguments_are_valid_command_line(self):
        args = cli.parse_args(list(shortcut.ARGUMENTS), "en")
        self.assertTrue(args.no_ui and args.all and args.yes)
        self.assertFalse(args.graceful)   # instant force-stop

    def test_installed_executable(self):
        exe = Path("/apps/CloseAllPython/CloseAllPython.exe")
        spec = shortcut.launcher(exe_path=exe)
        self.assertEqual(spec.target, str(exe))
        self.assertEqual(spec.arguments, "--no-ui --all -y")
        self.assertEqual(spec.directory, str(exe.parent))
        self.assertEqual(spec.icon, f"{exe},0")

    def test_from_source_uses_the_windowless_python(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "python.exe").write_bytes(b"")
            (folder / "pythonw.exe").write_bytes(b"")
            (folder / "app.ico").write_bytes(b"")
            with mock.patch.object(shortcut.updater, "current_executable", return_value=None):
                spec = shortcut.launcher(python=folder / "python.exe", project_dir=folder)
            self.assertEqual(spec.target, str(folder / "pythonw.exe"))
            self.assertEqual(spec.arguments, f'"{folder / "closeallpython.py"}" --no-ui --all -y')
            self.assertEqual(spec.directory, str(folder))
            self.assertEqual(spec.icon, f"{folder / 'app.ico'},0")

    def test_from_source_without_pythonw(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            with mock.patch.object(shortcut.updater, "current_executable", return_value=None):
                spec = shortcut.launcher(python=folder / "python.exe", project_dir=folder)
            self.assertEqual(spec.target, str(folder / "python.exe"))
            self.assertEqual(spec.icon, f"{folder / 'python.exe'},0")


class CreateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.desktop = Path(self.dir.name)
        self.addCleanup(self.dir.cleanup)

    def test_create_writes_the_shortcut_on_the_desktop(self):
        shell = FakeShell(self.desktop)
        exe = Path("/apps/CloseAllPython.exe")
        with mock.patch.object(shortcut.updater, "current_executable", return_value=exe):
            path = shortcut.create("Close everything", "Closes all", factory=lambda: shell)
        self.assertEqual(path, self.desktop / "Close everything.lnk")
        (link,) = shell.links
        self.assertTrue(link.saved)
        self.assertEqual((link.TargetPath, link.Arguments), (str(exe), "--no-ui --all -y"))
        self.assertEqual((link.Description, link.WindowStyle), ("Closes all", shortcut.WINDOW_MINIMIZED))

    def test_create_again_replaces_it(self):
        shell = FakeShell(self.desktop)
        with mock.patch.object(shortcut.updater, "current_executable", return_value=Path("/a/b.exe")):
            first = shortcut.create("Tout fermer", factory=lambda: shell)
            second = shortcut.create("Tout fermer", factory=lambda: shell)
        self.assertEqual(first, second)
        self.assertEqual(len(list(self.desktop.iterdir())), 1)

    def test_failure_is_reported(self):
        shell = FakeShell(self.desktop, fail=PermissionError(13, "Access is denied"))
        with self.assertRaises(shortcut.ShortcutError) as ctx:
            shortcut.create("Tout fermer", factory=lambda: shell)
        self.assertEqual(ctx.exception.detail, "Access is denied")

    def test_missing_pywin32_is_reported(self):
        def no_com():
            raise ImportError("No module named 'win32com'")

        with self.assertRaises(shortcut.ShortcutError) as ctx:
            shortcut.create("Tout fermer", factory=no_com)
        self.assertIn("win32com", ctx.exception.detail)

    def test_find(self):
        shell = FakeShell(self.desktop)
        self.assertIsNone(shortcut.find("Tout fermer", factory=lambda: shell))
        (self.desktop / "Tout fermer.lnk").write_bytes(b"lnk")
        self.assertEqual(shortcut.find("Tout fermer", factory=lambda: shell), self.desktop / "Tout fermer.lnk")
        self.assertEqual(shortcut.find("Tout fermer", folder=self.desktop), self.desktop / "Tout fermer.lnk")

    def test_find_any_language(self):
        shell = FakeShell(self.desktop)
        (self.desktop / "Close everything.lnk").write_bytes(b"lnk")
        found = shortcut.find_any(["Tout fermer", "Close everything"], factory=lambda: shell)
        self.assertEqual(found, self.desktop / "Close everything.lnk")
        self.assertIsNone(shortcut.find_any(["Tout fermer"], factory=lambda: shell))

    def test_find_without_desktop(self):
        def broken():
            raise OSError("no shell")

        self.assertIsNone(shortcut.find("Tout fermer", factory=broken))

    def test_file_name_is_safe(self):
        self.assertEqual(shortcut._file_name('a/b:c*"'), "a-b-c--.lnk")
        self.assertEqual(shortcut._file_name(" . "), "CloseAllPython.lnk")


class TextTests(unittest.TestCase):
    def test_texts_exist_in_both_languages(self):
        for language in ("en", "fr"):
            name = i18n.translate(language, "shortcut_name")
            self.assertNotIn("/", name)
            self.assertIn("{path}", i18n.TEXT[language]["shortcut_ready"])
            self.assertIn("{error}", i18n.TEXT[language]["shortcut_failed"])


@unittest.skipUnless(sys.platform == "win32", "needs Windows and pywin32")
class WindowsShortcutTests(unittest.TestCase):
    def test_real_shortcut_round_trip(self):
        import win32com.client

        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(shortcut.updater, "current_executable",
                                   return_value=Path(folder) / "CloseAllPython.exe"):
                path = shortcut.create("Tout fermer", "Description", folder=folder)
            self.assertTrue(path.is_file())
            link = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(path))
            self.assertEqual(Path(link.TargetPath), Path(folder) / "CloseAllPython.exe")
            self.assertEqual(link.Arguments, "--no-ui --all -y")
            self.assertEqual(link.Description, "Description")
            self.assertEqual(shortcut.find("Tout fermer", folder=folder), path)


if __name__ == "__main__":
    unittest.main()
