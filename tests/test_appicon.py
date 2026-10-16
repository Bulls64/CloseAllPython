import os
import unittest

from closeall import appicon

ICO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.ico")


class AppIconTests(unittest.TestCase):
    def test_windows_icon_sizes_follow_the_display_scaling(self):
        self.assertEqual(appicon.icon_sizes(96), (32, 16))     # 100 %
        self.assertEqual(appicon.icon_sizes(120), (40, 20))    # 125 %
        self.assertEqual(appicon.icon_sizes(144), (48, 24))    # 150 %
        self.assertEqual(appicon.icon_sizes(192), (64, 32))    # 200 %
        self.assertEqual(appicon.icon_sizes(0), (32, 16))      # unknown DPI

    def test_every_size_is_exact(self):
        for size in (16, 20, 24, 32, 40, 48, 64, 80, 96):
            image = appicon.icon_image(ICO, size)
            self.assertEqual((image.size, image.mode), ((size, size), "RGBA"), size)

    def test_sizes_present_in_the_file_are_used_as_designed(self):
        from PIL import Image
        with Image.open(ICO) as ico:
            designed = ico.ico.getimage((48, 48)).convert("RGBA")
        self.assertEqual(appicon.icon_image(ICO, 48).tobytes(), designed.tobytes())

    def test_other_sizes_are_reduced_never_enlarged(self):
        # 40 px (125 %) comes from the 48 px image, not from an enlarged 32 px one.
        from PIL import Image
        with Image.open(ICO) as ico:
            from_48 = ico.ico.getimage((48, 48)).convert("RGBA").resize((40, 40), Image.Resampling.LANCZOS)
        self.assertEqual(appicon.icon_image(ICO, 40).tobytes(), from_48.tobytes())


if __name__ == "__main__":
    unittest.main()
