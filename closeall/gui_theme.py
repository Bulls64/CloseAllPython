"""Colours, fonts, icons and style sheet of the Qt interface, in the Windows 11 Fluent style.

The colours are WinUI 3's theme resources, most of them translucent (a card is white at 5 % in
the dark theme): Qt draws them over the window's Mica backdrop on Windows 11, or over the plain
Mica colour elsewhere, exactly as WinUI applications do. The accent follows the user's Windows
accent colour.
"""
from dataclasses import dataclass

# Windows 11 default accent (blue): (accent in the light theme, accent in the dark theme).
DEFAULT_ACCENT = ("#005fb8", "#4cc2ff")

LIGHT = {
    "base": "#f3f3f3",                       # Mica (window) colour without the backdrop
    "layer": "rgba(255, 255, 255, 0.5)",     # LayerFillColorDefault: the content area
    "layer_stroke": "rgba(0, 0, 0, 0.059)",
    "card": "rgba(255, 255, 255, 0.7)",      # CardBackgroundFillColorDefault
    "card_hover": "rgba(249, 249, 249, 0.5)",
    "card_secondary": "rgba(246, 246, 246, 0.5)",
    "card_stroke": "rgba(0, 0, 0, 0.059)",
    "divider": "rgba(0, 0, 0, 0.08)",
    "text": "rgba(0, 0, 0, 0.894)",
    "text2": "rgba(0, 0, 0, 0.62)",
    "text3": "rgba(0, 0, 0, 0.45)",
    "text_disabled": "rgba(0, 0, 0, 0.36)",
    "control": "rgba(255, 255, 255, 0.7)",   # ControlFillColorDefault
    "control_hover": "rgba(249, 249, 249, 0.5)",
    "control_pressed": "rgba(249, 249, 249, 0.3)",
    "control_disabled": "rgba(249, 249, 249, 0.3)",
    "control_stroke": "rgba(0, 0, 0, 0.059)",
    "control_stroke_bottom": "rgba(0, 0, 0, 0.16)",
    "control_strong": "rgba(0, 0, 0, 0.447)",
    "control_alt": "rgba(0, 0, 0, 0.024)",
    "subtle_hover": "rgba(0, 0, 0, 0.037)",
    "subtle_pressed": "rgba(0, 0, 0, 0.024)",
    "input": "rgba(255, 255, 255, 0.7)",
    "input_focus": "#ffffff",
    "on_accent": "#ffffff",
    "on_accent_disabled": "#ffffff",
    "accent_disabled": "rgba(0, 0, 0, 0.217)",
    "accent_stroke": "rgba(255, 255, 255, 0.08)",
    "accent_stroke_bottom": "rgba(0, 0, 0, 0.4)",
    "success": "#0f7b0f", "success_bg": "#dff6dd",
    "caution": "#9d5d00", "caution_bg": "#fff4ce",
    "critical": "#c42b1c", "critical_bg": "#fde7e9",
    "neutral_bg": "rgba(0, 0, 0, 0.06)",
    "smoke": "rgba(0, 0, 0, 0.3)",
    "dialog": "#ffffff",
    "dialog_footer": "#f3f3f3",
    "flyout": "#fcfcfc",
    "flyout_stroke": "rgba(0, 0, 0, 0.059)",
    "scroll": "rgba(0, 0, 0, 0.45)",
}

DARK = {
    "base": "#202020",
    "layer": "rgba(58, 58, 58, 0.3)",
    "layer_stroke": "rgba(0, 0, 0, 0.1)",
    "card": "rgba(255, 255, 255, 0.051)",
    "card_hover": "rgba(255, 255, 255, 0.084)",
    "card_secondary": "rgba(255, 255, 255, 0.031)",
    "card_stroke": "rgba(0, 0, 0, 0.1)",
    "divider": "rgba(255, 255, 255, 0.084)",
    "text": "#ffffff",
    "text2": "rgba(255, 255, 255, 0.786)",
    "text3": "rgba(255, 255, 255, 0.545)",
    "text_disabled": "rgba(255, 255, 255, 0.363)",
    "control": "rgba(255, 255, 255, 0.061)",
    "control_hover": "rgba(255, 255, 255, 0.084)",
    "control_pressed": "rgba(255, 255, 255, 0.033)",
    "control_disabled": "rgba(255, 255, 255, 0.042)",
    "control_stroke": "rgba(255, 255, 255, 0.07)",
    "control_stroke_bottom": "rgba(255, 255, 255, 0.094)",
    "control_strong": "rgba(255, 255, 255, 0.545)",
    "control_alt": "rgba(0, 0, 0, 0.1)",
    "subtle_hover": "rgba(255, 255, 255, 0.061)",
    "subtle_pressed": "rgba(255, 255, 255, 0.042)",
    "input": "rgba(255, 255, 255, 0.061)",
    "input_focus": "rgba(30, 30, 30, 0.7)",
    "on_accent": "#000000",
    "on_accent_disabled": "rgba(255, 255, 255, 0.53)",
    "accent_disabled": "rgba(255, 255, 255, 0.158)",
    "accent_stroke": "rgba(255, 255, 255, 0.08)",
    "accent_stroke_bottom": "rgba(0, 0, 0, 0.14)",
    "success": "#6ccb5f", "success_bg": "#393d1b",
    "caution": "#fce100", "caution_bg": "#433519",
    "critical": "#ff99a4", "critical_bg": "#442726",
    "neutral_bg": "rgba(255, 255, 255, 0.084)",
    "smoke": "rgba(0, 0, 0, 0.3)",
    "dialog": "#2b2b2b",
    "dialog_footer": "#202020",
    "flyout": "#2c2c2c",
    "flyout_stroke": "rgba(0, 0, 0, 0.2)",
    "scroll": "rgba(255, 255, 255, 0.545)",
}

# Letter tiles of applications without an icon.
TILE_COLORS = ("#2f6fae", "#b8552c", "#2f7f87", "#a34474", "#5f53b8", "#4a5263", "#4d58b0", "#3f7d3a", "#8a5a1f")

# Segoe Fluent Icons (Windows 11) and Segoe MDL2 Assets (Windows 10) share these code points;
# the second character is drawn with an ordinary font where neither exists.
GLYPHS = {
    "apps": ("", "▦"),
    "memory": ("", "◔"),
    "log": ("", "≡"),
    "settings": ("", "⚙"),
    "menu": ("", "≡"),
    "refresh": ("", "↻"),
    "search": ("", "⚲"),
    "shield": ("", "⚑"),
    "lock": ("", "•"),
    "chevron_right": ("", "›"),
    "chevron_down": ("", "⌄"),
    "chevron_up": ("", "⌃"),
    "back": ("", "←"),
    "check": ("", "✓"),
    "folder": ("", "▭"),
    "window": ("", "▢"),
    "info": ("", "ℹ"),
    "warning": ("", "⚠"),
    "globe": ("", "◍"),
    "color": ("", "◐"),
    "transparency": ("", "◈"),
    "lightning": ("", "ϟ"),
    "timer": ("", "◷"),
    "list": ("", "☰"),
    "image": ("", "▣"),
    "link": ("", "∞"),
    "pin": ("", "⊙"),
    "monitor": ("", "▭"),
    "sync": ("", "⟳"),
    "document": ("", "▤"),
    "open": ("", "↗"),
    "power": ("", "◉"),
    "clock": ("", "◷"),
}
ICON_FAMILIES = ("Segoe Fluent Icons", "Segoe MDL2 Assets")


def tile_color(name):
    import zlib

    return TILE_COLORS[zlib.crc32(name.casefold().encode("utf-8")) % len(TILE_COLORS)]


def tile_letter(name):
    return next((ch.upper() for ch in name if ch.isalnum()), "?")


def icon_font_path(windows_dir=None):
    """The icon font file of Windows (Fluent on Windows 11, MDL2 on Windows 10), or None."""
    import os

    folders = []
    if windows_dir:
        folders.append(os.path.join(windows_dir, "Fonts"))
    if os.environ.get("WINDIR"):
        folders.append(os.path.join(os.environ["WINDIR"], "Fonts"))
    for folder in folders:
        for name in ("SegoeIcons.ttf", "segmdl2.ttf"):
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                return path
    return None


def parse_rgba(value):
    """'#rrggbb' or 'rgba(r, g, b, a)' -> (r, g, b, alpha 0-255)."""
    value = value.strip()
    if value.startswith("#"):
        return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16), 255
    inner = value[value.index("(") + 1:value.index(")")]
    r, g, b, a = (part.strip() for part in inner.split(","))
    return int(r), int(g), int(b), round(float(a) * 255)


def accent_shades(palette):
    """(light-theme accent, dark-theme accent) from Windows' AccentPalette registry value.

    The value holds 8 colours of 4 bytes, light to dark: Light3, Light2, Light1, Base, Dark1,
    Dark2, Dark3, ... WinUI uses Dark1 in the light theme and Light2 in the dark theme.
    """
    if not palette or len(palette) < 32:
        return DEFAULT_ACCENT

    def shade(index):
        r, g, b = palette[index * 4:index * 4 + 3]
        return f"#{r:02x}{g:02x}{b:02x}"

    return shade(4), shade(1)


@dataclass
class Theme:
    dark: bool
    mica: bool                     # the window shows the Mica backdrop (translucent background)
    accent: tuple = DEFAULT_ACCENT
    ui_font: str = "Segoe UI"
    display_font: str = "Segoe UI"
    mono_font: str = "Consolas"
    icon_font: str | None = None

    @property
    def tokens(self):
        values = dict(DARK if self.dark else LIGHT)
        accent = self.accent[1 if self.dark else 0]
        r, g, b, _a = parse_rgba(accent)
        values["accent"] = accent
        values["accent_hover"] = f"rgba({r}, {g}, {b}, 0.9)"
        values["accent_pressed"] = f"rgba({r}, {g}, {b}, 0.8)"
        values["link"] = accent
        values["window"] = "transparent" if self.mica else values["base"]
        return values

    def __getitem__(self, name):
        return self.tokens[name]

    def glyph(self, name):
        windows_char, fallback = GLYPHS[name]
        return windows_char if self.icon_font else fallback

    def style_sheet(self):
        """The Qt style sheet of the whole application for this theme."""
        t = self.tokens
        ui, display = self.ui_font, self.display_font
        return f"""
* {{ font-family: "{ui}"; font-size: 14px; color: {t['text']}; }}
QMainWindow, #root {{ background: {t['window']}; }}
#nav {{ background: transparent; }}
#layer {{ background: {t['layer']}; border: 1px solid {t['layer_stroke']}; border-right: none; border-bottom: none;
          border-top-left-radius: 8px; }}
QStackedWidget, #page, #scrollContent {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-family: "{display}"; font-size: 28px; font-weight: 600; }}
QLabel[role="subtitle"] {{ font-family: "{display}"; font-size: 20px; font-weight: 600; }}
QLabel[role="strong"] {{ font-weight: 600; }}
QLabel[role="caption"] {{ font-size: 12px; }}
QLabel[role="caption_strong"] {{ font-size: 12px; font-weight: 600; }}
QLabel[role="small"] {{ font-size: 13px; }}
QLabel[tone="secondary"] {{ color: {t['text2']}; }}
QLabel[tone="tertiary"] {{ color: {t['text3']}; }}
QLabel[tone="link"], QLabel[tone="accent"] {{ color: {t['accent']}; }}
QLabel[tone="caution"] {{ color: {t['caution']}; }}
QLabel[tone="critical"] {{ color: {t['critical']}; }}
QLabel[role="glyph"] {{ font-family: "{self.icon_font or ui}"; font-size: 16px; }}
QLabel[role="glyph20"] {{ font-family: "{self.icon_font or ui}"; font-size: 20px; }}
QLabel[role="glyph12"] {{ font-family: "{self.icon_font or ui}"; font-size: 12px; }}
QLabel[pill="neutral"] {{ background: {t['neutral_bg']}; color: {t['text2']}; }}
QLabel[pill="success"] {{ background: {t['success_bg']}; color: {t['success']}; }}
QLabel[pill="caution"] {{ background: {t['caution_bg']}; color: {t['caution']}; }}
QLabel[pill="critical"] {{ background: {t['critical_bg']}; color: {t['critical']}; }}
QLabel[pill] {{ border-radius: 10px; padding: 2px 10px; min-height: 18px; font-size: 12px; font-weight: 600; }}
QLabel[badge="true"] {{ background: {t['neutral_bg']}; color: {t['text2']}; border-radius: 4px; padding: 0 6px;
                        font-size: 12px; }}

QFrame[card="default"] {{ background: {t['card']}; border: 1px solid {t['card_stroke']}; border-radius: 4px; }}
QFrame[card="default"][hover="true"]:hover {{ background: {t['card_hover']}; }}
QFrame[card="secondary"] {{ background: {t['card_secondary']}; border: 1px solid {t['card_stroke']};
                            border-radius: 4px; }}
QFrame[card="selected"] {{ background: {t['card_hover']}; border: 1px solid {t['card_stroke']}; border-radius: 4px; }}
QFrame[divider="true"] {{ background: {t['divider']}; border: none; max-height: 1px; min-height: 1px; }}
QFrame[bar="true"] {{ background: transparent; border-top: 1px solid {t['divider']}; }}

QPushButton {{ background: {t['control']}; border: 1px solid {t['control_stroke']};
               border-bottom-color: {t['control_stroke_bottom']}; border-radius: 4px; padding: 5px 12px;
               min-height: 20px; }}
QPushButton:hover {{ background: {t['control_hover']}; }}
QPushButton:pressed {{ background: {t['control_pressed']}; color: {t['text2']};
                       border-bottom-color: {t['control_stroke']}; }}
QPushButton:disabled {{ background: {t['control_disabled']}; color: {t['text_disabled']};
                        border-color: {t['control_stroke']}; }}
QPushButton[kind="accent"] {{ background: {t['accent']}; color: {t['on_accent']}; border: 1px solid {t['accent_stroke']};
                              border-bottom-color: {t['accent_stroke_bottom']}; font-weight: 600; }}
QPushButton[kind="accent"]:hover {{ background: {t['accent_hover']}; }}
QPushButton[kind="accent"]:pressed {{ background: {t['accent_pressed']}; color: {t['on_accent']}; }}
QPushButton[kind="accent"]:disabled {{ background: {t['accent_disabled']}; color: {t['on_accent_disabled']};
                                       border-color: transparent; }}
QPushButton[kind="subtle"] {{ background: transparent; border: 1px solid transparent; }}
QPushButton[kind="subtle"]:hover {{ background: {t['subtle_hover']}; }}
QPushButton[kind="subtle"]:pressed {{ background: {t['subtle_pressed']}; color: {t['text2']}; }}
QPushButton[kind="subtle"]:disabled {{ background: transparent; color: {t['text_disabled']}; }}
QPushButton[kind="icon"] {{ padding: 0; min-height: 30px; max-height: 30px; min-width: 30px; max-width: 30px; }}
QPushButton[kind="link"] {{ background: transparent; border: none; color: {t['link']}; padding: 4px 6px; }}
QPushButton[kind="link"]:hover {{ background: {t['subtle_hover']}; }}
QPushButton[dropdown="true"] {{ padding-right: 34px; }}
QPushButton::menu-indicator {{ image: none; width: 0; }}

QLineEdit {{ background: {t['input']}; border: 1px solid {t['control_stroke']};
             border-bottom: 1px solid {t['control_strong']}; border-radius: 4px; padding: 5px 10px;
             selection-background-color: {t['accent']}; selection-color: {t['on_accent']}; }}
QLineEdit:hover {{ background: {t['control_hover']}; }}
QLineEdit:focus {{ background: {t['input_focus']}; border-bottom: 2px solid {t['accent']}; padding-bottom: 4px; }}

QComboBox {{ background: {t['control']}; border: 1px solid {t['control_stroke']};
             border-bottom-color: {t['control_stroke_bottom']}; border-radius: 4px; padding: 5px 34px 5px 11px;
             min-height: 20px; }}
QComboBox:hover {{ background: {t['control_hover']}; }}
QComboBox::drop-down {{ border: none; width: 30px; }}
QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
QComboBox QAbstractItemView {{ background: {t['flyout']}; border: 1px solid {t['flyout_stroke']}; padding: 4px;
                               outline: none; selection-background-color: {t['subtle_hover']};
                               selection-color: {t['text']}; }}
QComboBox QAbstractItemView::item {{ min-height: 32px; padding: 0 10px; border-radius: 4px; }}

QMenu {{ background: {t['flyout']}; border: 1px solid {t['flyout_stroke']}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 7px 28px 7px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t['subtle_hover']}; }}
QMenu::item:disabled {{ color: {t['text_disabled']}; }}

QSlider::groove:horizontal {{ height: 4px; background: {t['control_strong']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 20px; height: 20px; margin: -8px 0; border-radius: 10px;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 {t['accent']},
                                stop:0.55 {t['accent']}, stop:0.6 {'#454545' if self.dark else '#ffffff'},
                                stop:1 {'#454545' if self.dark else '#ffffff'});
    border: 1px solid {t['control_stroke']}; }}

QProgressBar {{ background: {t['neutral_bg']}; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 2px; }}

QPlainTextEdit {{ background: {t['card']}; border: 1px solid {t['card_stroke']}; border-radius: 4px; padding: 8px;
                  font-family: "{self.mono_font}"; font-size: 12px; selection-background-color: {t['accent']};
                  selection-color: {t['on_accent']}; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 4px 2px 4px 2px; }}
QScrollBar::handle:vertical {{ background: {t['scroll']}; border-radius: 3px; min-height: 32px; margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ margin: 0; border-radius: 4px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px 4px 2px 4px; }}
QScrollBar::handle:horizontal {{ background: {t['scroll']}; border-radius: 3px; min-width: 32px; margin: 2px 0; }}

#dialogCard {{ background: {t['dialog']}; border: 1px solid {t['flyout_stroke']}; border-radius: 8px; }}
#dialogFooter {{ background: {t['dialog_footer']}; border-top: 1px solid {t['divider']};
                 border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; }}
QToolTip {{ background: {t['flyout']}; color: {t['text']}; border: 1px solid {t['flyout_stroke']}; padding: 4px 8px; }}
"""
