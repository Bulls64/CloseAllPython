"""The application's own icon at any pixel size, for crisp title bar, taskbar and Alt+Tab icons.

Tk's `wm iconbitmap` always hands Windows the 16 px and 32 px images of the .ico, whatever the
display scaling: at 125 %, 150 % or 200 % Windows enlarges them and they look blurry. Here every
size is produced exactly: the image designed for that size when the .ico has it, otherwise the
next larger one reduced with a high-quality filter (never an enlargement).
"""
from PIL import Image

_cache = {}


def icon_image(ico_path, size):
    """RGBA Pillow image of `ico_path` at exactly `size` x `size` pixels."""
    key = (str(ico_path), size)
    if key not in _cache:
        with Image.open(ico_path) as ico:
            sizes = sorted(s for s in ico.info.get("sizes", {ico.size}) if s[0] == s[1])
            exact = (size, size)
            if exact in sizes:
                image = ico.ico.getimage(exact)
            else:
                larger = [s for s in sizes if s[0] > size]
                source = ico.ico.getimage(larger[0] if larger else sizes[-1])
                image = source.convert("RGBA").resize(exact, Image.Resampling.LANCZOS)
            _cache[key] = image.convert("RGBA")
    return _cache[key]


def icon_sizes(dpi):
    """(big, small) icon sizes Windows uses at `dpi` (96 = 100 %): 32/16 px scaled."""
    scale = max(dpi, 96) / 96
    return round(32 * scale), round(16 * scale)
