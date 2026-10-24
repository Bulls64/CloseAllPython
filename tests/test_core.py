import os
import unittest

from tests import fakewin  # installs the fake winapi before closeall.core is imported
from closeall import core

ME = os.getpid()


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def make_system():
    system = fakewin.FakeSystem()
    system.add_process(ME, r"C:\Tools\CloseAllPython.exe", ppid=50)
    system.add_process(50, r"C:\Windows\System32\cmd.exe", ppid=10)
    system.add_process(10, r"C:\Windows\explorer.exe")
    system.add_process(100, r"C:\Windows\notepad.exe", created=111)
    system.add_process(200, r"C:\Apps\editor.exe", created=222, exits_on_close=False)
    system.add_process(300, r"C:\Windows\System32\ApplicationFrameHost.exe", created=333)
    system.add_process(400, r"C:\Program Files\WindowsApps\Calc\Calculator.exe", created=444)
    system.add_process(500, r"C:\Windows\SystemApps\TextInputHost.exe", created=555)
    system.add_window(1, 10, "Program Manager")
    system.add_window(2, 100, "notes.txt - Notepad")
    system.add_window(3, 100, "todo.txt - Notepad")
    system.add_window(4, 200, "Editor")
    system.add_window(5, 300, "Calculator")
    system.add_window(6, ME, "CloseAllPython")
    system.add_window(7, 50, "Command Prompt")
    system.add_window(8, 100, "hidden helper", task=False)
    system.add_window(9, 100, "   ")
    system.add_window(10, 500, "Microsoft Text Input Application")
    system.uwp[5] = 400
    return fakewin.install(system)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.system = make_system()

    def test_lists_task_windows_only_and_resolves_uwp(self):
        windows = core.list_windows(frozenset({ME}))
        titles = {w.title for w in windows}
        self.assertNotIn("hidden helper", titles)
        self.assertNotIn("CloseAllPython", titles)
        self.assertNotIn("", titles)
        calc = next(w for w in windows if w.title == "Calculator")
        self.assertEqual((calc.pid, calc.hwnd_pid, calc.app_name), (400, 300, "Calculator"))
        self.assertFalse(calc.protected)

    def test_explorer_is_listed_but_protected(self):
        explorer = next(w for w in core.list_windows() if w.title == "Program Manager")
        self.assertTrue(explorer.protected)

    def test_cli_excludes_its_ancestors(self):
        pids = core.own_pids(include_ancestors=True)
        self.assertTrue({ME, 50, 10} <= pids)
        titles = {w.title for w in core.list_windows(pids)}
        self.assertNotIn("Command Prompt", titles)

    def test_gui_does_not_exclude_unrelated_parent(self):
        self.assertEqual(core.own_pids(include_ancestors=False), frozenset({ME}))

    def test_gui_excludes_pyinstaller_bootloader(self):
        self.system.processes[ME]["ppid"] = 60
        self.system.add_process(60, r"C:\Tools\CloseAllPython.exe")
        self.assertEqual(core.own_pids(include_ancestors=False), frozenset({ME, 60}))

    def test_filter_rejects_empty_pattern(self):
        with self.assertRaises(ValueError):
            core.filter_by_title(core.list_windows(), "  ")
        matches = core.filter_by_title(core.list_windows(), "NOTEPAD")
        self.assertEqual(len(matches), 2)

    def test_group_targets_one_per_process(self):
        targets = core.group_targets(core.filter_by_title(core.list_windows(), "notepad"))
        self.assertEqual(len(targets), 1)
        self.assertEqual(sorted(targets[0].titles), ["notes.txt - Notepad", "todo.txt - Notepad"])

    def test_truncate(self):
        self.assertEqual(core.truncate(range(5), 3), ([0, 1, 2], 2))
        self.assertEqual(core.truncate([1], 3), ([1], 0))


class ShutdownTests(unittest.TestCase):
    def setUp(self):
        self.system = make_system()
        self.clock = FakeClock()
        self.windows = core.list_windows(frozenset({ME}))

    def targets(self, text):
        return core.group_targets(core.filter_by_title(self.windows, text))

    def close(self, targets, force=False, timeout=5):
        return core.close_processes(targets, timeout, force=force, sleep=self.clock.sleep, clock=self.clock)

    def test_graceful_close_posts_wm_close_to_every_window(self):
        [result] = self.close(self.targets("notepad"))
        self.assertEqual(result.status, core.CLOSED)
        self.assertEqual(sorted(self.system.posted), [2, 3])
        self.assertEqual(self.system.terminated, [])

    def test_survivor_is_reported_not_killed_without_force(self):
        [result] = self.close(self.targets("editor"))
        self.assertEqual(result.status, core.STILL_RUNNING)
        self.assertEqual(self.system.terminated, [])
        self.assertGreaterEqual(self.clock.now, 5)

    def test_survivor_is_force_stopped_with_force_and_nonzero_exit_code(self):
        [result] = self.close(self.targets("editor"), force=True)
        self.assertEqual(result.status, core.FORCED)
        self.assertEqual(self.system.terminated, [(200, 1)])

    def test_uwp_app_closes_through_its_frame_without_touching_frame_host(self):
        [result] = self.close(self.targets("calculator"))
        self.assertEqual(result.status, core.CLOSED)
        self.assertEqual(self.system.posted, [5])
        self.assertTrue(self.system.processes[300]["alive"])

    def test_protected_process_is_never_touched(self):
        [result] = self.close(self.targets("program manager"), force=True)
        self.assertEqual(result.status, core.PROTECTED)
        self.assertEqual((self.system.posted, self.system.terminated), ([], []))

    def test_pid_reuse_is_detected(self):
        targets = self.targets("editor")
        self.system.processes[200]["created"] = 999  # PID 200 now belongs to another process
        [result] = self.close(targets, force=True)
        self.assertEqual((result.status, result.error_key), (core.FAILED, "process_changed"))
        self.assertEqual(self.system.terminated, [])

    def test_already_exited_counts_as_closed(self):
        targets = self.targets("editor")
        self.system.processes[200]["alive"] = False
        [result] = self.close(targets)
        self.assertEqual(result.status, core.CLOSED)

    def test_access_denied_is_reported(self):
        targets = self.targets("editor")
        self.system.processes[200]["deny"] = True
        [result] = self.close(targets, force=True)
        self.assertEqual((result.status, result.error_key), (core.FAILED, "access_denied"))

    def test_unverifiable_process_is_refused(self):
        target = core.Target(200, 0, r"C:\Apps\editor.exe", ["Editor"])
        [result] = self.close([target], force=True)
        self.assertEqual((result.status, result.error_key), (core.FAILED, "access_denied"))
        self.assertEqual(self.system.terminated, [])

    def test_force_processes_verifies_again(self):
        [target] = self.targets("editor")
        self.system.processes[200]["created"] = 5
        [result] = core.force_processes([target])
        self.assertEqual(result.error_key, "process_changed")

    def test_results_are_reported_live_with_elapsed_time(self):
        seen = []
        results = self.close(self.targets("notepad") + self.targets("editor"), force=True)
        self.assertEqual(len(results), 2)
        self.system = make_system()
        self.clock = FakeClock()
        self.windows = core.list_windows(frozenset({ME}))
        core.close_processes(self.targets("notepad") + self.targets("editor"), 2, force=False,
                             on_result=seen.append, sleep=self.clock.sleep, clock=self.clock)
        self.assertEqual([r.status for r in seen], [core.CLOSED, core.STILL_RUNNING])
        self.assertEqual(seen[0].elapsed, 0)
        self.assertGreaterEqual(seen[1].elapsed, 2)

    def test_targets_keep_their_windows(self):
        [target] = self.targets("notepad")
        self.assertEqual(sorted(target.hwnds), [2, 3])
        self.assertEqual(sorted(core.windows_of(target)), [2, 3])

    def test_force_processes_reports_live(self):
        seen = []
        core.force_processes(self.targets("editor"), on_result=seen.append)
        self.assertEqual([r.status for r in seen], [core.FORCED])

    def test_force_processes_terminates_everything_before_waiting(self):
        targets = self.targets("notepad") + self.targets("editor")
        self.system.calls.clear()
        results = core.force_processes(targets)
        self.assertEqual([r.status for r in results], [core.FORCED, core.FORCED])
        calls = self.system.calls
        a, b = targets[0].pid, targets[1].pid
        terminate_a = calls.index(("terminate", a))
        terminate_b = calls.index(("terminate", b))
        wait_a = calls.index(("wait", a), terminate_a + 1)
        # The second application is stopped before the program waits for the first one.
        self.assertLess(terminate_b, wait_a, calls)

    def test_graceful_survivors_are_forced_together(self):
        results = self.close(self.targets("editor"), force=True)
        self.assertEqual(results[0].status, core.FORCED)
        self.assertEqual(self.system.terminated, [(200, 1)])

    def test_summarize(self):
        results = self.close(self.targets("notepad") + self.targets("editor"))
        counts = core.summarize(results)
        self.assertEqual((counts[core.CLOSED], counts[core.STILL_RUNNING]), (1, 1))


if __name__ == "__main__":
    unittest.main()


class LogTitleTests(unittest.TestCase):
    def setUp(self):
        make_system()
        self.addCleanup(setattr, core, "log_titles", core.log_titles)
        self.windows = core.list_windows(frozenset({ME}))

    def logged(self):
        targets = core.group_targets(core.filter_by_title(self.windows, "notepad"))
        with self.assertLogs(core.log, "INFO") as logs:
            core.close_processes(targets, 5, force=False, sleep=lambda s: None, clock=FakeClock())
        return logs.output[0]

    def test_titles_stay_out_of_the_log_by_default(self):
        core.log_titles = False
        line = self.logged()
        self.assertIn("windows=2 titles=[]", line)
        self.assertNotIn("notes.txt", line)

    def test_titles_logged_when_allowed(self):
        core.log_titles = True
        self.assertRegex(self.logged(), r"windows=2 titles=\[.*notes\.txt.*\]")


class ExplorerWindowTests(unittest.TestCase):
    def setUp(self):
        self.system = make_system()
        self.system.processes[10]["exits_on_close"] = False   # closing a folder window never ends explorer.exe
        self.system.add_window(21, 10, "Documents", cls="CabinetWClass")
        self.system.add_window(22, 10, "Downloads", cls="CabinetWClass")
        self.system.add_window(23, 10, "Taskbar", cls="Shell_TrayWnd")
        self.system.add_window(24, 10, "Hidden", cls="CabinetWClass", visible=False)
        self.system.add_window(25, 100, "Impostor", cls="CabinetWClass")   # not owned by explorer.exe

    def test_only_file_explorer_folder_windows_are_closed(self):
        self.assertEqual(core.close_explorer_windows(), 2)
        self.assertEqual(sorted(self.system.posted), [21, 22])

    def test_explorer_process_is_never_terminated(self):
        core.close_explorer_windows()
        self.assertEqual(self.system.terminated, [])
        self.assertTrue(self.system.processes[10]["alive"])

    def test_nothing_to_close(self):
        self.system.windows = [w for w in self.system.windows if w["cls"] != "CabinetWClass"]
        self.assertEqual(core.close_explorer_windows(), 0)
