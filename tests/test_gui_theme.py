import os
import tempfile
import unittest

from closeall import gui_theme   # plain Python: no Qt needed


class TokenTests(unittest.TestCase):
    def test_light_and_dark_define_the_same_colours(self):
        self.assertEqual(set(gui_theme.LIGHT), set(gui_theme.DARK))

    def test_every_colour_parses(self):
        for palette in (gui_theme.LIGHT, gui_theme.DARK):
            for name, value in palette.items():
                r, g, b, a = gui_theme.parse_rgba(value)
                self.assertTrue(all(0 <= part <= 255 for part in (r, g, b, a)), name)

    def test_parse_rgba(self):
        self.assertEqual(gui_theme.parse_rgba("#202020"), (32, 32, 32, 255))
        self.assertEqual(gui_theme.parse_rgba("rgba(255, 255, 255, 0.051)"), (255, 255, 255, 13))

    def test_window_is_transparent_only_with_mica(self):
        self.assertEqual(gui_theme.Theme(dark=True, mica=True)["window"], "transparent")
        self.assertEqual(gui_theme.Theme(dark=True, mica=False)["window"], "#202020")
        self.assertEqual(gui_theme.Theme(dark=False, mica=False)["window"], "#f3f3f3")

    def test_accent_follows_the_theme(self):
        theme = gui_theme.Theme(dark=False, mica=False, accent=("#003e92", "#99ebff"))
        self.assertEqual(theme["accent"], "#003e92")
        self.assertEqual(gui_theme.Theme(dark=True, mica=False, accent=("#003e92", "#99ebff"))["accent"], "#99ebff")
        self.assertEqual(theme["accent_hover"], "rgba(0, 62, 146, 0.9)")

    def test_accent_from_the_windows_palette(self):
        self.assertEqual(gui_theme.accent_shades(None), gui_theme.DEFAULT_ACCENT)
        self.assertEqual(gui_theme.accent_shades(b"\x00" * 8), gui_theme.DEFAULT_ACCENT)
        palette = bytes(sum(([i * 10, i * 10 + 1, i * 10 + 2, 0] for i in range(8)), []))
        self.assertEqual(gui_theme.accent_shades(palette), ("#28292a", "#0a0b0c"))   # Dark1, Light2

    def test_style_sheet_has_no_missing_token(self):
        for dark in (False, True):
            sheet = gui_theme.Theme(dark=dark, mica=True, icon_font="Segoe Fluent Icons").style_sheet()
            self.assertEqual(sheet.count("{"), sheet.count("}"))
            self.assertNotRegex(sheet, r"\{\w+\}")   # an unformatted placeholder
            self.assertIn("Segoe Fluent Icons", sheet)


class GlyphTests(unittest.TestCase):
    def test_every_glyph_has_a_windows_and_a_fallback_character(self):
        for name, (windows_char, fallback) in gui_theme.GLYPHS.items():
            self.assertTrue(0xE000 <= ord(windows_char) <= 0xF8FF, name)   # icon font private area
            self.assertEqual(len(fallback), 1, name)

    def test_fallback_without_the_icon_font(self):
        self.assertEqual(gui_theme.Theme(dark=True, mica=False).glyph("back"), "←")
        self.assertEqual(gui_theme.Theme(dark=True, mica=False, icon_font="Segoe MDL2 Assets").glyph("back"), "")

    def test_tiles(self):
        self.assertRegex(gui_theme.tile_color("Notepad"), r"^#[0-9a-f]{6}$")
        self.assertEqual(gui_theme.tile_color("Notepad"), gui_theme.tile_color("notepad"))
        self.assertEqual(gui_theme.tile_letter("7-Zip"), "7")
        self.assertEqual(gui_theme.tile_letter("—"), "?")

    def test_icon_font_path(self):
        with tempfile.TemporaryDirectory() as windows:
            self.assertIsNone(gui_theme.icon_font_path(windows) if not os.environ.get("WINDIR") else None)
            os.makedirs(os.path.join(windows, "Fonts"))
            open(os.path.join(windows, "Fonts", "segmdl2.ttf"), "wb").close()
            self.assertEqual(gui_theme.icon_font_path(windows), os.path.join(windows, "Fonts", "segmdl2.ttf"))


if __name__ == "__main__":
    unittest.main()
