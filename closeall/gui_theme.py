"""Colours, fonts and icon glyphs of the CustomTkinter interface.

Colours are (light, dark) pairs: CustomTkinter picks the right one for the current theme.
"""
import tkinter.font
import zlib

import customtkinter as ctk

ACCENT = "#2f6bdc"
ACCENT_HOVER = "#2659bd"
WARN_FILL = "#f0963c"
WARN_FILL_HOVER = "#de8530"
WARN_ON = "#1c1206"          # text on WARN_FILL
WHITE = "#ffffff"

C = {
    "bg": ("#f3f5f8", "#15171c"),
    "rail": ("#e8ecf1", "#121419"),
    "rail_active": ("#d5dce8", "#232733"),
    "surface": ("#ffffff", "#1b1e24"),
    "inset": ("#eef1f5", "#1d2027"),
    "hover": ("#e9eef6", "#252a33"),
    "border": ("#d9dee6", "#2a2e37"),
    "border_strong": ("#c5ccd7", "#343946"),
    "text": ("#172033", "#eef0f4"),
    "muted": ("#535e70", "#9aa1ad"),
    "faint": ("#6b7585", "#8a919e"),
    "sel_bg": ("#e8effc", "#1c2740"),
    "sel_border": ("#8fb0ec", "#3d63aa"),
    "seg_selected": ("#ffffff", "#2c313d"),
    "bar": ("#e9edf2", "#1a1d23"),
    "tile": ("#e3e7ee", "#23262e"),
    "scroll": ("#c5ccd7", "#343946"),
    "scroll_hover": ("#aab3c1", "#4a5160"),
    "ok_bg": ("#e2f4ea", "#16302a"),
    "ok_fg": ("#16704b", "#7fd8b4"),
    "warn_bg": ("#fdf0e2", "#1f1c18"),
    "warn_pill": ("#fbdcb8", "#3a2a18"),
    "warn_border": ("#e8b27a", "#6b4a24"),
    "warn_fg": ("#8a4a0c", "#f3b373"),
    "warn_text": ("#5b4630", "#d9c8b4"),
    "err_bg": ("#fbe7e7", "#2a1a1c"),
    "err_border": ("#e4a3a3", "#6b2d33"),
    "err_fg": ("#a12c2c", "#f1a3a3"),
    "neutral_bg": ("#e6eaf0", "#262a33"),
}

TILE_COLORS = ("#2f6fae", "#b8552c", "#2f7f87", "#a34474", "#5f53b8", "#4a5263", "#4d58b0", "#3f7d3a", "#8a5a1f")


def tile_color(name):
    """Stable colour for an application's letter tile."""
    return TILE_COLORS[zlib.crc32(name.casefold().encode("utf-8")) % len(TILE_COLORS)]


def tile_letter(name):
    return next((ch.upper() for ch in name if ch.isalnum()), "?")


# Segoe Fluent Icons (Windows 11) and Segoe MDL2 Assets (Windows 10) share these code points.
GLYPHS = {
    "apps": ("", "▦"),
    "log": ("", "≡"),
    "settings": ("", "⚙"),
    "refresh": ("", "↻"),
    "search": ("", "⌕"),
    "shield": ("", "!"),
    "lock": ("", "•"),
    "chevron_right": ("", "›"),
    "chevron_down": ("", "⌄"),
    "back": ("", "‹"),
    "check": ("", "✓"),
    "clock": ("", "…"),
    "power": ("", "⏻"),
    "window": ("", "↗"),
    "folder": ("", "▸"),
}


class Fonts:
    """Fonts are created once a Tk root exists; families fall back gracefully outside Windows."""

    def __init__(self, root):
        families = set(tkinter.font.families(root))

        def pick(*names, default=None):
            return next((n for n in names if n in families), default)

        fallback = tkinter.font.nametofont("TkDefaultFont", root).actual("family")
        ui = pick("Segoe UI Variable Text", "Segoe UI", default=fallback)
        display = pick("Segoe UI Variable Display", "Segoe UI Semibold", default=ui)
        mono = pick("Cascadia Mono", "Consolas", "DejaVu Sans Mono", default="Courier")
        self.icon_family = pick("Segoe Fluent Icons", "Segoe MDL2 Assets")

        self.title = ctk.CTkFont(family=display, size=24, weight="bold")
        self.h2 = ctk.CTkFont(family=ui, size=15, weight="bold")
        self.body = ctk.CTkFont(family=ui, size=14)
        self.body_bold = ctk.CTkFont(family=ui, size=14, weight="bold")
        self.name = ctk.CTkFont(family=ui, size=15, weight="bold")
        self.small = ctk.CTkFont(family=ui, size=12)
        self.small_bold = ctk.CTkFont(family=ui, size=12, weight="bold")
        self.tiny = ctk.CTkFont(family=ui, size=10)
        self.mono = ctk.CTkFont(family=mono, size=12)
        self.tile = ctk.CTkFont(family=ui, size=15, weight="bold")
        icon_family = self.icon_family or ui
        self.icon = ctk.CTkFont(family=icon_family, size=18)
        self.icon_small = ctk.CTkFont(family=icon_family, size=13)

    def glyph(self, name):
        windows_glyph, fallback = GLYPHS[name]
        return windows_glyph if self.icon_family else fallback
