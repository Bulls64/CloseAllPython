"""Qt (PySide6) user interface in the Windows 11 Fluent style: navigation pane, application list,
closing screen, background processes, log and settings.

Qt draws the whole window at once with real transparency: on Windows 11 22H2 and later the
window shows the Mica backdrop (light and dark themes) and every WinUI colour, most of them
translucent, is drawn over it as in WinUI applications.
"""
import ast
import logging
import ntpath
import os
import re
import sys
import threading
import time
import weakref
from dataclasses import dataclass, field

from PySide6.QtCore import (QEvent, QLibraryInfo, QObject, QRectF, QSize, Qt, QTimer, QTranslator, QVariantAnimation,
                            Signal)
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetrics, QGuiApplication, QIcon, QImage, QKeySequence,
                           QPainter, QPen, QPixmap, QShortcut)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QBoxLayout, QButtonGroup, QCheckBox, QComboBox, QFrame,
                               QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
                               QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSlider,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import __version__, core, crash, settings as settings_mod, shortcut, updater, winapi
from .gui_theme import ICON_FAMILIES, Theme, accent_shades, parse_rgba, tile_color, tile_letter
from .i18n import LANGUAGE_NAMES, TEXT, format_memory, format_seconds, translate, translate_n

log = logging.getLogger(settings_mod.LOGGER_NAME)

SEARCH_DELAY_MS = 120
MAX_DIALOG_ITEMS = 12
MAX_TITLE = 110
ICON_SIZE = 24          # logical px
ICON_SOURCE_SIZE = 48   # extracted size, sharp up to 200 % scaling
LOG_LINES = 400
NOTICE_MS = 4000
# Automatic refreshes after closing applications: at once, then a few more for windows that
# disappear late (UWP frames left by ApplicationFrameHost, applications that close slowly).
AFTER_CLOSE_REFRESH_MS = (0, 400, 1200, 3000)
# After closing Explorer windows (folder windows close asynchronously).
EXPLORER_REFRESH_MS = (700, 2000)
RETRY_REFRESH_MS = 150
UPDATE_STARTUP_DELAY_MS = 2000   # the automatic check waits until the window is up
NAV_WIDTH, NAV_COMPACT_WIDTH = 248, 48
NAV_AUTO_COMPACT = 920            # narrower windows show the navigation pane as icons only
PAD = 36                          # page margins

THEME = Theme(dark=False, mica=False)
_ICONS = weakref.WeakKeyDictionary()   # buttons with a glyph icon -> (glyph, colour token)


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, name)


def shorten(text, limit=MAX_TITLE):
    return text if len(text) <= limit else text[:limit - 1] + "…"


# ====================================================================== drawing helpers

def qcolor(token):
    """QColor of a theme token (or of a literal colour)."""
    value = THEME.tokens.get(token, token)
    return QColor(*parse_rgba(value))


def glyph_font(pixel_size):
    font = QFont(THEME.icon_font or THEME.ui_font)
    font.setPixelSize(pixel_size)
    return font


def glyph_pixmap(name, token="text", size=16):
    ratio = 2.0
    screen = QGuiApplication.primaryScreen()
    if screen is not None:
        ratio = max(1.0, min(3.0, screen.devicePixelRatio()))
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setPen(qcolor(token))
    painter.setFont(glyph_font(size))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, THEME.glyph(name))
    painter.end()
    return pixmap


def set_glyph(button, name, token="text"):
    """Give a button a glyph icon, redrawn when the theme changes."""
    _ICONS[button] = (name, token)
    button.setIcon(QIcon(glyph_pixmap(name, token)))
    button.setIconSize(QSize(16, 16))


def refresh_glyphs():
    for button, (name, token) in list(_ICONS.items()):
        try:
            button.setIcon(QIcon(glyph_pixmap(name, token)))
        except RuntimeError:   # the widget is gone
            _ICONS.pop(button, None)


def repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_prop(widget, name, value):
    widget.setProperty(name, value)
    repolish(widget)


def label(text="", role=None, tone=None, wrap=False):
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    if tone:
        widget.setProperty("tone", tone)
    widget.setWordWrap(wrap)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return widget


def glyph_label(name, size=16, tone=None):
    widget = label(THEME.glyph(name), {16: "glyph", 20: "glyph20", 12: "glyph12"}[size], tone)
    widget.setFixedWidth(size + 4)
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return widget


class IconTextButton(QPushButton):
    """A button with a glyph before its text, kept apart from it as in WinUI."""

    def setText(self, text):
        super().setText(f" {text}" if text else text)


def button(text, on_click=None, kind="standard", icon=None):
    widget = IconTextButton(text) if icon and text else QPushButton(text)
    widget.setProperty("kind", kind)
    if icon:
        set_glyph(widget, icon, "on_accent" if kind == "accent" else "text")
    if on_click is not None:
        widget.clicked.connect(lambda _checked=False: on_click())
    return widget


def icon_button(name, on_click=None, kind="subtle", tooltip=None):
    widget = button("", on_click, kind, name)
    widget.setProperty("shape", "icon")
    widget.setFixedSize(32, 32)
    if tooltip:
        widget.setToolTip(tooltip)
    return widget


def hbox(margins=(0, 0, 0, 0), spacing=0):
    layout = QHBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout


def vbox(margins=(0, 0, 0, 0), spacing=0):
    layout = QVBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout


def card(kind="default", hover=False):
    frame = QFrame()
    frame.setProperty("card", kind)
    if hover:
        frame.setProperty("hover", "true")
        frame.setAttribute(Qt.WidgetAttribute.WA_Hover)
    return frame


def divider():
    line = QFrame()
    line.setProperty("divider", "true")
    line.setFixedHeight(1)
    return line


def scroll_area():
    """A transparent scroll area and the widget to fill (with a vertical layout)."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.viewport().setAutoFillBackground(False)   # a style sheet here would override the cards'
    content = QWidget()
    content.setObjectName("scrollContent")
    content.setLayout(vbox())
    area.setWidget(content)
    return area, content


class Painted:
    """Mixin for the widgets drawn by hand: they are repainted when the theme changes."""


# ====================================================================== Fluent controls

class CheckBox(QCheckBox, Painted):
    """WinUI CheckBox (the box only)."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(20, 20)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, 19, 19)
        hover = self.underMouse()
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor("accent_hover" if hover else "accent"))
            painter.drawRoundedRect(rect, 4, 4)
            pen = QPen(qcolor("on_accent"), 1.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline([QRectF(5.2, 10.2, 0, 0).topLeft(), QRectF(8.4, 13.4, 0, 0).topLeft(),
                                  QRectF(14.8, 6.8, 0, 0).topLeft()])
        else:
            painter.setPen(QPen(qcolor("control_strong"), 1))
            painter.setBrush(qcolor("subtle_hover" if hover else "control_alt"))
            painter.drawRoundedRect(rect, 4, 4)
        painter.end()


class Toggle(QCheckBox, Painted):
    """WinUI ToggleSwitch: outlined when off, accent with a contrasting knob when on (animated)."""

    def __init__(self, checked=False):
        super().__init__()
        self.setFixedSize(40, 20)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setChecked(checked)
        self._position = 1.0 if checked else 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(120)
        self._animation.valueChanged.connect(self._moved)
        self.toggled.connect(self._animate)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def _moved(self, value):
        self._position = float(value)
        self.update()

    def _animate(self, checked):
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, 39, 19)
        on, enabled, hover = self.isChecked(), self.isEnabled(), self.underMouse()
        if on:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor("accent_disabled" if not enabled else "accent_hover" if hover else "accent"))
        else:
            painter.setPen(QPen(qcolor("text_disabled" if not enabled else "control_strong"), 1))
            painter.setBrush(qcolor("subtle_hover" if hover else "control_alt"))
        painter.drawRoundedRect(rect, 9.5, 9.5)
        radius = 7 if hover and enabled else 6
        x = 10 + self._position * 20
        painter.setPen(Qt.PenStyle.NoPen)
        if on:
            painter.setBrush(qcolor("on_accent_disabled" if not enabled else "on_accent"))
        else:
            painter.setBrush(qcolor("text_disabled" if not enabled else "text2"))
        painter.drawEllipse(QRectF(x - radius, 10 - radius, radius * 2, radius * 2))
        painter.end()


class ComboBox(QComboBox, Painted):
    """WinUI ComboBox: a button-like box with a chevron."""

    def __init__(self, values, width=200):
        super().__init__()
        self.addItems(values)
        self.setFixedWidth(width)
        self.setMaxVisibleItems(12)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(qcolor("text2"))
        painter.setFont(glyph_font(12))
        painter.drawText(QRectF(self.width() - 32, 0, 22, self.height()), Qt.AlignmentFlag.AlignCenter,
                         THEME.glyph("chevron_down"))
        painter.end()


class DropDownButton(QPushButton, Painted):
    """WinUI DropDownButton: text, then a chevron; the menu opens under it."""

    def __init__(self, text, icon, menu):
        super().__init__(text)
        self.setProperty("kind", "standard")
        set_glyph(self, icon)
        self.setMenu(menu)
        self.setProperty("dropdown", "true")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(qcolor("text2" if self.isEnabled() else "text_disabled"))
        painter.setFont(glyph_font(10))
        painter.drawText(QRectF(self.width() - 28, 0, 16, self.height()), Qt.AlignmentFlag.AlignCenter,
                         THEME.glyph("chevron_down"))
        painter.end()


def flyout_menu(parent):
    """A QMenu with rounded corners (WinUI MenuFlyout)."""
    menu = QMenu(parent)
    menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint
                        | Qt.WindowType.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    return menu


class SelectorItem(QAbstractButton, Painted):
    def __init__(self, text=""):
        super().__init__()
        self.setCheckable(True)
        self.setText(text)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedHeight(40)

    def setText(self, text):
        super().setText(text)
        bold = QFont(self.font())
        bold.setWeight(QFont.Weight.DemiBold)
        self.setFixedWidth(QFontMetrics(bold).horizontalAdvance(text) + 26)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor("subtle_pressed" if self.isDown() else "subtle_hover"))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0, 2, 0, -2), 4, 4)
        font = QFont(self.font())
        font.setWeight(QFont.Weight.DemiBold if self.isChecked() else QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(qcolor("text" if self.isChecked() else "text2"))
        painter.drawText(QRectF(self.rect()).adjusted(0, -2, 0, -2), Qt.AlignmentFlag.AlignCenter, self.text())
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor("accent"))
            painter.drawRoundedRect(QRectF(self.width() / 2 - 8, self.height() - 5, 16, 3), 1.5, 1.5)
        painter.end()


class SelectorBar(QWidget):
    """WinUI SelectorBar: text items, the selected one in bold with an accent mark under it."""

    def __init__(self, names, on_select):
        super().__init__()
        self.items, self.on_select = {}, on_select
        layout = hbox(spacing=2)
        self.setLayout(layout)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for name in names:
            item = SelectorItem()
            item.clicked.connect(lambda _checked=False, n=name: self.on_select(n))
            group.addButton(item)
            layout.addWidget(item)
            self.items[name] = item
        self.items[names[0]].setChecked(True)

    def set_text(self, name, text):
        self.items[name].setText(text)

    def select(self, name):
        self.items[name].setChecked(True)


class Tile(QWidget, Painted):
    """32 px square: the application's icon, or its initial on a coloured background."""

    def __init__(self, name, pixmap=None, protected=False):
        super().__init__()
        self.setFixedSize(32, 32)
        self.name, self.pixmap, self.protected = name, pixmap, protected

    def set_pixmap(self, pixmap):
        if pixmap is not None:
            self.pixmap = pixmap
            self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.pixmap is not None:
            painter.drawPixmap(QRectF(4, 4, 24, 24).toRect(), self.pixmap)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor("neutral_bg") if self.protected else QColor(tile_color(self.name)))
            painter.drawRoundedRect(QRectF(0, 0, 32, 32), 6, 6)
            font = QFont(THEME.ui_font)
            font.setPixelSize(15)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            painter.setPen(qcolor("text2") if self.protected else QColor("#ffffff"))
            painter.drawText(QRectF(0, 0, 32, 32), Qt.AlignmentFlag.AlignCenter, tile_letter(self.name))
        painter.end()


def toggle_with_state(app, checked, on_change, enabled=True):
    """A ToggleSwitch with its On/Off text on the left, as WinUI shows it."""
    box = QWidget()
    layout = hbox(spacing=12)
    box.setLayout(layout)
    state = label("", tone="secondary")
    toggle = Toggle(checked)
    toggle.setEnabled(enabled)

    def show(value):
        state.setText(app.t("toggle_on") if value else app.t("toggle_off"))

    show(checked)
    toggle.toggled.connect(show)
    toggle.toggled.connect(lambda value: on_change(bool(value)))
    layout.addWidget(state)
    layout.addWidget(toggle)
    box.toggle = toggle
    return box


def settings_card(glyph, title, description=None, control=None, parent_layout=None):
    """A WinUI SettingsCard: icon, title and description on the left, the control on the right."""
    box = card()
    layout = hbox((16, 12, 16, 12), 16)
    box.setLayout(layout)
    box.setMinimumHeight(68)
    if glyph:
        layout.addWidget(glyph_label(glyph, 20))
    texts = vbox(spacing=0)
    texts.addWidget(label(title, wrap=True))
    box.description = None
    if description:
        box.description = label(description, "caption", "secondary", wrap=True)
        texts.addWidget(box.description)
    box.texts = texts
    layout.addLayout(texts, 1)
    if control is not None:
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    if parent_layout is not None:
        parent_layout.addWidget(box)
    return box


def section_header(text, parent_layout, first=False):
    if not first:
        parent_layout.addSpacing(18)
    parent_layout.addWidget(label(text, "strong"))
    parent_layout.addSpacing(6)


def infobar(text, glyph="info"):
    """A WinUI InfoBar (informational): icon and message on a quiet card."""
    box = card("secondary")
    layout = hbox((16, 10, 16, 10), 12)
    box.setLayout(layout)
    icon = glyph_label(glyph, tone="accent")
    icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
    box.icon = icon
    layout.addWidget(icon)
    layout.addWidget(label(text, "small", wrap=True), 1)
    return box


def pill():
    widget = label("", tone=None)
    widget.setProperty("pill", "neutral")
    return widget


def page_header(title):
    """Title row of a page: returns the layout, the texts block (for a subtitle) and the actions row."""
    row = hbox(spacing=16)
    texts = vbox(spacing=2)
    texts.addWidget(label(title, "title"))
    row.addLayout(texts, 1)
    actions = hbox(spacing=8)
    row.addLayout(actions)
    return row, texts, actions


class CommandBar(QFrame):
    """The bar under a list: a status text on the left, the buttons on the right. When the
    buttons leave too little room for the text, they go on a second row."""

    TEXT_MIN = 300

    def __init__(self):
        super().__init__()
        self.setProperty("bar", "true")
        self.box = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.box.setContentsMargins(PAD, 14, PAD, 16)
        self.box.setSpacing(12)
        self.setLayout(self.box)
        self.texts = vbox(spacing=2)
        self.box.addLayout(self.texts, 1)
        self.buttons = QWidget()
        self.buttons_row = hbox(spacing=8)
        self.buttons_row.addStretch(1)
        self.buttons.setLayout(self.buttons_row)
        self.box.addWidget(self.buttons, 0, Qt.AlignmentFlag.AlignVCenter)

    def add_buttons(self, *widgets):
        for widget in widgets:
            self.buttons_row.addWidget(widget)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        room = self.width() - 2 * PAD - self.buttons.sizeHint().width() - 12
        direction = (QBoxLayout.Direction.LeftToRight if room >= self.TEXT_MIN
                     else QBoxLayout.Direction.TopToBottom)
        if self.box.direction() != direction:
            self.box.setDirection(direction)


class Dialog(QWidget):
    """A WinUI ContentDialog: a card over the window, which is dimmed behind it."""

    def __init__(self, app, title, message, items=(), confirm_text=None, on_confirm=None, cancel_text=None):
        super().__init__(app)
        self.app, self.on_confirm, self.confirm_text = app, on_confirm, confirm_text
        self._open = True
        app.dialogs += 1   # automatic list refreshes wait while a dialog is open
        self.setGeometry(app.rect())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        outer = vbox((24, 24, 24, 24))
        self.setLayout(outer)
        outer.addStretch(1)
        frame = QFrame()
        frame.setObjectName("dialogCard")
        frame.setFixedWidth(min(520, max(340, app.width() - 96)))
        shadow = QGraphicsDropShadowEffect(frame)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 90))
        frame.setGraphicsEffect(shadow)
        row = hbox()
        row.addStretch(1)
        row.addWidget(frame)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)
        layout = vbox()
        frame.setLayout(layout)
        body = vbox((24, 22, 24, 24), 12)
        layout.addLayout(body)
        self.title_label = label(title, "subtitle", wrap=True)
        body.addWidget(self.title_label)
        self.message_label = label(message, wrap=True)
        body.addWidget(self.message_label)
        self.labels = [self.title_label, self.message_label]
        items = list(items)
        if items:
            shown, hidden = core.truncate(items, MAX_DIALOG_ITEMS)
            box = card()
            box_layout = vbox((14, 10, 14, 10), 6)
            box.setLayout(box_layout)
            for item in shown:
                line = label(f"•  {shorten(item, 70)}")
                box_layout.addWidget(line)
                self.labels.append(line)
            if hidden:
                box_layout.addWidget(label(app.t("more_items", count=hidden), "caption", "secondary"))
            body.addWidget(box)
        footer = QFrame()
        footer.setObjectName("dialogFooter")
        buttons = hbox((24, 24, 24, 24), 8)
        footer.setLayout(buttons)
        layout.addWidget(footer)
        if confirm_text:
            self.confirm_button = button(confirm_text, self._confirm, "accent")
            buttons.addWidget(self.confirm_button, 1)
            self.cancel_button = button(cancel_text or app.t("cancel"), self.destroy)
            buttons.addWidget(self.cancel_button, 1)
            default = self.confirm_button
        else:
            buttons.addStretch(1)
            default = button(app.t("ok"), self.destroy, "accent")
            buttons.addWidget(default, 1)
        self.show()
        self.raise_()
        default.setFocus()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), qcolor("smoke"))
        painter.end()

    def mousePressEvent(self, event):
        event.accept()   # modal: clicks behind the dialog do nothing

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.destroy()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirm() if self.confirm_text else self.destroy()
        else:
            super().keyPressEvent(event)

    def destroy(self):
        if self._open:
            self._open = False
            self.app.dialogs -= 1
            self.hide()
            self.deleteLater()

    def _confirm(self):
        callback = self.on_confirm
        self.destroy()
        if callback:
            callback()


# ====================================================================== application list

@dataclass
class Entry:
    card_key: object               # what a card represents (a process, or one window)
    proc_key: tuple                # the process it closes
    name: str
    meta: str
    search_text: str
    titles: list = field(default_factory=list)
    exe_path: str | None = None
    protected: bool = False


class AppCard(QFrame):
    def __init__(self, page, entry, pixmap):
        super().__init__()
        self.setProperty("card", "secondary" if entry.protected else "default")
        self.setProperty("hover", "true")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.page, self.entry, self.windows_box = page, entry, None
        outer = vbox()
        self.setLayout(outer)
        row = hbox((16, 12, 8, 12), 16)
        outer.addLayout(row)
        if entry.protected:
            row.addWidget(glyph_label("lock", tone="tertiary"))
            self.check = None
        else:
            self.check = CheckBox()
            self.check.toggled.connect(self._on_check)
            row.addWidget(self.check)
        self.tile = Tile(entry.name, pixmap, entry.protected)
        row.addWidget(self.tile)
        texts = vbox()
        texts.addWidget(label(entry.name, "strong", "secondary" if entry.protected else None))
        texts.addWidget(label(entry.meta, "caption", "tertiary" if entry.protected else "secondary"))
        row.addLayout(texts, 1)
        self.chevron = None
        if entry.titles:
            self.chevron = icon_button("chevron_down", self.toggle_expand)
            row.addWidget(self.chevron)
        self.outer = outer

    def mousePressEvent(self, event):
        if self.check is not None and event.button() == Qt.MouseButton.LeftButton:
            self.check.toggle()
        super().mousePressEvent(event)

    def _on_check(self, checked):
        self.page.set_selected(self.entry.proc_key, bool(checked))

    def show_selected(self, selected):
        if self.check is None:
            return
        self.check.blockSignals(True)
        self.check.setChecked(selected)
        self.check.blockSignals(False)
        self.check.update()
        kind = "selected" if selected else "default"
        if self.property("card") != kind:
            set_prop(self, "card", kind)

    def toggle_expand(self):
        expanded = self.entry.card_key not in self.page.expanded
        if expanded:
            self.page.expanded.add(self.entry.card_key)
        else:
            self.page.expanded.discard(self.entry.card_key)
        self.show_expanded(expanded)

    def show_expanded(self, expanded):
        if self.chevron is None:
            return
        set_glyph(self.chevron, "chevron_up" if expanded else "chevron_down")
        if expanded and self.windows_box is None:
            # Built on first use: most cards are never expanded.
            self.windows_box = QWidget()
            layout = vbox((0, 0, 0, 8))
            self.windows_box.setLayout(layout)
            layout.addWidget(divider())
            for title in self.entry.titles:
                row = hbox((100, 8, 16, 0), 12)
                row.addWidget(glyph_label("window", 12, "secondary"))
                row.addWidget(label(shorten(title), "small", "secondary"), 1)
                layout.addLayout(row)
            self.outer.addWidget(self.windows_box)
        if self.windows_box is not None:
            self.windows_box.setVisible(expanded)


class Page(QWidget):
    def __init__(self, app):
        super().__init__()
        self.setObjectName("page")
        self.app = app


class ListPage(Page):
    def __init__(self, app, state=None):
        super().__init__(app)
        t = app.t
        state = state or {}
        self.windows, self.entries, self.cards = [], [], {}
        self.selected = set(state.get("selected", ()))
        self.expanded = set(state.get("expanded", ()))
        self.filter = "all"
        self.app_count = self.selectable_count = 0
        self.notice = None          # status-bar message shown for NOTICE_MS
        self.notice_timer = None
        self.refresh_timers, self.retry_timer = [], None
        self.restarting_explorer = False
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.apply_filter)
        layout = vbox()
        self.setLayout(layout)

        top = vbox((PAD, 28, PAD, 0), 0)
        layout.addLayout(top)
        header, titles, actions = page_header(t("apps_title"))
        self.summary = label("", tone="secondary")
        titles.addWidget(self.summary)
        if not app.is_admin:
            actions.addWidget(button(t("admin_button"), app.restart_as_admin, icon="shield"), 0,
                              Qt.AlignmentFlag.AlignTop)
        actions.addWidget(icon_button("refresh", self.refresh, "standard", t("refresh")), 0, Qt.AlignmentFlag.AlignTop)
        top.addLayout(header)
        top.addSpacing(20)
        toolbar = hbox(spacing=24)
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("search_placeholder"))
        self.search.setClearButtonEnabled(False)
        self.search_action = self.search.addAction(QIcon(glyph_pixmap("search", "text2")),
                                                   QLineEdit.ActionPosition.TrailingPosition)
        self.search.setMinimumHeight(32)
        if state.get("query"):
            self.search.setText(state["query"])
        self.search.textChanged.connect(lambda _text: self.search_timer.start(SEARCH_DELAY_MS))
        self.search.installEventFilter(self)
        toolbar.addWidget(self.search, 1)
        self.filter_bar = SelectorBar(["all", "selected"], self._on_filter)
        toolbar.addWidget(self.filter_bar)
        top.addLayout(toolbar)
        top.addSpacing(12)

        area, self.list = scroll_area()
        self.list_layout = self.list.layout()
        self.list_layout.setContentsMargins(PAD - 4, 0, PAD - 16, 16)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch(1)
        layout.addWidget(area, 1)
        self.empty = label("", tone="secondary")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.protected_header = QWidget()
        header_row = hbox((4, 14, 0, 6), 8)
        self.protected_header.setLayout(header_row)
        header_row.addWidget(glyph_label("lock", 12, "secondary"))
        header_row.addWidget(label(t("protected_header"), "strong", "secondary"), 1)

        bar = CommandBar()
        texts = bar.texts
        self.selection_line = label("", "strong", wrap=True)
        texts.addWidget(self.selection_line)
        hint = hbox(spacing=6)
        self.hint_icon = glyph_label("warning", 12, "caution")
        hint.addWidget(self.hint_icon, 0, Qt.AlignmentFlag.AlignTop)
        self.hint = label("", "caption", "secondary", wrap=True)
        hint.addWidget(self.hint, 1)
        texts.addLayout(hint)
        self.explorer_menu = flyout_menu(self)
        self.close_explorer_action = self.explorer_menu.addAction(t("close_explorer_short"), self.close_explorer)
        self.restart_explorer_action = self.explorer_menu.addAction(t("restart_explorer_short"),
                                                                    self.restart_explorer)
        self.explorer_button = DropDownButton(t("explorer_group"), "folder", self.explorer_menu)
        self.clear_button = button(t("clear_selection"), self.clear_selection)
        self.close_button = button("", self.close_selected, "accent")
        bar.add_buttons(self.explorer_button, self.clear_button, self.close_button)
        layout.addWidget(bar)

    def eventFilter(self, watched, event):
        if watched is self.search and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.search.clear()
            self.apply_filter()
            return True
        return super().eventFilter(watched, event)

    # ---------------------------------------------------------------- data
    def refresh(self, rebuild=False):
        """Read the windows again. Cards whose content did not change are kept as they are
        (no flicker, no work); `rebuild` recreates them all (icons switched on or off)."""
        if self.app.busy:
            return
        app, t = self.app, self.app.t
        self.windows = core.list_windows(app.own_pids)
        by_process = {}
        for w in self.windows:
            by_process.setdefault(w.key, []).append(w)
        entries = []
        if app.settings["group_by_app"]:
            for key, windows in by_process.items():
                first = windows[0]
                name = app.display_name(first.exe_path) or t("process_n", pid=first.pid)
                exe = ntpath.basename(first.exe_path) if first.exe_path else ""
                meta = " · ".join(p for p in (app.tn("n_windows", len(windows)), exe, t("pid", pid=first.pid)) if p)
                titles = [w.title for w in windows]
                entries.append(Entry(key, key, name, meta, " ".join([name] + titles).casefold(), titles,
                                     first.exe_path, first.protected))
        else:
            for w in self.windows:
                app_name = app.display_name(w.exe_path) or t("process_n", pid=w.pid)
                meta = f"{app_name} · {t('pid', pid=w.pid)}"
                entries.append(Entry(("window", w.hwnd), w.key, shorten(w.title), meta,
                                     f"{w.title} {app_name}".casefold(), [], w.exe_path, w.protected))
        entries.sort(key=lambda e: (e.protected, e.name.casefold()))
        self.entries = entries
        selectable = {e.proc_key for e in entries if not e.protected}
        self.selected &= selectable   # closed applications leave the selection
        self.selectable_count = len(selectable)
        self.app_count = len({e.proc_key for e in entries})
        self._build_cards(rebuild)
        if app.settings["show_icons"]:
            app.preload_icons(e.exe_path for e in entries)
        self.apply_filter()

    def _build_cards(self, rebuild=False):
        old, self.cards = self.cards, {}
        for entry in self.entries:
            widget = old.pop(entry.card_key, None)
            if widget is not None and (rebuild or widget.entry != entry):
                widget.deleteLater()
                widget = None
            if widget is None:
                pixmap = None
                if self.app.settings["show_icons"]:
                    pixmap = self.app.icon_for(entry.exe_path, lambda pix, key=entry.card_key: self._icon_ready(key, pix))
                widget = AppCard(self, entry, pixmap)
                widget.show_expanded(entry.card_key in self.expanded)
            widget.show_selected(entry.proc_key in self.selected)
            self.cards[entry.card_key] = widget
        for widget in old.values():
            widget.deleteLater()

    def _icon_ready(self, card_key, pixmap):
        widget = self.cards.get(card_key)
        if widget is not None:
            widget.tile.set_pixmap(pixmap)

    # ---------------------------------------------------------------- automatic refresh
    def schedule_refreshes(self, delays_ms):
        """Plan automatic refreshes (replaces those already planned)."""
        for timer in self.refresh_timers:
            timer.stop()
        self.refresh_timers = [self.app.later(delay, self._auto_refresh, self) for delay in delays_ms]

    def _auto_refresh(self):
        # Never while a closing runs (the list would be read mid-way), nor under an open dialog
        # (a confirmation must not disagree with the list behind it): retried shortly after.
        if self.app.busy or self.app.dialogs:
            if self.retry_timer is None:
                self.retry_timer = self.app.later(RETRY_REFRESH_MS, self._retry_refresh, self)
            return
        self.refresh()

    def _retry_refresh(self):
        self.retry_timer = None
        self._auto_refresh()

    # ---------------------------------------------------------------- filtering
    def _on_filter(self, name):
        self.filter = "selected" if name == "selected" else "all"
        self.apply_filter()

    def apply_filter(self):
        t = self.app.t
        query = self.search.text().strip().casefold()
        self.list.setUpdatesEnabled(False)
        layout = self.list_layout
        while layout.count() > 1:   # everything but the final stretch
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
        visible = [e for e in self.entries if not query or query in e.search_text]
        normal = [e for e in visible if not e.protected]
        protected = [e for e in visible if e.protected]
        if self.filter == "selected":
            normal = [e for e in normal if e.proc_key in self.selected]
            protected = []
        shown = [self.cards[e.card_key] for e in normal]
        if protected:
            shown.append(self.protected_header)
            shown += [self.cards[e.card_key] for e in protected]
        if not shown:
            if query:
                text = t("no_match", query=self.search.text().strip())
            elif self.filter == "selected":
                text = t("no_selected")
            else:
                text = t("no_windows")
            self.empty.setText(text)
            shown = [self.empty]
        for index, widget in enumerate(shown):
            layout.insertWidget(index, widget)
            widget.show()
        self.list.setUpdatesEnabled(True)
        self.update_counts()

    # ---------------------------------------------------------------- selection
    def set_selected(self, proc_key, selected):
        self.notice = None
        if selected:
            self.selected.add(proc_key)
        else:
            self.selected.discard(proc_key)
        for entry in self.entries:
            if entry.proc_key == proc_key:
                self.cards[entry.card_key].show_selected(selected)
        self.update_counts()

    def clear_selection(self):
        for key in list(self.selected):
            self.set_selected(key, False)
        if self.filter == "selected":
            self.apply_filter()

    def update_counts(self):
        app, t = self.app, self.app.t
        self.summary.setText(f"{app.tn('n_windows', len(self.windows))} · {app.tn('n_apps', self.app_count)}")
        self.filter_bar.set_text("all", t("filter_all", count=self.selectable_count))
        self.filter_bar.set_text("selected", t("filter_selected", count=len(self.selected)))
        self.filter_bar.select("selected" if self.filter == "selected" else "all")
        count = len(self.selected)
        windows = sum(1 for w in self.windows if w.key in self.selected)
        if count:
            self.selection_line.setText(f"{app.tn('n_selected', count)} · {app.tn('n_windows', windows)}")
            self.close_button.setText(app.tn("close_button", count))
        else:
            self.selection_line.setText(t("selection_none"))
            self.close_button.setText(t("close_button_none"))
        self.close_button.setEnabled(bool(count))
        self.clear_button.setVisible(bool(count))
        if self.notice:
            self.selection_line.setText(self.notice)
        instant = app.settings["instant_force"]
        self.hint.setText(t("close_hint_instant") if instant else t("close_hint", seconds=app.settings["close_timeout"]))
        self.hint_icon.setVisible(instant)

    # ---------------------------------------------------------------- closing
    def close_selected(self):
        app = self.app
        chosen = [w for w in self.windows if w.key in self.selected and not w.protected]
        if not chosen or app.busy:
            return
        targets = core.group_targets(chosen)
        instant = app.settings["instant_force"]
        timeout = 0 if instant else app.settings["close_timeout"]

        def start():
            app.start_closing(targets, timeout)

        if app.settings["confirm_before_terminate"]:
            items = [f"{app.display_name(x.exe_path) or app.t('process_n', pid=x.pid)} — "
                     f"{app.tn('n_windows', len(x.titles))}" for x in targets]
            Dialog(app, app.t("confirm_title"), app.t("confirm_message_instant" if instant else "confirm_message",
                                                      seconds=timeout), items,
                   app.tn("close_button", len(targets)), start)
        else:
            start()

    def close_explorer(self):
        """Close File Explorer windows only; explorer.exe (desktop, taskbar) keeps running."""
        app = self.app
        if app.busy or self.restarting_explorer:
            return
        count = core.close_explorer_windows()
        self._show_notice(app.tn("explorer_closed", count) if count else app.t("explorer_none"))
        self.schedule_refreshes(EXPLORER_REFRESH_MS)

    def restart_explorer(self):
        """Restart explorer.exe (desktop, taskbar, folder windows), after a confirmation."""
        app, t = self.app, self.app.t
        if app.busy or self.restarting_explorer:
            return
        Dialog(app, t("restart_explorer_title"), t("restart_explorer_message"),
               confirm_text=t("restart_explorer_confirm"), on_confirm=self._start_explorer_restart)

    def _start_explorer_restart(self):
        app = self.app
        self.restarting_explorer = True
        self.explorer_button.setEnabled(False)
        self._show_notice(app.t("explorer_restarting"), keep=True)

        def run():
            try:
                core.restart_explorer()
            except core.ProcessError as exc:
                app.call_soon(lambda error=exc: self._explorer_restarted(error))
            except Exception as exc:   # never leave the button disabled
                log.exception("explorer restart failed")
                app.call_soon(lambda error=core.ProcessError("os_error", str(exc)): self._explorer_restarted(error))
            else:
                app.call_soon(lambda: self._explorer_restarted(None))
        threading.Thread(target=run, name="explorer-restart", daemon=True).start()

    def _explorer_restarted(self, error):
        app, t = self.app, self.app.t
        self.restarting_explorer = False
        try:
            self.explorer_button.setEnabled(True)
        except RuntimeError:
            return   # page rebuilt meanwhile (language change)
        if error is None:
            self._show_notice(t("explorer_restarted"))
            self.schedule_refreshes(EXPLORER_REFRESH_MS)
        else:
            self._show_notice(None)
            Dialog(app, t("error"), t("explorer_restart_failed", error=t(error.key, detail=error.detail or "")))

    def _show_notice(self, text, keep=False):
        if self.notice_timer is not None:
            self.notice_timer.stop()
            self.notice_timer = None
        self.notice = text
        if text and not keep:
            self.notice_timer = self.app.later(NOTICE_MS, self._end_notice, self)
        self.update_counts()

    def _end_notice(self):
        self.notice_timer, self.notice = None, None
        self.update_counts()

    def focus_search(self):
        self.search.setFocus()

    def state(self):
        return {"selected": set(self.selected), "expanded": set(self.expanded), "query": self.search.text()}


# ====================================================================== closing screen

class ClosingRow(QFrame):
    def __init__(self, page, target):
        super().__init__()
        self.setProperty("card", "default")
        app = page.app
        self.page, self.target = page, target
        outer = vbox()
        self.setLayout(outer)
        top = hbox((16, 12, 16, 12), 16)
        outer.addLayout(top)
        name = app.display_name(target.exe_path) or app.t("process_n", pid=target.pid)
        pixmap = None
        if app.settings["show_icons"]:
            pixmap = app.icon_for(target.exe_path, lambda pix: self.tile.set_pixmap(pix))
        self.tile = Tile(name, pixmap)
        top.addWidget(self.tile)
        texts = vbox()
        texts.addWidget(label(name, "strong"))
        texts.addWidget(label(" · ".join([shorten(", ".join(target.titles), 80), app.t("pid", pid=target.pid)]),
                              "caption", "secondary"))
        top.addLayout(texts, 1)
        self.pill = pill()
        top.addWidget(self.pill, 0, Qt.AlignmentFlag.AlignVCenter)
        self.body = QWidget()
        body = hbox((64, 0, 16, 14), 8)
        self.body.setLayout(body)
        self.explain_icon = glyph_label("warning", 12, "caution")
        body.addWidget(self.explain_icon, 0, Qt.AlignmentFlag.AlignTop)
        self.explain = label("", "small", wrap=True)
        body.addWidget(self.explain, 1)
        self.show_button = button(app.t("show_window"), self._show, icon="window")
        self.leave_button = button(app.t("leave_open"), self._leave)
        body.addWidget(self.show_button, 0, Qt.AlignmentFlag.AlignTop)
        body.addWidget(self.leave_button, 0, Qt.AlignmentFlag.AlignTop)
        outer.addWidget(self.body)
        self.body.hide()
        self.set_waiting()

    def _style(self, text, kind):
        self.pill.setText(text)
        set_prop(self.pill, "pill", kind)

    def set_waiting(self):
        self._style(self.page.app.t("status_waiting"), "neutral")

    def set_forcing(self):
        self._style(self.page.app.t("status_forcing"), "neutral")
        self.body.hide()

    def set_result(self, result):
        app = self.page.app
        self.body.hide()
        if result.status == core.CLOSED:
            text = (app.t("status_closed", seconds=format_seconds(app.language, result.elapsed))
                    if result.elapsed >= 0.1 else app.t("log_closed"))
            self._style(text, "success")
        elif result.status == core.FORCED:
            self._style(app.t("status_forced"), "caution")
        elif result.status == core.STILL_RUNNING:
            self._style(app.t("status_still"), "caution")
            set_prop(self.explain_icon, "tone", "caution")
            self.explain.setText(app.t("still_explain", seconds=self.page.timeout))
            self.show_button.show()
            self.leave_button.show()
            self.body.show()
        else:  # FAILED
            self._style(app.t("status_failed"), "critical")
            text = app.t(result.error_key, detail=result.detail) if result.error_key else ""
            if result.error_key == "access_denied" and not app.is_admin:
                text += "\n" + app.t("admin_hint")
            set_prop(self.explain_icon, "tone", "critical")
            self.explain.setText(text[:1].upper() + text[1:])
            self.show_button.hide()
            self.leave_button.hide()
            self.body.show()

    def set_left_open(self):
        self._style(self.page.app.t("status_left"), "neutral")
        self.body.hide()

    def _leave(self):
        self.page.leave_open(self.target)

    def _show(self):
        hwnds = core.windows_of(self.target)
        if hwnds:
            winapi.bring_to_front(hwnds[0])


class ClosingPage(Page):
    def __init__(self, app):
        super().__init__(app)
        t = app.t
        self.rows, self.results, self.left_open = {}, {}, set()
        self.targets, self.timeout, self.running, self.started = [], 0, False, 0.0
        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self._tick)
        layout = vbox()
        self.setLayout(layout)
        top = vbox((PAD - 10, 20, PAD, 0), 0)
        layout.addLayout(top)
        self.back = button(t("apps_title"), self.finish, "subtle", icon="back")
        top.addWidget(self.back, 0, Qt.AlignmentFlag.AlignLeft)
        top.addSpacing(8)
        line = hbox((10, 0, 0, 0), 16)
        texts = vbox(spacing=2)
        self.title = label(t("closing_title"), "title")
        texts.addWidget(self.title)
        self.subtitle = label("", tone="secondary", wrap=True)
        texts.addWidget(self.subtitle)
        line.addLayout(texts, 1)
        self.elapsed = label("", "caption", "secondary")
        line.addWidget(self.elapsed, 0, Qt.AlignmentFlag.AlignBottom)
        top.addLayout(line)
        top.addSpacing(16)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        progress_row = hbox((10, 0, 0, 0))
        progress_row.addWidget(self.progress)
        top.addLayout(progress_row)
        top.addSpacing(16)
        area, self.list = scroll_area()
        self.list_layout = self.list.layout()
        self.list_layout.setContentsMargins(PAD - 4, 0, PAD - 16, 16)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch(1)
        layout.addWidget(area, 1)
        bar = CommandBar()
        self.summary = label("", "strong", wrap=True)
        bar.texts.addWidget(self.summary)
        bar.texts.addWidget(label(t("closing_hint"), "caption", "secondary", wrap=True))
        self.done_button = button(t("done"), self.finish)
        self.force_button = button("", self.force, "accent", icon="power")
        bar.add_buttons(self.done_button, self.force_button)
        layout.addWidget(bar)

    def start(self, targets, timeout):
        self.targets, self.timeout = targets, timeout
        self.results, self.left_open = {}, set()
        for row in self.rows.values():
            row.deleteLater()
        self.rows = {}
        for index, target in enumerate(targets):
            row = ClosingRow(self, target)
            self.list_layout.insertWidget(index, row)
            self.rows[target.key] = row
        self.title.setText(self.app.t("closing_title"))
        self.subtitle.setText(self.app.tn("closing_subtitle", len(targets)))
        self.progress.setValue(0)
        self.elapsed.setText("")
        self.started = time.monotonic()
        if timeout:
            self._run(lambda report: core.close_processes(targets, timeout, on_result=report))
        else:
            for row in self.rows.values():
                row.set_forcing()
            self.subtitle.setText(self.app.tn("forcing_subtitle", len(targets)))
            self._run(lambda report: core.force_processes(targets, on_result=report))
        self.ticker.start(200)

    def _run(self, work):
        """Run `work(report)` in a thread; each Result is handed back to the interface thread."""
        self.running = True
        self.app.set_busy(True)
        self._update()

        def report(result):
            self.app.call_soon(lambda: self._on_result(result))

        def worker():
            try:
                work(report)
            except Exception:
                log.exception("closing failed")
            self.app.call_soon(self._on_finished)

        threading.Thread(target=worker, daemon=True).start()

    def _tick(self):
        if not self.running:
            self.ticker.stop()
            return
        elapsed = time.monotonic() - self.started
        if self.timeout:
            self.progress.setValue(int(min(1.0, elapsed / self.timeout) * 1000))
            self.elapsed.setText(self.app.t("elapsed", elapsed=min(self.timeout, int(elapsed)), seconds=self.timeout))

    def _on_result(self, result):
        self.results[result.target.key] = result
        row = self.rows.get(result.target.key)
        if row is not None:
            row.set_result(result)
        self._update()

    def _on_finished(self):
        self.running = False
        self.ticker.stop()
        self.app.set_busy(False)
        # Applications were just closed: bring the list of open windows up to date by itself.
        self.app.list_page.schedule_refreshes(AFTER_CLOSE_REFRESH_MS)
        self.progress.setValue(1000)
        if self.timeout:
            self.elapsed.setText(self.app.t("elapsed", elapsed=self.timeout, seconds=self.timeout))
        self.title.setText(self.app.t("closing_done_title"))
        if not self.timeout:
            self.subtitle.setText(self.app.tn("forced_subtitle", len(self.targets)))
        self._update()

    def still_running(self):
        return [r.target for r in self.results.values()
                if r.status == core.STILL_RUNNING and r.target.key not in self.left_open]

    def _update(self):
        app = self.app
        counts = {"closed": 0, "forced": 0, "still": 0, "failed": 0, "left": len(self.left_open)}
        for key, result in self.results.items():
            if key in self.left_open:
                continue
            status = {core.CLOSED: "closed", core.FORCED: "forced", core.STILL_RUNNING: "still"}.get(result.status, "failed")
            counts[status] += 1
        waiting = len(self.targets) - len(self.results)
        parts = [app.tn(f"sum_{name}", count) for name, count in counts.items() if count]
        if waiting:
            parts.append(app.tn("sum_waiting", waiting))
        self.summary.setText(" · ".join(parts))
        still = self.still_running()
        if still and not self.running:
            text = (app.t("force_one_named", name=app.display_name(still[0].exe_path) or app.t("process_n", pid=still[0].pid))
                    if len(still) == 1 else app.t("force_count", count=len(still)))
            self.force_button.setText(text)
            self.force_button.show()
        else:
            self.force_button.hide()
        self.done_button.setEnabled(not self.running)
        self.back.setEnabled(not self.running)

    def leave_open(self, target):
        self.left_open.add(target.key)
        self.rows[target.key].set_left_open()
        core.log_target("left_open", target)
        self._update()

    def force(self):
        targets = self.still_running()
        if not targets or self.running:
            return
        for target in targets:
            self.rows[target.key].set_forcing()
        self.started = time.monotonic()
        self._run(lambda report: core.force_processes(targets, on_result=report))

    def finish(self):
        if self.running:
            return
        self.app.show_page("apps")
        self.app.list_page.refresh()


# ====================================================================== log

LOG_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)(?:,\d+)? \w+ (closed|forced|still_running|failed|protected|left_open) "
                      r"pid=(\d+) exe=(.*?)(?: windows=(\d+))? titles=(\[.*?\])(?: error=(\S+)(?: (.*))?)?$")


def format_log_line(app, line):
    match = LOG_LINE.match(line.rstrip("\n"))
    if not match:
        return line.rstrip("\n")
    when, status, pid, exe, windows, titles, error_key, detail = match.groups()
    name = app.display_name(exe) if exe and exe != "None" else app.t("process_n", pid=pid)
    try:
        titles = "; ".join(ast.literal_eval(titles))
    except (ValueError, SyntaxError):
        pass
    if not titles and windows:   # titles kept out of the log: say how many windows instead
        titles = app.tn("n_windows", int(windows))
    status_text = app.t("status_left") if status == "left_open" else app.t(f"log_{status}")
    text = f"{when}   {status_text:<18} {name} ({pid})   {shorten(titles, 90)}"
    if error_key:
        try:
            text += f"   — {app.t(error_key, detail=detail or '')}"
        except KeyError:
            text += f"   — {error_key} {detail or ''}"
    return text


class LogPage(Page):
    def __init__(self, app):
        super().__init__(app)
        t = app.t
        layout = vbox((PAD, 28, PAD, 28), 0)
        self.setLayout(layout)
        header, texts, actions = page_header(t("log_title"))
        texts.addWidget(label(str(settings_mod.log_path()), tone="secondary"))
        actions.addWidget(button(t("refresh"), self.load, icon="refresh"), 0, Qt.AlignmentFlag.AlignTop)
        actions.addWidget(button(t("log_open_file"), self.open_file, icon="open"), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
        layout.addSpacing(20)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.text, 1)

    def load(self):
        try:
            with open(settings_mod.log_path(), encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()[-LOG_LINES:]
        except OSError:
            lines = []
        text = "\n".join(format_log_line(self.app, line) for line in lines if line.strip()) or self.app.t("log_empty")
        self.text.setPlainText(text)
        self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())

    def open_file(self):
        path = settings_mod.log_path()
        if path.exists() and hasattr(os, "startfile"):
            os.startfile(path)  # noqa: S606 - opens the log in the user's default text editor


# ====================================================================== background

class BackgroundPage(Page):
    """The background processes (no window) using the most memory."""

    def __init__(self, app):
        super().__init__(app)
        t = app.t
        layout = vbox()
        self.setLayout(layout)
        top = vbox((PAD, 28, PAD, 0), 8)
        layout.addLayout(top)
        header, titles, actions = page_header(t("background_title"))
        self.summary = label("", tone="secondary", wrap=True)
        titles.addWidget(self.summary)
        actions.addWidget(button(t("refresh"), self.load, icon="refresh"), 0, Qt.AlignmentFlag.AlignTop)
        top.addLayout(header)
        top.addSpacing(12)
        self.include_system = toggle_with_state(app, app.settings["background_include_system"],
                                                self._on_include_system)
        settings_card("monitor", t("background_include_system"), t("background_include_system_hint"),
                      self.include_system, top)
        self.hint = infobar(t("background_hint"))
        top.addWidget(self.hint)
        top.addSpacing(8)
        area, self.list = scroll_area()
        self.list_layout = self.list.layout()
        self.list_layout.setContentsMargins(PAD - 4, 0, PAD - 16, 16)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch(1)
        layout.addWidget(area, 1)
        self.report = None
        self.generation = 0   # the latest read; older ones arriving late are dropped

    def _on_include_system(self, value):
        self.app.update_settings(background_include_system=value)
        self.load()

    def load(self):
        """Read the processes on a worker thread: opening every process can take a moment and the
        window must stay responsive. The current rows stay until the new ones are ready."""
        self.generation += 1
        generation, include_system = self.generation, self.app.settings["background_include_system"]

        def read():
            try:
                result = core.background_processes(core.list_windows(), include_system=include_system)
            except Exception as exc:   # shown on the page; never lost in a dead thread
                if not isinstance(exc, OSError):
                    log.exception("background processes")
                result = exc
            self.app.call_soon(lambda: self._show(generation, result))
        threading.Thread(target=read, name="background", daemon=True).start()

    def _show(self, generation, result):
        if generation != self.generation:
            return
        app, t = self.app, self.app.t
        layout = self.list_layout
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if isinstance(result, Exception):
            self.report = None
            self.summary.setText(t("background_error", error=result))
            return
        self.report = report = result
        if not report.top:
            self.summary.setText(t("background_empty"))
            return
        total = format_memory(app.language, report.total)
        self.summary.setText(f"{app.tn('background_top', len(report.top))} · "
                             f"{app.tn('background_count', report.count, total=total)}")
        largest = max(report.top[0].memory, 1)
        app.preload_icons(p.exe_path for p in report.top)
        for rank, process in enumerate(report.top, 1):
            layout.insertWidget(rank - 1, self._row(rank, process, largest))

    def _row(self, rank, process, largest):
        app = self.app
        box = card()
        row = hbox((12, 12, 16, 12), 16)
        box.setLayout(row)
        number = label(str(rank), "caption", "secondary")
        number.setFixedWidth(20)
        number.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(number)
        name = app.display_name(process.exe_path) if process.exe_path else process.app_name
        tile = Tile(name, None, process.protected)
        if process.exe_path and app.settings["show_icons"]:
            tile.set_pixmap(app.icon_for(process.exe_path, on_ready=tile.set_pixmap))
        row.addWidget(tile)
        texts = vbox()
        line = hbox(spacing=8)
        line.addWidget(label(name, "strong", "secondary" if process.protected else None))
        if process.protected:
            badge = label(app.t("protected_badge"))
            badge.setProperty("badge", "true")
            line.addWidget(badge)
        line.addStretch(1)
        texts.addLayout(line)
        texts.addWidget(label(f"{process.name} · {app.t('pid', pid=process.pid)}", "caption", "secondary"))
        row.addLayout(texts, 1)
        memory = vbox(spacing=6)
        size = label(format_memory(app.language, process.memory), "strong")
        size.setAlignment(Qt.AlignmentFlag.AlignRight)
        memory.addWidget(size)
        bar = QProgressBar()
        bar.setRange(0, 1000)
        bar.setValue(int(process.memory / largest * 1000))
        bar.setTextVisible(False)
        bar.setFixedWidth(160)
        memory.addWidget(bar)
        row.addLayout(memory)
        return box


# ====================================================================== settings

class SettingsPage(Page):
    def __init__(self, app):
        super().__init__(app)
        t, s = app.t, app.settings
        layout = vbox()
        self.setLayout(layout)
        self.scroll, content = scroll_area()
        layout.addWidget(self.scroll)
        body = content.layout()
        body.setContentsMargins(PAD, 28, PAD - 12, 36)
        body.setSpacing(4)
        body.addWidget(label(t("settings_title"), "title"))
        body.addWidget(label(t("settings_subtitle", path=settings_mod.data_dir()), tone="secondary", wrap=True))
        body.addSpacing(8)

        # ---- display
        section_header(t("section_display"), body)
        self.language_values = list(LANGUAGE_NAMES.items())
        language = ComboBox([name for _, name in self.language_values])
        language.setCurrentText(LANGUAGE_NAMES[s["language"]])
        language.currentTextChanged.connect(self._on_language)
        settings_card("globe", t("language"), t("language_hint"), language, body)
        self.theme_values = [(code, t(f"theme_{code}")) for code in settings_mod.THEMES]
        self.theme_box = ComboBox([name for _, name in self.theme_values])
        self.theme_box.setCurrentText(dict(self.theme_values)[s["theme"]])
        self.theme_box.currentTextChanged.connect(self._on_theme)
        settings_card("color", t("theme"), t("theme_hint"), self.theme_box, body)
        supported = app.translucent
        self.backdrop_values = [(code, t(f"backdrop_{code}")) for code in settings_mod.BACKDROPS]
        self.backdrop_box = ComboBox([name for _, name in self.backdrop_values])
        self.backdrop_box.setCurrentText(dict(self.backdrop_values)[s["backdrop"] if supported else "none"])
        self.backdrop_box.setEnabled(supported)
        self.backdrop_box.currentTextChanged.connect(self._on_backdrop)
        settings_card("transparency", t("mica"), t("mica_hint") if supported else t("mica_unavailable"),
                      self.backdrop_box, body)
        level = QWidget()
        level_layout = hbox(spacing=12)
        level.setLayout(level_layout)
        self.level_slider = QSlider(Qt.Orientation.Horizontal)
        self.level_slider.setRange(settings_mod.TRANSPARENCY_MIN, settings_mod.TRANSPARENCY_MAX)
        self.level_slider.setValue(s["transparency"])
        self.level_slider.setFixedWidth(200)
        self.level_value = label(t("percent_value", value=s["transparency"]))
        self.level_value.setFixedWidth(48)
        self.level_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        level_layout.addWidget(self.level_slider)
        level_layout.addWidget(self.level_value)
        self.level_timer = QTimer(self)
        self.level_timer.setSingleShot(True)
        self.level_timer.timeout.connect(lambda: app.update_settings(transparency=self.level_slider.value()))
        self.level_slider.valueChanged.connect(self._on_level)
        self.level_card = settings_card("transparency", t("transparency_level"), t("transparency_hint"), level, body)
        self.show_backdrop_state()

        # ---- closing
        section_header(t("section_closing"), body)
        self._switch_card(body, "check", "confirm_before_terminate", t("confirm_before_terminate"), t("confirm_hint"))
        self._switch_card(body, "lightning", "instant_force", t("instant_force"), t("instant_force_hint"))
        delay = QWidget()
        delay_layout = hbox(spacing=12)
        delay.setLayout(delay_layout)
        self.timeout_slider = QSlider(Qt.Orientation.Horizontal)
        self.timeout_slider.setRange(settings_mod.TIMEOUT_MIN, settings_mod.TIMEOUT_MAX)
        self.timeout_slider.setValue(s["close_timeout"])
        self.timeout_slider.setFixedWidth(200)
        self.timeout_value = label(t("seconds_value", seconds=s["close_timeout"]))
        self.timeout_value.setFixedWidth(40)
        self.timeout_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        delay_layout.addWidget(self.timeout_slider)
        delay_layout.addWidget(self.timeout_value)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(lambda: app.update_settings(close_timeout=self.timeout_slider.value()))
        self.timeout_slider.valueChanged.connect(self._on_timeout)
        settings_card("timer", t("close_timeout"), t("timeout_hint"), delay, body)

        # ---- window list
        section_header(t("section_list"), body)
        self._switch_card(body, "list", "group_by_app", t("group_by_app"), t("group_hint"))
        self._switch_card(body, "image", "show_icons", t("show_icons"), t("icons_hint"))

        # ---- shortcut
        section_header(t("section_shortcut"), body)
        buttons = QWidget()
        buttons_layout = hbox(spacing=8)
        buttons.setLayout(buttons_layout)
        buttons_layout.addWidget(button(t("shortcut_create"), self._create_shortcut))
        self.pin_button = button(t("shortcut_pin"), self._pin_shortcut, icon="pin")
        buttons_layout.addWidget(self.pin_button)
        shortcut_card = settings_card("link", t("shortcut_card"), t("shortcut_hint"), buttons, body)
        self.shortcut_status = label("", "caption", "secondary", wrap=True)
        shortcut_card.texts.addWidget(self.shortcut_status)
        # Named in the language of its creation: look for every language's name, current first.
        self.shortcut_file = shortcut.find_any([t("shortcut_name")] + [
            texts["shortcut_name"] for code, texts in TEXT.items() if code != app.language])
        self._show_shortcut_status()

        # ---- about
        section_header(t("section_about"), body)
        about = card()
        about_layout = vbox()
        about.setLayout(about_layout)
        head = hbox((16, 14, 16, 14), 16)
        logo = QLabel()
        logo.setPixmap(QIcon(resource_path("app.ico")).pixmap(32, 32))
        logo.setFixedSize(32, 32)
        head.addWidget(logo)
        names = vbox()
        names.addWidget(label("CloseAllPython", "strong"))
        names.addWidget(label(t("about_line", version=__version__), "caption", "secondary"))
        head.addLayout(names, 1)
        project = button(updater.PROJECT_PAGE.removeprefix("https://"), self._open_project, "link")
        project.setCursor(Qt.CursorShape.PointingHandCursor)
        head.addWidget(project)
        about_layout.addLayout(head)
        rights = t("rights_admin") if app.is_admin else t("rights_user")
        row = self._about_row(about_layout, t("rights_line", rights=rights))
        if not app.is_admin:
            row.addWidget(button(t("admin_restart"), app.restart_as_admin, icon="shield"))
        row = self._about_row(about_layout, t("log_line", name=settings_mod.log_path().name))
        row.addWidget(button(t("open_log"), lambda: app.show_page("log")))
        row = self._about_row(about_layout, t("log_window_titles"), t("log_window_titles_hint"))
        row.addWidget(toggle_with_state(app, s["log_window_titles"],
                                        lambda value: app.update_settings(log_window_titles=value)))
        row = self._about_row(about_layout, t("auto_update"), t("auto_update_hint"))
        self.check_button = button(t("check_updates"), app.updates.check, icon="sync")
        row.addWidget(self.check_button)
        row.addSpacing(8)
        row.addWidget(toggle_with_state(app, s["auto_update"], lambda value: app.update_settings(auto_update=value)))
        self.update_status = label("", "caption", "secondary", wrap=True)
        row.texts.addWidget(self.update_status)
        body.addWidget(about)
        body.addStretch(1)
        app.updates.on_status = self._show_update_status
        self._show_update_status()

    def _about_row(self, about_layout, title, description=None):
        about_layout.addWidget(divider())
        row = hbox((64, 10, 16, 10), 12)
        texts = vbox()
        texts.addWidget(label(title, wrap=True))
        if description:
            texts.addWidget(label(description, "caption", "secondary", wrap=True))
        row.addLayout(texts, 1)
        row.texts = texts
        about_layout.addLayout(row)
        return row

    def _switch_card(self, body, glyph, key, title, hint):
        control = toggle_with_state(self.app, self.app.settings[key],
                                    lambda value: self.app.update_settings(**{key: value}))
        return settings_card(glyph, title, hint, control, body)

    def _open_project(self):
        import webbrowser

        webbrowser.open(updater.PROJECT_PAGE)   # a fixed constant, never text from the network

    def _show_shortcut_status(self):
        file = self.shortcut_file
        self.shortcut_status.setText(self.app.t("shortcut_ready", path=file) if file else "")
        self.shortcut_status.setVisible(bool(file))
        self.pin_button.setEnabled(bool(file))

    def _create_shortcut(self):
        t = self.app.t
        try:
            # An existing shortcut is updated under its own name rather than duplicated.
            existing = self.shortcut_file if self.shortcut_file and self.shortcut_file.is_file() else None
            self.shortcut_file = shortcut.create(existing.stem if existing else t("shortcut_name"),
                                                 t("shortcut_description"), folder=existing.parent if existing else None)
        except shortcut.ShortcutError as exc:
            Dialog(self.app, t("error"), t("shortcut_failed", error=exc.detail))
            return
        self._show_shortcut_status()

    def _pin_shortcut(self):
        t = self.app.t
        Dialog(self.app, t("shortcut_pin_title"), t("shortcut_pin_message"), confirm_text=t("shortcut_show"),
               on_confirm=self._show_shortcut_file, cancel_text=t("ok"))

    def _show_shortcut_file(self):
        try:
            shortcut.reveal(self.shortcut_file)
        except OSError as exc:
            Dialog(self.app, self.app.t("error"), self.app.t("shortcut_failed", error=exc.strerror or exc))

    def _show_update_status(self):
        updates = self.app.updates
        try:
            text = updates.status_text()
            self.update_status.setText(text)
            self.update_status.setVisible(bool(text))
            self.check_button.setEnabled(not (updates.running or updates.installed))
        except RuntimeError:
            pass   # page destroyed (language change): the new page registers itself

    def _on_language(self, value):
        code = next(code for code, name in self.language_values if name == value)
        self.app.update_settings(language=code)

    def show_theme(self):
        """The theme changed elsewhere (the dark / light button): show it in the list."""
        self.theme_box.blockSignals(True)
        self.theme_box.setCurrentText(dict(self.theme_values)[self.app.settings["theme"]])
        self.theme_box.blockSignals(False)

    def _on_backdrop(self, value):
        code = next(code for code, name in self.backdrop_values if name == value)
        self.app.update_settings(backdrop=code)
        self.show_backdrop_state()

    def show_backdrop_state(self):
        """The level only means something while an effect is on."""
        self.level_card.setEnabled(self.app.translucent and self.app.settings["backdrop"] != "none")

    def _on_level(self, value):
        self.level_value.setText(self.app.t("percent_value", value=value))
        self.level_timer.start(120)   # the whole window is restyled: wait for the slider to settle

    def _on_theme(self, value):
        code = next(code for code, name in self.theme_values if name == value)
        self.app.update_settings(theme=code)

    def _on_timeout(self, value):
        self.timeout_value.setText(self.app.t("seconds_value", seconds=value))
        self.save_timer.start(300)


# ====================================================================== updates

class Updates:
    """Checks GitHub for a newer release and installs it, off the interface thread.

    Manual check (Settings): asks before installing, then restarts into the new version.
    Automatic check (startup, when enabled): installs silently and offers to restart; the new
    version is used at the next start anyway. Results go to `status` (shown on the settings page).
    """

    def __init__(self, app, module=updater):
        self.app, self.module = app, module
        self.running = False
        self.status = None        # (i18n key, values) or None
        self.on_status = None     # callback of the settings page
        self.installed = None     # Path of an executable updated during this session

    def set_status(self, key, **values):
        self.status = (key, values) if key else None
        if self.on_status:
            self.on_status()

    def status_text(self):
        if not self.status:
            return ""
        key, values = self.status
        values = dict(values)
        if "error" in values and isinstance(values["error"], tuple):
            error_key, error_values = values["error"]
            values["error"] = self.app.t(error_key, **error_values)
        return self.app.t(key, **values)

    def _thread(self, work, done, failed):
        def run():
            try:
                result = work()
            except self.module.UpdateError as exc:
                self.app.call_soon(lambda error=exc: failed(error))
            except Exception:   # never let a network oddity kill the worker silently
                log.exception("update failed")
                self.app.call_soon(lambda: failed(self.module.UpdateError("update_err_response")))
            else:
                self.app.call_soon(lambda: done(result))
        threading.Thread(target=run, name="updates", daemon=True).start()

    def check(self, automatic=False):
        if self.running or self.installed:
            return
        self.running = True
        self.set_status("update_checking")
        self._thread(self.module.fetch_latest, lambda release: self._checked(release, automatic),
                     self._failed)

    def _failed(self, exc):
        self.running = False
        log.info("update check failed: %s %s", exc.key, exc.values)
        self.set_status("update_failed", error=(exc.key, exc.values))

    def _checked(self, release, automatic):
        self.running = False
        if not self.module.is_newer(release):
            self.set_status("update_latest", version=__version__)
            return
        self.set_status("update_available", version=release.label)
        exe = self.module.current_executable()
        app, t = self.app, self.app.t
        if exe is None:
            if not automatic:
                Dialog(app, t("update_title"), t("update_source_message", version=release.label, current=__version__),
                       confirm_text=t("update_open_page"), on_confirm=lambda: self._open_page(release))
        elif automatic:
            self.install(release, exe, restart=False)
        else:
            Dialog(app, t("update_title"), t("update_message", version=release.label, current=__version__),
                   confirm_text=t("update_install"), on_confirm=lambda: self.install(release, exe, restart=True))

    def _open_page(self, release):
        import webbrowser

        webbrowser.open(self.module.release_page(release.page))   # checked again: never a local file

    def install(self, release, exe, restart):
        if self.running:
            return
        self.running = True
        self.set_status("update_downloading", version=release.label, percent=0)
        last = [-1]

        def progress(done, total):
            percent = int(done * 100 / total) if total else 0
            if percent != last[0]:
                last[0] = percent
                self.app.call_soon(lambda: self.set_status("update_downloading", version=release.label,
                                                           percent=percent))

        self._thread(lambda: self.module.update(exe, release, progress=progress),
                     lambda path: self._installed(release, path, restart),
                     self._failed)

    def _installed(self, release, path, restart):
        self.running = False
        self.installed = path
        self.set_status("update_installed", version=release.label)
        if restart:
            self.restart()
        else:
            t = self.app.t
            Dialog(self.app, t("update_done_title"), t("update_done_message", version=release.label),
                   confirm_text=t("update_restart"), on_confirm=self.restart, cancel_text=t("update_later"))

    def restart(self):
        if self.installed is None:
            return
        if self.app.busy:
            Dialog(self.app, self.app.t("update_title"), self.app.t("update_busy"))
            return
        try:
            self.module.relaunch(self.installed)
        except OSError as exc:
            Dialog(self.app, self.app.t("error"), self.app.t("update_failed", error=exc))
            return
        self.app.close()


# ====================================================================== window

class NavItem(QAbstractButton, Painted):
    """A NavigationView item: icon and label; the selected one gets a fill and an accent mark."""

    def __init__(self, glyph, text, page=True):
        super().__init__()
        self.glyph, self.compact = glyph, False
        self.setText(text)
        if page:   # a page of the window; otherwise a plain action (never selected)
            self.setCheckable(True)
            self.setAutoExclusive(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedHeight(36)
        self.setToolTip(text)

    def set_compact(self, compact):
        self.compact = compact
        self.update()

    def set_content(self, glyph, text):
        self.glyph = glyph
        self.setText(text)
        self.setToolTip(text)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        if self.isChecked() or self.underMouse():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor("subtle_pressed" if self.isDown() else "subtle_hover"))
            painter.drawRoundedRect(rect, 4, 4)
        if self.isChecked():
            painter.setBrush(qcolor("accent"))
            painter.drawRoundedRect(QRectF(0, self.height() / 2 - 8, 3, 16), 1.5, 1.5)
        painter.setPen(qcolor("text"))
        painter.setFont(glyph_font(16))
        painter.drawText(QRectF(12, 0, 20, self.height()), Qt.AlignmentFlag.AlignCenter, THEME.glyph(self.glyph))
        if not self.compact:
            font = QFont(THEME.ui_font)
            font.setPixelSize(14)
            painter.setFont(font)
            painter.drawText(QRectF(48, 0, self.width() - 52, self.height()),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        painter.end()


class Dispatcher(QObject):
    """Runs callables on the interface thread, whatever thread asks."""

    call = Signal(object)


def pick_font(families, *names, default):
    return next((name for name in names if name in families), default)


class App(QMainWindow):
    def __init__(self):
        self.qapp = QApplication.instance() or QApplication(sys.argv[:1])
        self.qapp.setStyle("Fusion")
        super().__init__()
        self.settings = settings_mod.load_settings()
        core.log_titles = self.settings["log_window_titles"]
        try:
            self.mica_supported = bool(winapi.backdrop_supported())
        except Exception:
            self.mica_supported = False
        # Qt needs a translucent window before it exists; whether Mica shows is decided later.
        self.translucent = self.mica_supported
        if self.translucent:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.mica = False
        self.is_admin = winapi.is_admin()
        self.own_pids = core.own_pids(include_ancestors=False)
        self.icon_cache = {}          # lower-case path -> QPixmap or None
        self.icon_waiters = {}        # lower-case path -> callbacks waiting for that icon
        self.icon_pending = set()     # lower-case paths queued for extraction
        self.icon_jobs = None         # queue of paths for the icon thread (started on first use)
        self.dialogs = 0              # open dialogs
        self.names = {}
        self.busy = False
        self.current = "apps"
        self.nav_compact = False
        self.nav_choice = None        # set by the ☰ button; otherwise the window's width decides
        self.nav_pane = None
        self.dispatcher = Dispatcher()
        self.dispatcher.call.connect(self._run_call, Qt.ConnectionType.QueuedConnection)
        families = set(QFontDatabase.families())
        default = self.qapp.font().family()
        self.fonts = {
            "ui_font": pick_font(families, "Segoe UI Variable Text", "Segoe UI", default=default),
            "display_font": pick_font(families, "Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI",
                                      default=default),
            "mono_font": pick_font(families, "Cascadia Mono", "Consolas", "DejaVu Sans Mono", default="monospace"),
            "icon_font": pick_font(families, *ICON_FAMILIES, default=None),
        }
        try:
            self.accent = accent_shades(winapi.accent_palette())
        except Exception:
            self.accent = accent_shades(None)
        self.setWindowTitle(f"CloseAllPython {__version__}")
        self.setWindowIcon(QIcon(resource_path("app.ico")))
        self.resize(1180, 760)
        self.setMinimumSize(880, 600)
        self.updates = Updates(self)
        updater.cleanup()   # leftovers of an update installed by the previous run
        self.list_page = None
        self.apply_theme(native=False)
        self.build()
        QShortcut(QKeySequence("F5"), self, lambda: self.list_page.refresh() if self.current == "apps" else None)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: (self.show_page("apps"), self.list_page.focus_search()))
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._system_theme_changed)
        if self.settings["auto_update"] and updater.current_executable() is not None:
            self.later(UPDATE_STARTUP_DELAY_MS, lambda: self.updates.check(automatic=True))

    # ---------------------------------------------------------------- helpers
    @property
    def language(self):
        return self.settings["language"]

    def t(self, key, **values):
        return translate(self.language, key, **values)

    def tn(self, key, count, **values):
        return translate_n(self.language, key, count, **values)

    def call_soon(self, callback):
        """Thread-safe: run `callback` on the interface thread."""
        self.dispatcher.call.emit(callback)

    def _run_call(self, callback):
        try:
            callback()
        except Exception:
            self.report_callback_exception(*sys.exc_info())

    def later(self, ms, callback, owner=None):
        """A single-shot timer that can be stopped."""
        timer = QTimer(owner or self)
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timer.start(ms)
        return timer

    def report_callback_exception(self, exc, value, tb):
        """An interface callback raised: save the details and say so, instead of a silent
        failure (the windowed executable has no console)."""
        import traceback

        details = "".join(traceback.format_exception(exc, value, tb))
        path = crash.write_report(details)
        log.error("UI callback failed:\n%s", details)
        if getattr(self, "_reporting", False):
            return
        self._reporting = True
        try:
            Dialog(self, self.t("unexpected_title"),
                   self.t("unexpected_message", error=f"{exc.__name__}: {value}", path=path or "-"))
        except Exception:
            crash.message_box(details)
        finally:
            self._reporting = False

    def display_name(self, exe_path):
        """Product name from the executable's version resource ("Visual Studio Code"), else its file name."""
        if not exe_path:
            return ""
        key = exe_path.lower()
        if key not in self.names:
            name = None
            try:
                name = winapi.file_description(exe_path)
            except Exception:
                log.debug("no description for %s", exe_path, exc_info=True)
            self.names[key] = shorten(name, 40) if name else ntpath.splitext(ntpath.basename(exe_path))[0]
        return self.names[key]

    def icon_for(self, exe_path, on_ready=None):
        """QPixmap of an executable's icon if already extracted, else None.

        Icons are extracted on a background thread so the window never waits on the disk;
        `on_ready(pixmap)` is called on the interface thread once this one is available.
        """
        if not exe_path:
            return None
        key = exe_path.lower()
        if key in self.icon_cache:
            return self.icon_cache[key]
        if on_ready is not None:
            self.icon_waiters.setdefault(key, []).append(on_ready)
        self._request_icon(exe_path)
        return None

    def preload_icons(self, paths):
        """Queue every listed icon, so scrolling never shows a missing one for long."""
        for path in paths:
            if path and path.lower() not in self.icon_cache:
                self._request_icon(path)

    def _request_icon(self, exe_path):
        import queue

        key = exe_path.lower()
        if key in self.icon_pending:
            return
        self.icon_pending.add(key)
        if self.icon_jobs is None:
            self.icon_jobs = queue.Queue()
            threading.Thread(target=self._icon_worker, args=(self.icon_jobs,), daemon=True).start()
        self.icon_jobs.put(exe_path)

    def _icon_worker(self, jobs):
        while True:
            path = jobs.get()
            picture = None
            try:
                picture = winapi.exe_icon_image(path, ICON_SOURCE_SIZE)
            except Exception:  # an icon is cosmetic: never let it break anything
                log.debug("icon failed for %s", path, exc_info=True)
            self.call_soon(lambda path=path, picture=picture: self._icon_ready(path, picture))

    def _icon_ready(self, exe_path, picture):
        key = exe_path.lower()
        self.icon_pending.discard(key)
        pixmap = None
        if picture is not None:
            image = picture.convert("RGBA")
            data = image.tobytes("raw", "RGBA")
            qimage = QImage(data, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy()
            pixmap = QPixmap.fromImage(qimage)
            pixmap.setDevicePixelRatio(image.width / ICON_SIZE)
        self.icon_cache[key] = pixmap
        for callback in self.icon_waiters.pop(key, []):
            if pixmap is not None:
                try:
                    callback(pixmap)
                except RuntimeError:
                    pass   # the widget was rebuilt meanwhile

    # ---------------------------------------------------------------- theme and Mica
    def is_dark(self):
        theme = self.settings["theme"]
        if theme in ("dark", "light"):
            return theme == "dark"
        hints = QGuiApplication.styleHints()
        scheme = getattr(hints, "colorScheme", lambda: None)()
        return scheme == Qt.ColorScheme.Dark

    def _system_theme_changed(self, _scheme):
        if self.settings["theme"] == "system" and not getattr(self, "_theme_busy", False):
            self.apply_theme()

    def apply_theme(self, native=True):
        """Colours of the light or dark theme, Mica on or off, without rebuilding anything."""
        global THEME
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "setColorScheme"):   # Qt's own parts (title bar, menus) follow the setting too
            wanted = {"dark": Qt.ColorScheme.Dark, "light": Qt.ColorScheme.Light}.get(self.settings["theme"],
                                                                                     Qt.ColorScheme.Unknown)
            self._theme_busy = True
            try:
                hints.setColorScheme(wanted)
            finally:
                self._theme_busy = False
        dark = self.is_dark()
        backdrop = self.settings["backdrop"]
        self.mica = self.translucent and backdrop != "none"
        if native and self.translucent:
            hwnd = int(self.winId())
            try:
                winapi.set_dark_title_bar(hwnd, dark)
                if not winapi.set_backdrop(hwnd, backdrop if self.mica else "none") and self.mica:
                    log.info("Mica refused by Windows: plain background")
                    self.mica = False
            except Exception:
                log.debug("backdrop failed", exc_info=True)
                self.mica = False
        elif native:
            try:
                winapi.set_dark_title_bar(int(self.winId()), dark)
            except Exception:
                log.debug("title bar colour failed", exc_info=True)
        THEME = Theme(dark=dark, mica=self.mica, backdrop=backdrop,
                      transparency=self.settings["transparency"], accent=self.accent, **self.fonts)
        self.qapp.setStyleSheet(THEME.style_sheet())
        refresh_glyphs()
        self.update_theme_item()
        for widget in self.findChildren(QWidget):
            if isinstance(widget, Painted):
                widget.update()

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_shown", False):
            self._shown = True
            self.apply_theme()   # the native window exists now: title bar colour and Mica

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for dialog in self.findChildren(Dialog):
            dialog.setGeometry(self.rect())
        # As WinUI's NavigationView: icons only when the window is narrow, unless the ☰ button decided.
        if self.nav_choice is None and getattr(self, "nav_pane", None) is not None:
            self.set_nav_compact(self.width() < NAV_AUTO_COMPACT)

    # ---------------------------------------------------------------- layout
    def build(self):
        state = self.list_page.state() if self.list_page is not None else None
        old = self.centralWidget()
        t = self.t
        self.install_translator()
        root = QWidget()
        root.setObjectName("root")
        layout = hbox()
        root.setLayout(layout)
        self.nav_pane = QWidget()
        self.nav_pane.setObjectName("nav")
        self.nav_pane.setFixedWidth(NAV_COMPACT_WIDTH if self.nav_compact else NAV_WIDTH)
        nav = vbox((4, 4, 6, 8), 2)
        self.nav_pane.setLayout(nav)
        toggle = icon_button("menu", self.toggle_nav, tooltip=t("nav_toggle"))
        toggle.setFixedSize(40, 36)
        nav.addWidget(toggle)
        nav.addSpacing(4)
        self.nav = {name: NavItem(glyph, t(f"nav_{name}")) for name, glyph in
                    (("apps", "apps"), ("background", "memory"), ("log", "log"), ("settings", "settings"))}
        for name, item in self.nav.items():
            item.clicked.connect(lambda _checked=False, n=name: self.show_page(n))
            item.set_compact(self.nav_compact)
        for name in ("apps", "background", "log"):
            nav.addWidget(self.nav[name])
        nav.addStretch(1)
        # Dark / light switch: shows what a click gives (the sun in the dark theme, the moon in the light).
        self.theme_item = NavItem("sun", "", page=False)
        self.theme_item.set_compact(self.nav_compact)
        self.theme_item.clicked.connect(self.toggle_theme)
        self.update_theme_item()
        nav.addWidget(self.theme_item)
        nav.addWidget(self.nav["settings"])
        layout.addWidget(self.nav_pane)
        layer = QFrame()
        layer.setObjectName("layer")
        layer_layout = vbox((1, 1, 0, 0))
        layer.setLayout(layer_layout)
        self.stack = QStackedWidget()
        layer_layout.addWidget(self.stack)
        layout.addWidget(layer, 1)
        self.list_page = ListPage(self, state)
        self.pages = {"apps": self.list_page, "closing": ClosingPage(self), "background": BackgroundPage(self),
                      "log": LogPage(self), "settings": SettingsPage(self)}
        for page in self.pages.values():
            self.stack.addWidget(page)
        self.setCentralWidget(root)
        if old is not None:
            old.deleteLater()
        self.list_page.refresh()
        self.show_page(self.current if self.current != "closing" else "apps")

    def update_theme_item(self):
        if getattr(self, "theme_item", None) is None:
            return
        if self.is_dark():
            self.theme_item.set_content("sun", self.t("nav_to_light"))
        else:
            self.theme_item.set_content("moon", self.t("nav_to_dark"))

    def toggle_theme(self):
        """Switch between the dark and the light theme (it replaces 'Follow Windows' until changed)."""
        self.update_settings(theme="light" if self.is_dark() else "dark")
        settings = self.pages.get("settings")
        if settings is not None:
            settings.show_theme()

    def install_translator(self):
        """Qt's own texts (the Copy / Paste menu of text fields) in the interface's language."""
        if getattr(self, "translator", None) is not None:
            self.qapp.removeTranslator(self.translator)
        self.translator = QTranslator(self)
        folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if self.translator.load(f"qtbase_{self.language}", folder):
            self.qapp.installTranslator(self.translator)

    def toggle_nav(self):
        self.nav_choice = not self.nav_compact
        self.set_nav_compact(self.nav_choice)

    def set_nav_compact(self, compact):
        if compact == self.nav_compact:
            return
        self.nav_compact = compact
        self.nav_pane.setFixedWidth(NAV_COMPACT_WIDTH if self.nav_compact else NAV_WIDTH)
        for item in (*self.nav.values(), self.theme_item):
            item.set_compact(self.nav_compact)

    def show_page(self, name):
        if self.busy and name != "closing":
            return
        self.current = name
        if name == "log":
            self.pages["log"].load()
        elif name == "background":
            self.pages["background"].load()
        self.stack.setCurrentWidget(self.pages[name])
        active = "apps" if name == "closing" else name
        self.nav[active].setChecked(True)

    def set_busy(self, busy):
        self.busy = busy
        if busy:
            self.qapp.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            self.qapp.restoreOverrideCursor()

    # ---------------------------------------------------------------- actions
    def start_closing(self, targets, timeout):
        self.show_page("closing")
        self.pages["closing"].start(targets, timeout)

    def update_settings(self, **changes):
        new = settings_mod.parse_settings({**self.settings, **changes})
        try:
            settings_mod.save_settings(new)
        except OSError as exc:
            Dialog(self, self.t("error"), self.t("save_error", detail=exc))
            return
        old, self.settings = self.settings, new
        core.log_titles = new["log_window_titles"]
        if new["theme"] != old["theme"] or new["backdrop"] != old["backdrop"] \
                or new["transparency"] != old["transparency"]:
            self.apply_theme()
        if new["language"] != old["language"]:
            # Rebuilt once the current event is handled: the settings page is replaced too.
            self.later(0, self.build)
            return
        if new["group_by_app"] != old["group_by_app"] or new["show_icons"] != old["show_icons"]:
            self.list_page.refresh(rebuild=True)
        elif new["close_timeout"] != old["close_timeout"] or new["instant_force"] != old["instant_force"]:
            self.list_page.update_counts()

    def restart_as_admin(self):
        unprotected = core.unprotected_elevation_files()
        if not unprotected:
            self._relaunch_as_admin()
            return
        Dialog(self, self.t("admin_unsafe_title"),
               self.t("admin_unsafe_message", folder=ntpath.dirname(unprotected[0])),
               confirm_text=self.t("admin_restart_anyway"), on_confirm=self._relaunch_as_admin,
               cancel_text=self.t("cancel"))

    def _relaunch_as_admin(self):
        if winapi.relaunch_as_admin():
            self.close()
        else:
            Dialog(self, self.t("error"), self.t("admin_failed"))


def main():
    app = App()
    app.show()
    return app.qapp.exec()
