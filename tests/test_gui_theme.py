import unittest

try:   # the interface needs Tk and CustomTkinter (always there on Windows)
    from closeall import gui_theme
except ImportError:
    gui_theme = None


@unittest.skipIf(gui_theme is None, "needs tkinter and customtkinter")
class PaletteTests(unittest.TestCase):
    def tearDown(self):
        gui_theme.apply_palette(False)

    def test_mica_color_is_the_difference_from_the_base(self):
        self.assertEqual(gui_theme.mica_color("#323232"), "#121212")
        self.assertEqual(gui_theme.mica_color("#60cdff"), "#40addf")
        self.assertEqual(gui_theme.mica_color("#202020"), "#000000")   # the window background
        self.assertEqual(gui_theme.mica_color("#000000"), "#000000")   # nothing below black

    def test_palette_without_mica_is_the_tokens(self):
        palette = gui_theme.apply_palette(False)
        self.assertEqual(palette["card"], gui_theme.TOKENS["card"])
        self.assertFalse(gui_theme.mica_active())

    def test_palette_with_mica_converts_dark_colours_only(self):
        palette = gui_theme.apply_palette(True)
        self.assertTrue(gui_theme.mica_active())
        light, dark = gui_theme.TOKENS["card"]
        self.assertEqual(palette["card"], (light, gui_theme.mica_color(dark)))
        self.assertEqual(palette["bg"][1], "#000000")
        for name in gui_theme.OPAQUE:   # pop-up menus are separate windows: never converted
            self.assertEqual(palette[name], gui_theme.TOKENS[name])
        self.assertEqual(gui_theme.tile_color("Notepad")[1], gui_theme.mica_color(gui_theme.tile_color("Notepad")[0]))

    def test_icons_lose_the_base_under_mica(self):
        from PIL import Image

        picture = Image.new("RGBA", (2, 2), (100, 20, 255, 128))
        self.assertIs(gui_theme.mica_image(picture), picture)   # no Mica: unchanged
        gui_theme.apply_palette(True)
        self.assertEqual(gui_theme.mica_image(picture).getpixel((0, 0)), (68, 0, 223, 128))

    def test_every_token_is_a_colour_pair(self):
        for name, pair in gui_theme.TOKENS.items():
            self.assertEqual(len(pair), 2, name)
            for value in pair:
                self.assertRegex(value, r"^#[0-9a-f]{6}$", name)


@unittest.skipIf(gui_theme is None, "needs tkinter and customtkinter")
class GlyphTests(unittest.TestCase):
    def test_every_glyph_has_a_windows_and_a_fallback_character(self):
        for name, (windows_char, fallback) in gui_theme.GLYPHS.items():
            self.assertTrue(0xE000 <= ord(windows_char) <= 0xF8FF, name)   # icon font private area
            self.assertEqual(len(fallback), 1, name)

    def test_icon_font_path(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as windows:
            self.assertIsNone(gui_theme.icon_font_path(windows) if not os.environ.get("WINDIR") else None)
            os.makedirs(os.path.join(windows, "Fonts"))
            open(os.path.join(windows, "Fonts", "segmdl2.ttf"), "wb").close()
            self.assertEqual(gui_theme.icon_font_path(windows), os.path.join(windows, "Fonts", "segmdl2.ttf"))


if __name__ == "__main__":
    unittest.main()
