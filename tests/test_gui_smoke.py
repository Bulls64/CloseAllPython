"""Smoke test of the interface: the real Qt window, every page, on the fake Windows of the tests.

Skipped where PySide6 is not installed, except on GitHub Actions: there it must run. Without a
display (Linux), Qt draws offscreen.
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

if sys.platform != "win32" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton
    QT = True
except ImportError:
    QT = False


@unittest.skipUnless(QT or os.environ.get("GITHUB_ACTIONS") == "true", "needs PySide6")
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
        self.app = self.open_app()

    def open_app(self):
        app = self.gui.App()
        app.show()
        self.addCleanup(self.close_app, app)
        self.pump(0.2, app=app)
        return app

    def close_app(self, app):
        try:
            app.hide()
            app.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        except RuntimeError:
            pass

    def pump(self, seconds=0.3, until=None, app=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            QApplication.processEvents()
            if until and until():
                return True
            time.sleep(0.01)
        return until() if until else True

    @staticmethod
    def texts(widget):
        return [w.text() for w in widget.findChildren(QLabel) + widget.findChildren(QPushButton)]

    def dialogs(self):
        return [d for d in self.app.findChildren(self.gui.Dialog) if d.isVisible()]

    def test_every_page_opens(self):
        self.assertIn("notepad", " ".join(self.texts(self.app.list_page)).lower())
        self.app.show_page("background")
        page = self.app.pages["background"]
        self.assertTrue(self.pump(5, until=lambda: page.report is not None), "background list never loaded")
        self.assertIn("sync.exe", [p.name for p in page.report.top])
        self.app.show_page("log")
        self.app.show_page("settings")
        texts = self.texts(self.app.pages["settings"])
        self.assertIn("github.com/Bulls64/CloseAllPython", texts)
        self.assertTrue(any(self.gui.__version__ in text for text in texts), texts)

    def test_select_and_close(self):
        page = self.app.list_page
        [card] = [c for c in page.cards.values() if c.entry.name == "notepad"]
        card.check.click()
        self.assertEqual(len(page.selected), 1)
        self.assertTrue(page.close_button.isEnabled())
        page.close_selected()
        [dialog] = self.dialogs()
        self.assertIn("notepad — 1 fenêtre", " ".join(self.texts(dialog)))
        dialog._confirm()
        closing = self.app.pages["closing"]
        self.assertTrue(self.pump(5, until=lambda: not closing.running), "closing never finished")
        self.assertIn(("wait", 2208), self.system.calls)
        closing.finish()
        self.assertEqual(self.app.current, "apps")

    def test_search_filters_the_list(self):
        page = self.app.list_page
        page.search.setText("zzz")
        page.apply_filter()
        self.assertTrue(page.empty.isVisible())
        self.assertIn("zzz", page.empty.text())
        page.search.setText("note")
        page.apply_filter()
        self.assertFalse(page.empty.isVisible())

    def test_log_lines_without_titles(self):
        old = "2026-10-20 10:00:00,1 INFO closed pid=12 exe=C:\\Windows\\notepad.exe titles=['notes.txt - Notepad']"
        new = "2026-10-24 10:00:00,1 INFO closed pid=12 exe=C:\\Windows\\notepad.exe windows=2 titles=[]"
        self.assertIn("notes.txt - Notepad", self.gui.format_log_line(self.app, old))
        self.assertIn("2 fenêtres", self.gui.format_log_line(self.app, new))
        self.app.update_settings(log_window_titles=True)
        self.assertTrue(self.gui.core.log_titles)
        self.app.update_settings(log_window_titles=False)
        self.assertFalse(self.gui.core.log_titles)

    def test_restart_as_admin_warns_outside_program_files(self):
        self.system.elevation = [r"C:\Users\me\Downloads\CloseAllPython.exe"]
        with mock.patch.object(self.app, "close") as close:
            self.app.restart_as_admin()
            [dialog] = self.dialogs()
            self.assertIn(r"C:\Users\me\Downloads", " ".join(self.texts(dialog)))
            self.assertNotIn(("relaunch_as_admin",), self.system.calls)
            dialog.destroy()
            self.assertEqual(self.app.dialogs, 0)
            self.system.elevation = [r"C:\Program Files\CloseAllPython\CloseAllPython.exe"]
            self.app.restart_as_admin()
            self.assertIn(("relaunch_as_admin",), self.system.calls)
            close.assert_called_once()

    def test_language_change_rebuilds_the_window(self):
        self.app.show_page("settings")
        self.app.update_settings(language="en")
        self.pump(0.3)
        self.assertIn("Settings", self.texts(self.app.pages["settings"]))
        self.assertEqual(self.app.current, "settings")

    def test_theme_change_restyles_without_rebuilding(self):
        page = self.app.list_page
        self.assertTrue(self.gui.THEME.dark)
        self.app.update_settings(theme="light")
        self.assertFalse(self.gui.THEME.dark)
        self.assertIs(self.app.list_page, page)
        self.assertIn(("dark_title_bar", False), self.system.calls)

    def test_dark_light_button(self):
        app = self.app
        self.assertTrue(app.is_dark())
        self.assertEqual(app.theme_item.text(), "Mode clair")   # what a click gives
        self.assertEqual(app.theme_item.glyph, "sun")
        app.theme_item.click()
        self.assertEqual(app.settings["theme"], "light")
        self.assertFalse(self.gui.THEME.dark)
        self.assertEqual(app.theme_item.text(), "Mode sombre")
        self.assertEqual(app.theme_item.glyph, "moon")
        self.assertEqual(self.settings.load_settings()["theme"], "light")   # remembered
        app.theme_item.click()
        self.assertEqual(app.settings["theme"], "dark")
        self.assertTrue(self.gui.THEME.dark)
        self.assertFalse(app.theme_item.isChecked())   # an action, never a selected page
        app.show_page("settings")
        self.assertEqual(app.pages["settings"].theme_box.currentText(), "Sombre")
        app.update_settings(language="en")
        self.pump(0.3)
        self.assertEqual(app.theme_item.text(), "Light mode")

    def test_transparency_slider(self):
        self.system.mica = True
        self.app = self.open_app()
        self.app.show_page("settings")
        page = self.app.pages["settings"]
        self.assertTrue(page.level_card.isEnabled())
        before = self.gui.THEME["card"]
        page.level_slider.setValue(100)
        self.assertEqual(page.level_value.text(), "100 %")
        self.pump(0.4, until=lambda: self.app.settings["transparency"] == 100)
        self.assertEqual(self.app.settings["transparency"], 100)
        self.assertNotEqual(self.gui.THEME["card"], before)
        self.assertEqual(self.settings.load_settings()["transparency"], 100)   # remembered
        page.backdrop_box.setCurrentText("Désactivé")
        self.assertFalse(page.level_card.isEnabled())   # nothing to adjust without an effect

    def test_transparency_slider_is_off_without_an_effect(self):
        self.app.show_page("settings")
        self.assertFalse(self.app.pages["settings"].level_card.isEnabled())

    def test_backdrop_follows_the_setting_in_both_themes(self):
        self.system.mica = True
        self.app = self.open_app()
        self.assertTrue(self.app.mica)
        self.assertEqual(self.gui.THEME["window"], "transparent")
        self.assertIn(("set_backdrop", "acrylic"), self.system.calls)   # the default: the most transparent
        self.assertEqual(self.gui.THEME["layer"], "rgba(0, 0, 0, 0.000)")
        self.system.calls.clear()
        self.app.update_settings(theme="light")
        self.assertTrue(self.app.mica)   # in the light theme too
        self.assertIn(("set_backdrop", "acrylic"), self.system.calls)
        self.app.update_settings(backdrop="mica")
        self.assertIn(("set_backdrop", "mica"), self.system.calls)
        self.assertTrue(self.app.mica)
        self.app.update_settings(backdrop="none")
        self.assertFalse(self.app.mica)
        self.assertIn(("set_backdrop", "none"), self.system.calls)
        self.assertEqual(self.gui.THEME["window"], "#f3f3f3")   # opaque again
        self.app.show_page("settings")
        settings = self.app.pages["settings"]
        self.assertIn("Effet de transparence", self.texts(settings))
        settings.backdrop_box.setCurrentText("Mica Alt")
        self.assertEqual(self.app.settings["backdrop"], "mica_alt")

    def test_mica_refused_falls_back_to_an_opaque_window(self):
        self.system.mica = True
        sys.modules["closeall.winapi"].set_backdrop = lambda hwnd, kind: False
        self.app = self.open_app()
        self.assertFalse(self.app.mica)
        self.assertEqual(self.gui.THEME["window"], "#202020")

    def test_without_mica_the_window_is_opaque(self):
        self.assertFalse(self.app.mica)
        self.assertFalse(self.app.translucent)
        self.assertEqual(self.gui.THEME["window"], "#202020")
        self.assertFalse([call for call in self.system.calls if call[0] == "set_backdrop"])

    def test_navigation_pane_folds_in_narrow_windows(self):
        self.app.resize(900, 700)
        self.pump(0.1)
        self.assertTrue(self.app.nav_compact)
        self.app.resize(1200, 700)
        self.pump(0.1)
        self.assertFalse(self.app.nav_compact)
        self.app.toggle_nav()   # the user's choice wins over the width
        self.app.resize(1300, 700)
        self.pump(0.1)
        self.assertTrue(self.app.nav_compact)

    def test_worker_threads_hand_back_to_the_interface(self):
        import threading

        done = []
        threading.Thread(target=lambda: self.app.call_soon(lambda: done.append(threading.current_thread()))).start()
        self.assertTrue(self.pump(2, until=lambda: done))
        self.assertIs(done[0], threading.main_thread())

    def test_update_errors_are_readable(self):
        updates = self.app.updates
        updates.status = ("update_failed", {"error": ("update_err_rate_limit", {"time": "15:42"})})
        self.assertIn("15:42", updates.status_text())
        self.assertIn("60", updates.status_text())


if __name__ == "__main__":
    unittest.main()
