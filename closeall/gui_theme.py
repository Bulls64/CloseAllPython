"""Colours, fonts and icons of the interface, in the Windows 11 Fluent (WinUI 3) style.

Colours are (light, dark) pairs: CustomTkinter picks the right one for the current theme. They
are the WinUI 3 theme resources (Mica window, layer, cards, controls, accent) flattened to solid
colours.

Mica (dark theme, Windows 11 22H2 and later): the window's client area is handed to the desktop
compositor, which draws the Mica backdrop behind it. Tk paints with GDI, whose pixels carry no
alpha: the compositor then ADDS each colour to the backdrop, and black shows the backdrop alone.
So with Mica every dark colour is replaced by its difference from the backdrop's base tone
(#202020, also what Windows shows when the window is inactive or transparency is off): a card
meant to look #323232 is painted #121212 and the compositor brings it back to #323232, tinted by
the wallpaper like the rest of the window. See `apply_palette`.
"""
import os
import tkinter.font
import zlib

import customtkinter as ctk

# (light, dark) values of WinUI 3 theme resources, as solid colours.
TOKENS = {
    # window and navigation (Mica base)
    "bg": ("#f3f3f3", "#202020"),
    "nav_hover": ("#eaeaea", "#2d2d2d"),
    "nav_selected": ("#e6e6e6", "#2d2d2d"),
    # content layer (LayerFillColorDefault) and its edge
    "layer": ("#f9f9f9", "#282828"),
    "layer_border": ("#e5e5e5", "#262626"),
    # cards (CardBackgroundFillColorDefault / CardStrokeColorDefault)
    "card": ("#fdfdfd", "#323232"),
    "card_selected": ("#ffffff", "#3a3a3a"),
    "card_border": ("#e5e5e5", "#2b2b2b"),
    "card_secondary": ("#f6f6f6", "#2c2c2c"),
    "divider": ("#e5e5e5", "#3a3a3a"),
    # text
    "text": ("#1a1a1a", "#ffffff"),
    "text2": ("#5d5d5d", "#cfcfcf"),
    "text3": ("#8a8a8a", "#9a9a9a"),
    "text_disabled": ("#a0a0a0", "#787878"),
    # standard controls (ControlFillColorDefault / ControlStrokeColorDefault)
    "control": ("#fefefe", "#353535"),
    "control_hover": ("#f7f7f7", "#3c3c3c"),
    "control_border": ("#d9d9d9", "#424242"),
    "control_strong": ("#8a8a8a", "#9e9e9e"),
    "subtle_hover": ("#ededed", "#3a3a3a"),
    "input": ("#ffffff", "#2f2f2f"),
    "input_border": ("#d4d4d4", "#454545"),
    "track": ("#d0d0d0", "#4a4a4a"),
    # accent (default Windows blue)
    "accent": ("#005fb8", "#60cdff"),
    "accent_hover": ("#1a6fbf", "#5ab9e6"),
    "accent_disabled": ("#c8c8c8", "#4f4f4f"),
    "on_accent": ("#ffffff", "#000000"),
    "on_accent_disabled": ("#ffffff", "#a5a5a5"),
    "link": ("#005fb8", "#99ebff"),
    # status
    "success": ("#0f7b0f", "#6ccb5f"),
    "success_bg": ("#dff6dd", "#393d1b"),
    "caution": ("#9d5d00", "#fce100"),
    "caution_bg": ("#fff4ce", "#433519"),
    "critical": ("#c42b1c", "#ff99a4"),
    "critical_bg": ("#fde7e9", "#442726"),
    "neutral_bg": ("#f0f0f0", "#383838"),
    # pop-up menus: separate windows without Mica, never converted
    "menu": ("#f9f9f9", "#2c2c2c"),
    "menu_hover": ("#ebebeb", "#3d3d3d"),
}
OPAQUE = {"menu", "menu_hover"}

MICA_BASE = (0x20, 0x20, 0x20)

# Letter tiles of applications without an icon.
TILE_COLORS = ("#2f6fae", "#b8552c", "#2f7f87", "#a34474", "#5f53b8", "#4a5263", "#4d58b0", "#3f7d3a", "#8a5a1f")

C = {}
_mica = False


def mica_color(color):
    """The colour to paint so that, added to the Mica base, it shows as `color`."""
    value = color.lstrip("#")
    channels = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return "#" + "".join(f"{max(0, c - base):02x}" for c, base in zip(channels, MICA_BASE))


def apply_palette(mica):
    """Fill `C` for this window: real colours, or dark colours converted for Mica."""
    global _mica
    _mica = bool(mica)
    C.clear()
    for name, (light, dark) in TOKENS.items():
        C[name] = (light, mica_color(dark) if _mica and name not in OPAQUE else dark)
    return C


apply_palette(False)


def mica_active():
    return _mica


def color(light, dark=None):
    """A (light, dark) pair for a colour that is not a token (converted when Mica is on)."""
    dark = light if dark is None else dark
    return (light, mica_color(dark) if _mica else dark)


def mica_image(picture):
    """The dark-theme version of a picture (icon) under Mica: its colours minus the base."""
    if not _mica or picture is None:
        return picture
    from PIL import Image

    *rgb, alpha = picture.convert("RGBA").split()
    bands = [band.point(lambda v, b=base: max(0, v - b)) for band, base in zip(rgb, MICA_BASE)]
    return Image.merge("RGBA", (*bands, alpha))


def tile_color(name):
    """Stable (light, dark) colour for an application's letter tile."""
    value = TILE_COLORS[zlib.crc32(name.casefold().encode("utf-8")) % len(TILE_COLORS)]
    return color(value)


def tile_letter(name):
    return next((ch.upper() for ch in name if ch.isalnum()), "?")


# Segoe Fluent Icons (Windows 11) and Segoe MDL2 Assets (Windows 10) share these code points;
# the second character is drawn with an ordinary font where neither exists.
GLYPHS = {
    "apps": ("\ue71d", "▦"),
    "memory": ("\ue9d9", "◔"),
    "log": ("\ue81c", "≡"),
    "settings": ("\ue713", "⚙"),
    "menu": ("\ue700", "≡"),
    "refresh": ("\ue72c", "↻"),
    "search": ("\ue721", "⚲"),
    "shield": ("\uea18", "⚑"),
    "lock": ("\ue72e", "•"),
    "chevron_right": ("\ue76c", "›"),
    "chevron_down": ("\ue70d", "⌄"),
    "chevron_up": ("\ue70e", "⌃"),
    "back": ("\ue72b", "←"),
    "check": ("\ue73e", "✓"),
    "folder": ("\ue8b7", "▭"),
    "window": ("\ue737", "▢"),
    "info": ("\ue946", "ℹ"),
    "warning": ("\ue7ba", "⚠"),
    "globe": ("\ue774", "◍"),
    "color": ("\ue790", "◐"),
    "transparency": ("\ue771", "◈"),
    "lightning": ("\ue945", "ϟ"),
    "timer": ("\ue916", "◷"),
    "list": ("\ue8fd", "☰"),
    "image": ("\ue91b", "▣"),
    "link": ("\ue71b", "∞"),
    "pin": ("\ue718", "⊙"),
    "monitor": ("\ue7f4", "▭"),
    "sync": ("\ue895", "⟳"),
    "document": ("\ue8a5", "▤"),
    "open": ("\ue8e5", "↗"),
    "power": ("\ue7e8", "◉"),
    "clock": ("\ue823", "◷"),
}


def _semibold(families, *names):
    return next((name for name in names if name in families), None)


class Fonts:
    """The Windows 11 type ramp (Segoe UI Variable), created once a Tk root exists."""

    def __init__(self, root):
        families = set(tkinter.font.families(root))

        def pick(*names, default=None):
            return next((n for n in names if n in families), default)

        fallback = tkinter.font.nametofont("TkDefaultFont", root).actual("family")
        ui = pick("Segoe UI Variable Text", "Segoe UI", default=fallback)
        display = pick("Segoe UI Variable Display", "Segoe UI", default=ui)
        # Semibold is a family of its own on Windows (Tk only knows normal and bold weights).
        ui_semibold = _semibold(families, "Segoe UI Variable Text Semibold", "Segoe UI Variable Text Semib",
                                "Segoe UI Semibold")
        display_semibold = _semibold(families, "Segoe UI Variable Display Semib",
                                     "Segoe UI Variable Display Semibold", "Segoe UI Semibold")
        mono = pick("Cascadia Mono", "Consolas", "DejaVu Sans Mono", default="Courier")

        def strong(size, family=None, semibold=None):
            if semibold:
                return ctk.CTkFont(family=semibold, size=size)
            return ctk.CTkFont(family=family or ui, size=size, weight="bold")

        self.title = strong(28, display, display_semibold)
        self.subtitle = strong(20, display, display_semibold)
        self.body = ctk.CTkFont(family=ui, size=14)
        self.body_strong = strong(14, ui, ui_semibold)
        self.caption = ctk.CTkFont(family=ui, size=12)
        self.caption_strong = strong(12, ui, ui_semibold)
        self.small = ctk.CTkFont(family=ui, size=13)
        self.mono = ctk.CTkFont(family=mono, size=12)
        self.tile = strong(15, ui, ui_semibold)
        # names kept from the previous look
        self.h2 = self.subtitle
        self.name = self.body_strong
        self.body_bold = self.body_strong
        self.small_bold = self.caption_strong


def icon_font_path(windows_dir=None):
    """The icon font file of Windows (Fluent on Windows 11, MDL2 on Windows 10), or None."""
    folders = []
    if windows_dir:
        folders.append(os.path.join(windows_dir, "Fonts"))
    windir = os.environ.get("WINDIR")
    if windir:
        folders.append(os.path.join(windir, "Fonts"))
    for folder in folders:
        for name in ("SegoeIcons.ttf", "segmdl2.ttf"):
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                return path
    return None


class Glyphs:
    """Icons drawn from the Windows icon font into CTkImages (coloured for each theme).

    Pictures, unlike font glyphs, can sit next to text on a button. Outside Windows the fallback
    characters are drawn with an ordinary font, so the interface still shows something.
    """

    RENDER_SCALE = 3   # drawn larger, then reduced by CustomTkinter: sharp up to 300 % scaling

    def __init__(self, windows_dir=None):
        from PIL import ImageFont

        self._font_cls = ImageFont
        self.path = icon_font_path(windows_dir)
        self.fallback_path = None
        if self.path is None:
            for name in ("DejaVuSans.ttf", "seguisym.ttf", "Arial Unicode.ttf"):
                try:
                    ImageFont.truetype(name, 10)
                except OSError:
                    continue
                self.fallback_path = name
                break
        self.cache = {}

    @property
    def available(self):
        return bool(self.path or self.fallback_path)

    def _draw(self, char, size, hex_color, font_path):
        from PIL import Image, ImageDraw

        px = size * self.RENDER_SCALE
        font = self._font_cls.truetype(font_path, int(px * (0.9 if self.path else 0.8)))
        image = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        left, top, right, bottom = draw.textbbox((0, 0), char, font=font)
        draw.text(((px - (right - left)) / 2 - left, (px - (bottom - top)) / 2 - top), char, font=font,
                  fill=hex_color)
        return image

    def image(self, name, size=16, token="text", pair=None):
        """CTkImage of icon `name`, `size` logical px, in colour token `token` (or a colour pair)."""
        light, dark = pair or C[token]
        key = (name, size, light, dark)
        if key not in self.cache:
            if not self.available:
                self.cache[key] = None
            else:
                windows_char, fallback = GLYPHS[name]
                char, path = (windows_char, self.path) if self.path else (fallback, self.fallback_path)
                try:
                    self.cache[key] = ctk.CTkImage(light_image=self._draw(char, size, light, path),
                                                   dark_image=self._draw(char, size, dark, path), size=(size, size))
                except OSError:
                    self.cache[key] = None
        return self.cache[key]
