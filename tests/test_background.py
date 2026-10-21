import os
import sys
import unittest

from tests import fakewin  # installs the fake winapi before closeall.core is imported
from closeall import core, i18n

MB = 1024 * 1024


def make_system():
    system = fakewin.FakeSystem()
    system.add_process(0, None, name="", memory=0)
    system.add_process(4, None, name="System", memory=2 * MB)
    system.add_process(90, None, name="Memory Compression", memory=900 * MB)
    system.add_process(10, r"C:\Windows\explorer.exe", memory=150 * MB)
    system.add_process(20, r"C:\Windows\System32\svchost.exe", memory=60 * MB)
    system.add_process(100, r"C:\Program Files\Google\Chrome\chrome.exe", created=1, memory=400 * MB)
    system.add_process(101, r"C:\Program Files\Google\Chrome\chrome.exe", created=2, ppid=100, memory=700 * MB)
    system.add_process(200, r"C:\Users\me\OneDrive\OneDrive.exe", created=3, memory=120 * MB)
    system.add_process(300, r"C:\Program Files\Steam\steam.exe", created=4, memory=250 * MB)
    system.add_process(400, r"C:\Windows\System32\ApplicationFrameHost.exe", memory=30 * MB)
    system.add_process(401, r"C:\Program Files\WindowsApps\Calc\Calculator.exe", memory=40 * MB)
    system.add_process(500, r"C:\Program Files\Defender\MsMpEng.exe", memory=300 * MB, deny=True)
    system.add_process(600, r"C:\Tools\tiny.exe", created=6, memory=1 * MB)
    system.add_window(1, 100, "Inbox - Chrome")
    system.add_window(2, 400, "Calculator")
    system.uwp[2] = 401
    return fakewin.install(system)


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        self.system = make_system()
        self.windows = core.list_windows()

    def names(self, report):
        return [p.name for p in report.top]

    def test_top_is_sorted_and_skips_windowed_apps(self):
        report = core.background_processes(self.windows)
        # chrome.exe (the window and its helper), the UWP frame host and app, and Windows are left out
        self.assertEqual(self.names(report), ["MsMpEng.exe", "steam.exe", "OneDrive.exe", "tiny.exe"])
        self.assertEqual(report.top[0].memory, 300 * MB)
        self.assertEqual(report.count, 4)
        self.assertEqual(report.total, (300 + 250 + 120 + 1) * MB)

    def test_paths_and_access_denied(self):
        report = core.background_processes(self.windows)
        by_name = {p.name: p for p in report.top}
        self.assertEqual(by_name["steam.exe"].exe_path, r"C:\Program Files\Steam\steam.exe")
        self.assertIsNone(by_name["MsMpEng.exe"].exe_path)   # still listed with its image name
        self.assertEqual(by_name["steam.exe"].app_name, "steam")

    def test_include_system(self):
        report = core.background_processes(self.windows, include_system=True)
        self.assertEqual(self.names(report)[:3], ["Memory Compression", "MsMpEng.exe", "steam.exe"])
        self.assertIn("explorer.exe", self.names(report))
        protected = {p.name for p in report.top if p.protected}
        self.assertEqual(protected, {"Memory Compression", "explorer.exe", "svchost.exe", "System"})
        self.assertNotIn("", self.names(report))   # the idle process
        self.assertIsNone(report.top[0].exe_path)

    def test_limit(self):
        self.assertEqual(len(core.background_processes(self.windows, include_system=True, limit=3).top), 3)
        for pid in range(1000, 1020):
            self.system.add_process(pid, rf"C:\Bg\app{pid}.exe", memory=pid)
        self.assertEqual(len(core.background_processes(self.windows).top), core.BACKGROUND_LIMIT)

    def test_same_executable_without_a_parent_window_is_listed(self):
        # A Python service must not vanish because a Python program has a window.
        self.system.add_process(700, r"C:\Python\python.exe", created=7, memory=30 * MB)
        self.system.add_process(701, r"C:\Python\python.exe", created=8, ppid=20, memory=900 * MB)
        self.system.add_window(7, 700, "IDLE Shell")
        report = core.background_processes(core.list_windows())
        self.assertEqual((report.top[0].pid, report.top[0].memory), (701, 900 * MB))
        self.assertNotIn(700, [p.pid for p in report.top])

    def test_helpers_of_helpers_stay_with_the_application(self):
        self.system.add_process(102, r"C:\Program Files\Google\Chrome\chrome.exe", created=9, ppid=101,
                                memory=500 * MB)
        self.assertNotIn("chrome.exe", self.names(core.background_processes(self.windows)))

    def test_children_of_explorer_are_listed_when_explorer_has_a_window(self):
        self.system.add_window(3, 10, "Documents")   # a folder window: explorer.exe is windowed
        self.system.add_process(201, r"C:\Apps\tray.exe", created=11, ppid=10, memory=80 * MB)
        windows = core.list_windows()
        self.assertIn("tray.exe", self.names(core.background_processes(windows)))

    def test_reused_parent_pid_does_not_hide_a_process(self):
        # The parent PID now belongs to a newer, windowed process: not the real parent.
        self.system.add_process(900, r"C:\Apps\editor.exe", created=50)
        self.system.add_window(9, 900, "Editor")
        self.system.add_process(901, r"C:\Apps\sync.exe", created=40, ppid=900, memory=70 * MB)
        self.assertIn("sync.exe", self.names(core.background_processes(core.list_windows())))

    def test_closeallpython_itself_is_never_listed(self):
        self.system.add_process(950, r"C:\Tools\CloseAllPython.exe", created=60, memory=900 * MB)
        self.assertNotIn("CloseAllPython.exe", self.names(core.background_processes(self.windows)))

    def test_reused_pid_hides_the_path(self):
        system = fakewin.FakeSystem()
        system.add_process(700, r"C:\Apps\other.exe", created=99, memory=10 * MB)
        fakewin.install(system)
        module = sys.modules["closeall.winapi"]
        original = module.system_processes
        module.system_processes = lambda: [p._replace(created=42) for p in original()]
        report = core.background_processes([])
        self.assertIsNone(report.top[0].exe_path)


class FormatTests(unittest.TestCase):
    def test_memory_sizes(self):
        self.assertEqual(i18n.format_memory("en", 412 * MB), "412 MB")
        self.assertEqual(i18n.format_memory("fr", 412 * MB), "412 Mo")
        self.assertEqual(i18n.format_memory("en", int(1.3 * 1024 * MB)), "1.3 GB")
        self.assertEqual(i18n.format_memory("fr", int(1.3 * 1024 * MB)), "1,3 Go")
        self.assertEqual(i18n.format_memory("fr", 300 * 1024), "0,3 Mo")
        self.assertEqual(i18n.format_memory("en", 0), "0 MB")


@unittest.skipUnless(sys.platform == "win32", "needs Windows")
class WindowsProcessListTests(unittest.TestCase):
    def test_this_process_is_read_correctly(self):
        import importlib.util

        # tests.fakewin replaced closeall.winapi: load the real module from its file.
        path = os.path.join(os.path.dirname(core.__file__), "winapi.py")
        spec = importlib.util.spec_from_file_location("real_winapi", path)
        winapi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(winapi)
        processes = {p.pid: p for p in winapi.system_processes()}
        me = processes[os.getpid()]
        self.assertTrue(me.name.lower().startswith("python"), me.name)
        self.assertEqual(me.ppid, os.getppid())
        self.assertGreater(me.private_memory, 1024 * 1024)
        self.assertGreaterEqual(me.working_set, me.private_memory)
        # same creation time as GetProcessTimes: the structure layout is right
        self.assertEqual(me.created, winapi.process_info(os.getpid())[1])
        self.assertIn(4, processes)
        self.assertEqual(me.session, winapi.current_session())
        windows = winapi.windows_directory()
        self.assertTrue(os.path.isfile(os.path.join(windows, "explorer.exe")), windows)


class SummaryTests(unittest.TestCase):
    def test_singular_and_plural(self):
        self.assertEqual(i18n.translate_n("fr", "background_top", 1), "Celui qui utilise le plus de mémoire")
        self.assertEqual(i18n.translate_n("fr", "background_top", 10), "Les 10 qui utilisent le plus de mémoire")
        self.assertEqual(i18n.translate_n("en", "background_top", 1), "The one using the most memory")
        self.assertEqual(i18n.translate_n("en", "background_count", 1, total="3 MB"),
                         "1 process without a window, 3 MB in all")


if __name__ == "__main__":
    unittest.main()
