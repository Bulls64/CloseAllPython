"""Smoke test of the interface: the real window, every page, on the fake Windows of the tests.

Skipped where Tk cannot open a window (no display) or CustomTkinter is not installed. On the
GitHub Windows runner it runs with the other tests.
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

from tests import fakewin  # installs the fake winapi before closeall.core is imported
from tests.test_core import ME

try:
    import customtkinter  # noqa: F401
    import tkinter
    tkinter.Tk().destroy()
    DISPLAY = True
except Exception:   # no CustomTkinter, or no display to open a window on
    DISPLAY = False


@unittest.skipUnless(DISPLAY, "needs CustomTkinter and a display")
class InterfaceSmokeTests(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.data, True)
        patcher = mock.patch.dict(os.environ, {"APPDATA": self.data})
        patcher.start()
        self.addCleanup(patcher.stop)
        system = fakewin.FakeSystem()
        system.add_process(ME, r"C:\Tools\CloseAllPython.exe", created=1)
        system.add_process(2208, r"C:\Windows\System32\notepad.exe", created=2)
        system.add_process(3000, r"C:\Apps\sync.exe", created=3, memory=50 * 1024 * 1024)
        system.add_window(1, 2208, "notes.txt - Notepad")
        system.add_window(2, ME, "CloseAllPython")
        self.system = fakewin.install(system)
        module = sys.modules["closeall.winapi"]
        module.exe_icon_image = lambda path, size: None
        module.file_description = lambda path: None
        from closeall import gui, settings
        self.gui, self.settings = gui, settings
        gui.winapi = module
        gui.core.winapi = module
        self.addCleanup(setattr, gui.core, "log_titles", gui.core.log_titles)
        settings.save_settings({"language": "fr", "theme": "dark"})
        self.app = gui.App()
        self.addCleanup(self.close_app)

    def close_app(self):
        try:
            self.app.destroy()
        except Exception:
            pass

    def pump(self, seconds=0.3, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.update()
            if until and until():
                return True
            time.sleep(0.01)
        return until() if until else True

    def labels(self, widget):
        found = []
        for child in widget.winfo_children():
            if isinstance(child, self.gui.ctk.CTkLabel):
                found.append(child.cget("text"))
            found += self.labels(child)
        return found

    def dialogs(self):
        return [w for w in self.app.winfo_children() if isinstance(w, self.gui.Dialog)]

    def test_every_page_opens(self):
        self.pump()
        entries = self.app.list_page.entries if hasattr(self.app.list_page, "entries") else None
        self.assertIn("notepad", " ".join(self.labels(self.app.list_page)).lower(), entries)
        self.app.show("background")
        page = self.app.pages["background"]
        self.assertTrue(self.pump(5, until=lambda: page.report is not None), "background list never loaded")
        self.assertIn("sync.exe", [p.name for p in page.report.top])
        self.app.show("log")
        self.app.show("settings")
        texts = self.labels(self.app.pages["settings"])
        self.assertIn("github.com/Bulls64/CloseAllPython", texts)
        self.assertIn(self.gui.__version__, texts)

    def test_log_lines_without_titles(self):
        self.pump()
        old = "2026-10-20 10:00:00,1 INFO closed pid=12 exe=C:\\Windows\\notepad.exe titles=['notes.txt - Notepad']"
        new = "2026-10-24 10:00:00,1 INFO closed pid=12 exe=C:\\Windows\\notepad.exe windows=2 titles=[]"
        self.assertIn("notes.txt - Notepad", self.gui.format_log_line(self.app, old))
        self.assertIn("2 fenêtres", self.gui.format_log_line(self.app, new))
        self.app.update_settings(log_window_titles=True)
        self.assertTrue(self.gui.core.log_titles)
        self.app.update_settings(log_window_titles=False)
        self.assertFalse(self.gui.core.log_titles)

    def test_restart_as_admin_warns_outside_program_files(self):
        self.pump()
        self.system.elevation = [r"C:\Users\me\Downloads\CloseAllPython.exe"]
        with mock.patch.object(self.app, "destroy") as destroy:
            self.app.restart_as_admin()
            self.pump()
            [dialog] = self.dialogs()
            self.assertIn(r"C:\Users\me\Downloads", " ".join(self.labels(dialog)))
            self.assertNotIn(("relaunch_as_admin",), self.system.calls)
            dialog.destroy()
            self.system.elevation = [r"C:\Program Files\CloseAllPython\CloseAllPython.exe"]
            self.app.restart_as_admin()
            self.assertIn(("relaunch_as_admin",), self.system.calls)
            destroy.assert_called_once()

    def test_update_errors_are_readable(self):
        self.pump()
        updates = self.app.updates
        updates.status = ("update_failed", {"error": ("update_err_rate_limit", {"time": "15:42"})})
        self.assertIn("15:42", updates.status_text())
        self.assertIn("60", updates.status_text())


if __name__ == "__main__":
    unittest.main()
