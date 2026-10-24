import sys
import unittest

from tests import fakewin  # installs the fake winapi before closeall.core is imported
from closeall import core
from tests.test_core import FakeClock


def make_system():
    system = fakewin.FakeSystem()
    system.add_process(10, r"C:\Windows\explorer.exe", created=100)          # the shell
    system.add_process(11, r"C:\Windows\explorer.exe", created=110)          # separate folder windows
    system.add_process(12, r"C:\Windows\explorer.exe", created=120, session=2)  # another user's shell
    system.add_process(20, r"C:\Windows\notepad.exe", created=200)
    return fakewin.install(system)


class RestartExplorerTests(unittest.TestCase):
    def setUp(self):
        self.system = make_system()
        self.clock = FakeClock()

    def alive(self, pid):
        return self.system.processes[pid]["alive"]

    def test_windows_restarts_the_shell(self):
        def sleep(seconds):
            self.clock.sleep(seconds)
            if self.clock.now >= 1 and 30 not in self.system.processes:
                self.system.add_process(30, r"C:\Windows\explorer.exe", created=300)   # winlogon

        result = core.restart_explorer(sleep=sleep, clock=self.clock)
        self.assertEqual(result, "restarted")
        self.assertEqual(sorted(pid for pid, _ in self.system.terminated), [10, 11])
        self.assertTrue(all(code == 1 for _, code in self.system.terminated))   # "unexpected" exit
        self.assertTrue(self.alive(12) and self.alive(20))
        self.assertNotIn(("start_explorer", None), self.system.calls)
        self.assertLess(self.clock.now, core.EXPLORER_RESTART_WAIT)

    def test_started_when_windows_does_not(self):
        result = core.restart_explorer(sleep=self.clock.sleep, clock=self.clock)
        self.assertEqual(result, "started")
        self.assertIn(("start_explorer", None), self.system.calls)
        self.assertGreaterEqual(self.clock.now, core.EXPLORER_RESTART_WAIT)

    def test_no_shell_running_starts_it(self):
        for pid in (10, 11):
            self.system.processes[pid]["alive"] = False
        self.assertEqual(core.restart_explorer(wait=0, sleep=self.clock.sleep, clock=self.clock), "started")

    def test_access_denied(self):
        for pid in (10, 11):
            self.system.processes[pid]["deny"] = True
        with self.assertRaises(core.ProcessError) as ctx:
            core.restart_explorer(sleep=self.clock.sleep, clock=self.clock)
        self.assertEqual(ctx.exception.key, "access_denied")
        self.assertNotIn(("start_explorer", None), self.system.calls)

    def test_one_stopped_is_enough(self):
        self.system.processes[11]["deny"] = True
        self.assertEqual(core.restart_explorer(wait=0, sleep=self.clock.sleep, clock=self.clock), "started")
        self.assertEqual([pid for pid, _ in self.system.terminated], [10])


class ElevatedRestartTests(unittest.TestCase):
    """Running as administrator, explorer.exe must never be started from here (elevated shell)."""

    def setUp(self):
        self.system = make_system()
        self.system.admin = True
        self.clock = FakeClock()

    def test_never_started_when_elevated(self):
        with self.assertRaises(core.ProcessError) as ctx:
            core.restart_explorer(sleep=self.clock.sleep, clock=self.clock)
        self.assertEqual(ctx.exception.key, "explorer_not_restarted")
        self.assertNotIn(("start_explorer", None), self.system.calls)
        self.assertGreaterEqual(self.clock.now, core.EXPLORER_RESTART_WAIT_ELEVATED)   # waited longer for Windows

    def test_windows_restart_is_still_fine(self):
        def sleep(seconds):
            self.clock.sleep(seconds)
            if self.clock.now >= 12 and 30 not in self.system.processes:
                self.system.add_process(30, r"C:\Windows\explorer.exe", created=300)

        self.assertEqual(core.restart_explorer(sleep=sleep, clock=self.clock), "restarted")

    def test_message_exists(self):
        from closeall import i18n
        for language in ("en", "fr"):
            self.assertIn("Ctrl", i18n.translate(language, "explorer_not_restarted", detail=""))


if __name__ == "__main__":
    unittest.main()


class ElevationFolderTests(unittest.TestCase):
    def setUp(self):
        self.system = fakewin.install(fakewin.FakeSystem())

    def test_program_files_is_safe(self):
        self.assertEqual(core.unprotected_elevation_files(), [])
        self.system.elevation = [r"c:\program files (x86)\CloseAllPython\CloseAllPython.exe"]
        self.assertEqual(core.unprotected_elevation_files(), [])

    def test_user_folders_are_reported(self):
        exe = r"C:\Users\me\Downloads\CloseAllPython.exe"
        self.system.elevation = [exe]
        self.assertEqual(core.unprotected_elevation_files(), [exe])
        # a look-alike name next to Program Files is not inside it, and ".." does not climb into it
        for path in (r"C:\Program Files Evil\CloseAllPython.exe",
                     r"C:\Program Files\..\Users\me\CloseAllPython.exe"):
            self.system.elevation = [path]
            self.assertEqual(core.unprotected_elevation_files(), [path], path)

    def test_from_source_both_files_are_checked(self):
        script = r"C:\Users\me\code\closeallpython.py"
        self.system.elevation = [r"C:\Program Files\Python314\pythonw.exe", script]
        self.assertEqual(core.unprotected_elevation_files(), [script])

    def test_unreadable_folders(self):
        def broken():
            raise OSError(5, "denied")

        sys.modules["closeall.winapi"].protected_folders = broken
        self.assertEqual(core.unprotected_elevation_files(), self.system.elevation)   # warn rather than trust
