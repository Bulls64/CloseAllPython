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


if __name__ == "__main__":
    unittest.main()
