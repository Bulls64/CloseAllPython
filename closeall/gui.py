"""CustomTkinter user interface in the Windows 11 Fluent style: navigation pane, application
list, closing screen, background processes, log and settings."""
import ast
import logging
import ntpath
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field

import customtkinter as ctk

from . import __version__, appicon, core, crash, settings as settings_mod, shortcut, updater, winapi
from .gui_theme import C, Fonts, Glyphs, apply_palette, mica_image, tile_color, tile_letter
from .i18n import LANGUAGE_NAMES, TEXT, format_memory, format_seconds, translate, translate_n

log = logging.getLogger(settings_mod.LOGGER_NAME)

POLL_MS = 80
SEARCH_DELAY_MS = 120
MAX_DIALOG_ITEMS = 12
MAX_TITLE = 110
ICON_SIZE = 24          # logical px; CustomTkinter scales it with the screen DPI
ICON_SOURCE_SIZE = 48   # rendered size, sharp up to 200 % scaling
LOG_LINES = 400
NOTICE_MS = 4000
# Automatic refreshes after closing applications: at once, then a few more for windows that
# disappear late (UWP frames left by ApplicationFrameHost, applications that close slowly).
AFTER_CLOSE_REFRESH_MS = (0, 400, 1200, 3000)
# After closing Explorer windows (folder windows close asynchronously).
EXPLORER_REFRESH_MS = (700, 2000)
RETRY_REFRESH_MS = 150
UPDATE_STARTUP_DELAY_MS = 2000   # the automatic check waits until the window is up

NAV_WIDTH, NAV_COMPACT_WIDTH = 248, 52
# The content layer is larger than its area by OVERHANG on the right and at the bottom, so that
# only its top-left corner shows rounded, as in WinUI's NavigationView.
OVERHANG = 16
PAD = 36                 # page margins
PAD_RIGHT = PAD + OVERHANG


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, name)


class WindowIcon:
    """Crisp title-bar and taskbar icons for a Tk window, at the DPI of its monitor.

    Tk's `wm iconbitmap` always uses the 16 and 32 px images of the .ico, so they are enlarged,
    hence blurry, on scaled displays. The icons are given again whenever the window is shown or
    moves to a monitor with another scaling.
    """

    def __init__(self, window):
        self.window, self.dpi, self.handles = window, None, ()
        # A toplevel's bindings also receive its child widgets' events: keep only its own.
        window.bind("<Map>", lambda e: e.widget is window and self.apply(force=True), add="+")
        window.bind("<Configure>", lambda e: e.widget is window and self.apply(), add="+")
        window.after(250, lambda: self.apply(force=True))  # after CustomTkinter's own icon setup

    def apply(self, force=False):
        try:
            hwnd = int(self.window.wm_frame(), 16)
            dpi = winapi.window_dpi(hwnd)
            if dpi == self.dpi and not force:
                return
            big_size, small_size = appicon.icon_sizes(dpi)
            path = resource_path("app.ico")
            big = winapi.icon_from_image(appicon.icon_image(path, big_size))
            small = winapi.icon_from_image(appicon.icon_image(path, small_size))
        except Exception:  # an icon is cosmetic: never let it break the window
            log.debug("window icon failed", exc_info=True)
            return
        winapi.set_window_icons(hwnd, big, small)
        for old in self.handles:   # ours from the previous DPI; Tk's own are left alone
            winapi.destroy_icon(old)
        self.handles, self.dpi = (big, small), dpi


def shorten(text, limit=MAX_TITLE):
    return text if len(text) <= limit else text[:limit - 1] + "…"


def scaled(widget, value):
    try:
        return round(value * widget._get_widget_scaling())
    except Exception:
        return value


# ====================================================================== Fluent controls

def label(master, text="", font=None, color="text", **kwargs):
    kwargs.setdefault("anchor", "w")
    kwargs.setdefault("justify", "left")
    return ctk.CTkLabel(master, text=text, font=font, text_color=C[color], **kwargs)


def wrapping(widget, minimum=120):
    """Make a label wrap to the width its parent gives it (long translations, narrow windows)."""
    parent = widget.master

    def wrap(event):
        width = max(minimum, int(event.width / (scaled(widget, 100) / 100 or 1)) - 4)
        if widget.cget("wraplength") != width:
            widget.configure(wraplength=width)

    parent.bind("<Configure>", wrap, add="+")
    return widget


BUTTON_STYLES = {
    "standard": dict(fg="control", hover="control_hover", text="text", border="control_border", border_width=1),
    "accent": dict(fg="accent", hover="accent_hover", text="on_accent", border="accent", border_width=0),
    "subtle": dict(fg=None, hover="subtle_hover", text="text", border=None, border_width=0),
}


def button(master, app, text, command, icon=None, style="standard", height=32, **kwargs):
    """A WinUI Button: standard (neutral), accent (main action) or subtle (no background)."""
    spec = BUTTON_STYLES[style]
    image = app.glyphs.image(icon, 16, spec["text"]) if icon else None
    widget = ctk.CTkButton(master, text=text, command=command, image=image, compound="left", height=height,
                           corner_radius=4, border_width=spec["border_width"],
                           border_color=C[spec["border"]] if spec["border"] else None,
                           fg_color=C[spec["fg"]] if spec["fg"] else "transparent", hover_color=C[spec["hover"]],
                           text_color=C[spec["text"]], text_color_disabled=C["text_disabled"],
                           font=kwargs.pop("font", app.fonts.body), **kwargs)
    widget.fluent_style = style
    return widget


def set_enabled(widget, enabled):
    """Enable or disable a button with WinUI's disabled colours."""
    style = getattr(widget, "fluent_style", "standard")
    if style == "accent":
        widget.configure(state="normal" if enabled else "disabled",
                         fg_color=C["accent"] if enabled else C["accent_disabled"],
                         text_color_disabled=C["on_accent_disabled"])
    else:
        widget.configure(state="normal" if enabled else "disabled")


def icon_button(master, app, glyph, command, size=32, style="subtle", token="text", **kwargs):
    spec = BUTTON_STYLES[style]
    return ctk.CTkButton(master, text="", image=app.glyphs.image(glyph, 16, token), command=command, width=size,
                         height=size, corner_radius=4, border_width=spec["border_width"],
                         border_color=C[spec["border"]] if spec["border"] else None,
                         fg_color=C[spec["fg"]] if spec["fg"] else "transparent", hover_color=C[spec["hover"]],
                         **kwargs)


def glyph_label(master, app, glyph, size=16, token="text", **kwargs):
    kwargs.setdefault("width", size)
    return ctk.CTkLabel(master, text="", image=app.glyphs.image(glyph, size, token), **kwargs)


def checkbox(master, command):
    return ctk.CTkCheckBox(master, text="", width=20, checkbox_width=20, checkbox_height=20, corner_radius=4,
                           border_width=1, fg_color=C["accent"], hover_color=C["accent_hover"],
                           border_color=C["control_strong"], checkmark_color=C["on_accent"], command=command)


class Toggle(ctk.CTkSwitch):
    """WinUI ToggleSwitch: outlined when off, accent with a contrasting knob when on."""

    def __init__(self, master, variable, command):
        self._user_command = command
        super().__init__(master, text="", variable=variable, command=self._changed, width=44, switch_width=40,
                         switch_height=20, border_width=1, button_length=0, progress_color=C["accent"])
        self._style()

    def _changed(self):
        self._style()
        if self._user_command:
            self._user_command()

    def _style(self):
        on = bool(self.get())
        self.configure(fg_color=C["control"], border_color=C["accent"] if on else C["control_strong"],
                       button_color=C["on_accent"] if on else C["control_strong"],
                       button_hover_color=C["on_accent"] if on else C["text2"])

    def set_value(self, on):
        self.select() if on else self.deselect()
        self._style()


def combo(master, app, values, command, width=200):
    menu_text = ("#1a1a1a", "#ffffff")
    return ctk.CTkOptionMenu(master, values=values, command=command, width=width, height=32, corner_radius=4,
                             fg_color=C["control"], button_color=C["control"], button_hover_color=C["control_hover"],
                             text_color=C["text"], font=app.fonts.body, dropdown_font=app.fonts.body,
                             dropdown_fg_color=C["menu"], dropdown_hover_color=C["menu_hover"],
                             dropdown_text_color=menu_text, dynamic_resizing=False)


def progress_bar(master, width=160, height=4):
    return ctk.CTkProgressBar(master, width=width, height=height, corner_radius=2, fg_color=C["track"],
                              progress_color=C["accent"])


def scroll_area(master, color="layer"):
    area = ctk.CTkScrollableFrame(master, fg_color=C[color], corner_radius=0, scrollbar_button_color=C["text3"],
                                  scrollbar_button_hover_color=C["text2"])
    try:   # thin like WinUI's scrollbars (private attribute: cosmetic only)
        area._scrollbar.configure(width=10)
    except Exception:
        pass
    return area


def card(master, color="card", border="card_border", **kwargs):
    return ctk.CTkFrame(master, fg_color=C[color], border_color=C[border], border_width=1, corner_radius=4, **kwargs)


class Divider(tk.Frame):
    """A 1 px line (CustomTkinter frames draw nothing under 2 px), recoloured with the theme."""

    def __init__(self, master, token="divider"):
        super().__init__(master, height=1, bd=0, highlightthickness=0)
        self.colors = C[token]
        ctk.AppearanceModeTracker.add(self._set_mode, self)
        self._set_mode(ctk.get_appearance_mode())

    def _set_mode(self, mode):
        self.configure(bg=self.colors[1 if str(mode).lower() == "dark" else 0])

    def destroy(self):
        try:
            ctk.AppearanceModeTracker.remove(self._set_mode)
        except Exception:
            pass
        super().destroy()


def divider(master):
    return Divider(master)


def section_header(master, app, text, first=False):
    widget = label(master, text, app.fonts.body_strong)
    widget.pack(fill="x", pady=(0 if first else 22, 6))
    return widget


def settings_card(master, app, glyph, title, description=None):
    """A WinUI SettingsCard: icon, title and description on the left, the control on the right.
    Returns the card, the frame for the control and the texts frame."""
    box = card(master)
    box.pack(fill="x", pady=(0, 4))
    row = ctk.CTkFrame(box, fg_color="transparent")
    row.pack(fill="x", padx=(16, 16), pady=14)
    if glyph:
        glyph_label(row, app, glyph, 20).pack(side="left", padx=(2, 18))
    right = ctk.CTkFrame(row, fg_color="transparent")
    right.pack(side="right", padx=(16, 0))
    texts = ctk.CTkFrame(row, fg_color="transparent")
    texts.pack(side="left", fill="x", expand=True)
    label(texts, title, app.fonts.body).pack(fill="x")
    if description:
        wrapping(label(texts, description, app.fonts.caption, "text2")).pack(fill="x")
    box.row = row
    return box, right, texts


def infobar(master, app, text, glyph="info", token="accent"):
    """A WinUI InfoBar (informational): icon and message on a quiet card."""
    box = card(master, color="card_secondary")
    row = ctk.CTkFrame(box, fg_color="transparent")
    row.pack(fill="x", padx=16, pady=10)
    glyph_label(row, app, glyph, 16, token).pack(side="left", padx=(0, 12), anchor="n", pady=2)
    holder = ctk.CTkFrame(row, fg_color="transparent")
    holder.pack(side="left", fill="x", expand=True)
    wrapping(label(holder, text, app.fonts.small)).pack(fill="x")
    return box


def tile(master, app, name, image=None, protected=False):
    """32 px square: the application's icon, or its initial on a coloured background."""
    if image is not None:
        box = ctk.CTkFrame(master, width=32, height=32, corner_radius=6, fg_color="transparent")
        inner = ctk.CTkLabel(box, text="", image=image, width=24, height=24, fg_color="transparent")
    else:
        box = ctk.CTkFrame(master, width=32, height=32, corner_radius=6,
                           fg_color=C["neutral_bg"] if protected else tile_color(name))
        inner = ctk.CTkLabel(box, text=tile_letter(name), font=app.fonts.tile, width=24, height=24,
                             fg_color="transparent", text_color=C["text2"] if protected else ("#ffffff", "#dfdfdf"))
    box.pack_propagate(False)
    inner.place(relx=0.5, rely=0.5, anchor="center")
    box.inner = inner
    return box


def set_tile_icon(box, image):
    """Show an icon that arrived after the tile was drawn with the application's initial."""
    try:
        if image is not None and box.winfo_exists():
            box.configure(fg_color="transparent")
            box.inner.configure(text="", image=image)
    except tk.TclError:
        pass  # the card was rebuilt in the meantime


STATUS_STYLES = {   # status pill: background and text colour tokens
    "neutral": ("neutral_bg", "text2"),
    "success": ("success_bg", "success"),
    "caution": ("caution_bg", "caution"),
    "critical": ("critical_bg", "critical"),
}


def pill(master, app):
    return ctk.CTkLabel(master, text="", font=app.fonts.caption_strong, height=24, corner_radius=12, padx=10)


class Page(ctk.CTkFrame):
    """A page on the content layer: rounded top-left corner and edge, like WinUI pages."""

    def __init__(self, app):
        super().__init__(app.content, fg_color=C["layer"], bg_color=C["bg"], corner_radius=8, border_width=1,
                         border_color=C["layer_border"])
        self.app = app
        # CustomTkinter refuses a size in place(); the layer must overhang its area, so Tk's own
        # placer is used with the overhang in real pixels.
        overhang = scaled(self, OVERHANG)
        tk.Place.place_configure(self, x=0, y=0, relwidth=1, relheight=1, width=overhang, height=overhang)


def page_header(page, app, title, row=0, pady=(28, 16)):
    """Title of a page. Returns the header (actions go on its right) and the block under the
    title (for a subtitle)."""
    header = ctk.CTkFrame(page, fg_color="transparent")
    header.grid(row=row, column=0, sticky="ew", padx=(PAD, PAD_RIGHT), pady=pady)
    titles = ctk.CTkFrame(header, fg_color="transparent")
    titles.pack(side="left", fill="x", expand=True)
    label(titles, title, app.fonts.title).pack(fill="x")
    return header, titles


class Dialog(ctk.CTkToplevel):
    """A WinUI ContentDialog in its own window (confirmation when `confirm_text` is given)."""

    def __init__(self, app, title, message, items=(), confirm_text=None, on_confirm=None, cancel_text=None):
        super().__init__(app, fg_color=C["layer"])
        self.app, self.on_confirm = app, on_confirm
        self._counted = True
        app.dialogs += 1   # automatic list refreshes wait while a dialog is open
        try:
            self.iconbitmap(resource_path("app.ico"))
        except tk.TclError:
            pass
        self.window_icon = WindowIcon(self)
        self.title(title)
        self.resizable(False, False)
        self.transient(app)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(22, 24))
        label(body, title, app.fonts.subtitle, wraplength=460).pack(fill="x")
        label(body, message, app.fonts.body, wraplength=460).pack(fill="x", pady=(12, 0))
        items = list(items)
        if items:
            shown, hidden = core.truncate(items, MAX_DIALOG_ITEMS)
            box = card(body)
            box.pack(fill="x", pady=(16, 0))
            for item in shown:
                label(box, f"•  {shorten(item, 70)}", app.fonts.body).pack(fill="x", padx=14, pady=(8, 0))
            if hidden:
                label(box, app.t("more_items", count=hidden), app.fonts.caption, "text2").pack(
                    fill="x", padx=14, pady=(6, 0))
            box.winfo_children()[-1].pack_configure(pady=(6, 12))
        divider(self).pack(fill="x")
        footer = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        footer.pack(fill="x")
        buttons = ctk.CTkFrame(footer, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=24)
        buttons.grid_columnconfigure((0, 1), weight=1, uniform="buttons")
        if confirm_text:
            button(buttons, app, confirm_text, self._confirm, style="accent", width=150).grid(
                row=0, column=0, sticky="ew", padx=(0, 4))
            button(buttons, app, cancel_text or app.t("cancel"), self.destroy, width=150).grid(
                row=0, column=1, sticky="ew", padx=(4, 0))
        else:
            button(buttons, app, app.t("ok"), self.destroy, style="accent", width=150).grid(
                row=0, column=1, sticky="ew")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._confirm() if confirm_text else self.destroy())
        self.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_reqwidth()) // 2
        y = app.winfo_rooty() + (app.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        # CTkToplevel may open behind its parent on Windows: raise it once it exists.
        self.after(20, self._raise)

    def _raise(self):
        try:
            self.app.apply_backdrop(self)
            self.lift()
            self.focus_force()
            self.grab_set()
        except tk.TclError:
            pass

    def destroy(self):
        if self._counted:
            self._counted = False
            self.app.dialogs -= 1
        super().destroy()

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


class AppCard(ctk.CTkFrame):
    def __init__(self, master, page, entry, image):
        super().__init__(master, fg_color=C["card_secondary" if entry.protected else "card"],
                         border_color=C["card_border"], border_width=1, corner_radius=4)
        app = page.app
        self.page, self.entry, self.windows_frame = page, entry, None
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=(16, 8), pady=12)
        clickable = [row]
        if entry.protected:
            glyph_label(row, app, "lock", 16, "text3", width=20).pack(side="left", padx=(0, 16))
            self.check = None
        else:
            self.check = checkbox(row, self._on_check)
            self.check.pack(side="left", padx=(0, 12))
        icon = tile(row, app, entry.name, image, entry.protected)
        icon.pack(side="left", padx=(0, 16))
        self.tile = icon
        texts = ctk.CTkFrame(row, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True)
        name = label(texts, entry.name, app.fonts.body_strong, "text2" if entry.protected else "text")
        name.pack(fill="x")
        meta = label(texts, entry.meta, app.fonts.caption, "text3" if entry.protected else "text2")
        meta.pack(fill="x")
        clickable += [icon, icon.inner, texts, name, meta]
        self.chevron = None
        if entry.titles:
            self.chevron = icon_button(row, app, "chevron_down", self.toggle_expand)
            self.chevron.pack(side="right")
        if not entry.protected:
            for widget in clickable:
                widget.bind("<Button-1>", lambda _e: self.check.toggle())

    def _on_check(self):
        self.page.set_selected(self.entry.proc_key, bool(self.check.get()))

    def show_selected(self, selected):
        if self.check is None:
            return
        if selected:
            self.check.select()
        else:
            self.check.deselect()
        self.configure(fg_color=C["card_selected"] if selected else C["card"])

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
        app = self.page.app
        self.chevron.configure(image=app.glyphs.image("chevron_up" if expanded else "chevron_down", 16))
        if expanded and self.windows_frame is None:
            # Built on first use: most cards are never expanded.
            self.windows_frame = ctk.CTkFrame(self, fg_color="transparent")
            divider(self.windows_frame).pack(fill="x", padx=1)
            for title in self.entry.titles:
                row = ctk.CTkFrame(self.windows_frame, fg_color="transparent")
                row.pack(fill="x", padx=(96, 16), pady=(8, 0))
                glyph_label(row, app, "window", 14, "text2").pack(side="left", padx=(0, 12))
                label(row, shorten(title), app.fonts.small, "text2").pack(side="left", fill="x", expand=True)
            row.pack_configure(pady=(8, 12))
        if self.windows_frame is not None:
            if expanded:
                self.windows_frame.pack(fill="x", padx=1, pady=(0, 1))
            else:
                self.windows_frame.pack_forget()


class SelectorBar(ctk.CTkFrame):
    """WinUI SelectorBar: text items, the selected one in bold with an accent mark under it."""

    def __init__(self, master, app, names, command):
        super().__init__(master, fg_color="transparent")
        self.app, self.command, self.items, self.current = app, command, {}, names[0]
        for name in names:
            item = ctk.CTkButton(self, text="", command=lambda n=name: self.select(n, notify=True), height=40,
                                 width=60, corner_radius=4, fg_color="transparent", hover_color=C["subtle_hover"],
                                 text_color=C["text2"], font=app.fonts.body)
            item.pack(side="left", padx=(0, 4))
            self.items[name] = item
        self.mark = ctk.CTkFrame(self, width=16, height=3, corner_radius=2, fg_color=C["accent"])
        self.select(names[0])

    def set_text(self, name, text):
        self.items[name].configure(text=text)

    def select(self, name, notify=False):
        self.current = name
        for key, item in self.items.items():
            item.configure(text_color=C["text"] if key == name else C["text2"],
                           font=self.app.fonts.body_strong if key == name else self.app.fonts.body)
        self.mark.place(in_=self.items[name], relx=0.5, rely=1.0, anchor="s", y=-3)
        self.mark.lift()
        if notify:
            self.command(name)


class ListPage(Page):
    def __init__(self, app, state=None):
        super().__init__(app)
        t = app.t
        state = state or {}
        self.windows, self.entries, self.cards = [], [], {}
        self.selected = set(state.get("selected", ()))
        self.expanded = set(state.get("expanded", ()))
        self.filter = "all"
        self.search_job = None
        self.app_count = self.selectable_count = 0
        self.notice = None          # status-bar message shown for NOTICE_MS
        self.notice_job = None
        self.refresh_jobs, self.retry_job = [], None
        self.restarting_explorer = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header, titles = page_header(self, app, t("apps_title"))
        self.summary = label(titles, "", app.fonts.body, "text2")
        self.summary.pack(fill="x", pady=(2, 0))
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.pack(side="right", anchor="n", pady=(4, 0))
        icon_button(actions, app, "refresh", self.refresh, style="standard").pack(side="right")
        if not app.is_admin:
            button(actions, app, t("admin_button"), app.restart_as_admin, icon="shield").pack(side="right", padx=(0, 8))

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=(PAD, PAD_RIGHT), pady=(0, 12))
        self.filter_bar = SelectorBar(toolbar, app, ["all", "selected"], self._on_filter)
        self.filter_bar.pack(side="right", padx=(24, 0))
        search = ctk.CTkFrame(toolbar, fg_color=C["input"], border_color=C["input_border"], border_width=1,
                              corner_radius=4, height=32)
        search.pack(side="left", fill="x", expand=True)
        glyph_label(search, app, "search", 16, "text2").pack(side="right", padx=(4, 10))
        self.search = ctk.CTkEntry(search, placeholder_text=t("search_placeholder"), font=app.fonts.body, height=28,
                                   border_width=0, corner_radius=0, fg_color=C["input"], text_color=C["text"],
                                   placeholder_text_color=C["text2"])
        self.search.pack(side="left", fill="x", expand=True, padx=(8, 0), pady=2)
        if state.get("query"):
            self.search.insert(0, state["query"])
        self.search.bind("<KeyRelease>", self._schedule_filter)
        self.search.bind("<Escape>", self._clear_search)

        self.list = scroll_area(self)
        self.list.grid(row=2, column=0, sticky="nsew", padx=(PAD - 8, PAD_RIGHT - 16))
        self.empty = label(self.list, "", app.fonts.body, "text2", anchor="center", justify="center")
        self.protected_header = ctk.CTkFrame(self.list, fg_color="transparent")
        glyph_label(self.protected_header, app, "lock", 14, "text2").pack(side="left", padx=(2, 8))
        label(self.protected_header, t("protected_header"), app.fonts.body_strong, "text2").pack(side="left")

        divider(self).grid(row=3, column=0, sticky="ew", padx=(1, OVERHANG))
        bar = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        bar.grid(row=4, column=0, sticky="ew", padx=(1, OVERHANG), pady=(0, OVERHANG))
        self.close_button = button(bar, app, "", self.close_selected, style="accent", font=app.fonts.body_strong)
        self.close_button.pack(side="right", padx=(0, PAD), pady=16)
        self.clear_button = button(bar, app, t("clear_selection"), self.clear_selection)
        self.explorer_menu = tk.Menu(self, tearoff=0)
        self.explorer_menu.add_command(label=t("close_explorer_short"), command=self.close_explorer)
        self.explorer_menu.add_command(label=t("restart_explorer_short"), command=self.restart_explorer)
        self.explorer_button = button(bar, app, f"{t('explorer_group')}  ⌄", self._show_explorer_menu, icon="folder")
        self.explorer_button.pack(side="right", padx=(0, 8), pady=16)
        texts = ctk.CTkFrame(bar, fg_color="transparent")
        self.selection_line = label(texts, "", app.fonts.body_strong)
        self.selection_line.pack(fill="x")
        hint = ctk.CTkFrame(texts, fg_color="transparent")
        hint.pack(fill="x")
        self.hint_icon = glyph_label(hint, app, "warning", 12, "caution")
        self.hint_icon.pack(side="left", padx=(0, 6))
        self.hint = label(hint, "", app.fonts.caption, "text2")
        self.hint.pack(side="left", fill="x", expand=True)
        # Packed after the buttons: they keep their full width and the texts take what is left.
        texts.pack(side="left", fill="x", expand=True, padx=(PAD - 1, 16), pady=14)
        texts.bind("<Configure>", self._wrap_bar_texts)

    def _wrap_bar_texts(self, event):
        # Narrow window or long translation: wrap the texts instead of cutting them off.
        width = max(80, int(event.width / self._get_widget_scaling()))
        for widget in (self.selection_line, self.hint):
            if widget.cget("wraplength") != width:
                widget.configure(wraplength=width - (20 if widget is self.hint else 0))

    def _show_explorer_menu(self):
        widget = self.explorer_button
        self.explorer_menu.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height() + 2)

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
            card_widget = old.pop(entry.card_key, None)
            if card_widget is not None and (rebuild or card_widget.entry != entry):
                card_widget.destroy()
                card_widget = None
            if card_widget is None:
                image = None
                if self.app.settings["show_icons"]:
                    image = self.app.icon_for(entry.exe_path, lambda img, key=entry.card_key: self._icon_ready(key, img))
                card_widget = AppCard(self.list, self, entry, image)
                card_widget.show_expanded(entry.card_key in self.expanded)
            card_widget.show_selected(entry.proc_key in self.selected)
            self.cards[entry.card_key] = card_widget
        for card_widget in old.values():
            card_widget.destroy()

    def _icon_ready(self, card_key, image):
        card_widget = self.cards.get(card_key)
        if card_widget is not None:
            set_tile_icon(card_widget.tile, image)

    # ---------------------------------------------------------------- automatic refresh
    def schedule_refreshes(self, delays_ms):
        """Plan automatic refreshes (replaces those already planned)."""
        for job in self.refresh_jobs:
            self.after_cancel(job)
        self.refresh_jobs = [self.after(delay, self._auto_refresh) for delay in delays_ms]

    def _auto_refresh(self):
        # Never while a closing runs (the list would be read mid-way), nor under an open dialog
        # (a confirmation must not disagree with the list behind it): retried shortly after.
        if self.app.busy or self.app.dialogs:
            if self.retry_job is None:
                self.retry_job = self.after(RETRY_REFRESH_MS, self._retry_refresh)
            return
        self.refresh()

    def _retry_refresh(self):
        self.retry_job = None
        self._auto_refresh()

    # ---------------------------------------------------------------- filtering
    def _schedule_filter(self, _event=None):
        if self.search_job is not None:
            self.after_cancel(self.search_job)
        self.search_job = self.after(SEARCH_DELAY_MS, self.apply_filter)

    def _clear_search(self, _event=None):
        self.search.delete(0, "end")
        self.apply_filter()

    def _on_filter(self, name):
        self.filter = "selected" if name == "selected" else "all"
        self.apply_filter()

    def apply_filter(self):
        self.search_job = None
        t = self.app.t
        query = self.search.get().strip().casefold()
        for widget in self.list.winfo_children():
            widget.pack_forget()
        visible = [e for e in self.entries if not query or query in e.search_text]
        normal = [e for e in visible if not e.protected]
        protected = [e for e in visible if e.protected]
        if self.filter == "selected":
            normal = [e for e in normal if e.proc_key in self.selected]
            protected = []
        for entry in normal:
            self.cards[entry.card_key].pack(fill="x", padx=(8, 12), pady=(0, 4))
        if protected:
            self.protected_header.pack(fill="x", padx=10, pady=(18, 8))
            for entry in protected:
                self.cards[entry.card_key].pack(fill="x", padx=(8, 12), pady=(0, 4))
        if not normal and not protected:
            if query:
                text = t("no_match", query=self.search.get().strip())
            elif self.filter == "selected":
                text = t("no_selected")
            else:
                text = t("no_windows")
            self.empty.configure(text=text)
            self.empty.pack(fill="x", pady=48)
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
        self.summary.configure(text=f"{app.tn('n_windows', len(self.windows))} · {app.tn('n_apps', self.app_count)}")
        self.filter_bar.set_text("all", t("filter_all", count=self.selectable_count))
        self.filter_bar.set_text("selected", t("filter_selected", count=len(self.selected)))
        self.filter_bar.select("selected" if self.filter == "selected" else "all")
        count = len(self.selected)
        windows = sum(1 for w in self.windows if w.key in self.selected)
        if count:
            self.selection_line.configure(text=f"{app.tn('n_selected', count)} · {app.tn('n_windows', windows)}")
            self.close_button.configure(text=app.tn("close_button", count))
            set_enabled(self.close_button, True)
            self.clear_button.pack(side="right", padx=(0, 8), pady=16, after=self.close_button)
        else:
            self.selection_line.configure(text=t("selection_none"))
            self.close_button.configure(text=t("close_button_none"))
            set_enabled(self.close_button, False)
            self.clear_button.pack_forget()
        if self.notice:
            self.selection_line.configure(text=self.notice)
        instant = app.settings["instant_force"]
        self.hint.configure(text=t("close_hint_instant") if instant
                            else t("close_hint", seconds=app.settings["close_timeout"]))
        if instant:
            self.hint_icon.pack(side="left", padx=(0, 6), before=self.hint)
        else:
            self.hint_icon.pack_forget()

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
        self.notice = app.tn("explorer_closed", count) if count else app.t("explorer_none")
        if self.notice_job is not None:
            self.after_cancel(self.notice_job)
        self.notice_job = self.after(NOTICE_MS, self._end_notice)
        self.update_counts()
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
        set_enabled(self.explorer_button, False)
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
            set_enabled(self.explorer_button, True)
        except tk.TclError:
            return   # page rebuilt meanwhile (language change)
        if error is None:
            self._show_notice(t("explorer_restarted"))
            self.schedule_refreshes(EXPLORER_REFRESH_MS)
        else:
            self._show_notice(None)
            Dialog(app, t("error"), t("explorer_restart_failed", error=t(error.key, detail=error.detail or "")))

    def _show_notice(self, text, keep=False):
        if self.notice_job is not None:
            self.after_cancel(self.notice_job)
            self.notice_job = None
        self.notice = text
        if text and not keep:
            self.notice_job = self.after(NOTICE_MS, self._end_notice)
        self.update_counts()

    def _end_notice(self):
        self.notice_job, self.notice = None, None
        self.update_counts()

    def focus_search(self):
        self.search.focus_set()

    def state(self):
        return {"selected": set(self.selected), "expanded": set(self.expanded), "query": self.search.get()}


# ====================================================================== closing screen

class ClosingRow(ctk.CTkFrame):
    def __init__(self, master, page, target):
        super().__init__(master, fg_color=C["card"], border_color=C["card_border"], border_width=1, corner_radius=4)
        app = page.app
        self.page, self.target = page, target
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=12)
        name = app.display_name(target.exe_path) or app.t("process_n", pid=target.pid)
        image = None
        if app.settings["show_icons"]:
            image = app.icon_for(target.exe_path, lambda img: set_tile_icon(self.tile, img))
        self.tile = tile(top, app, name, image)
        self.tile.pack(side="left", padx=(0, 16))
        texts = ctk.CTkFrame(top, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True)
        label(texts, name, app.fonts.body_strong).pack(fill="x")
        meta = " · ".join([shorten(", ".join(target.titles), 80), app.t("pid", pid=target.pid)])
        label(texts, meta, app.fonts.caption, "text2").pack(fill="x")
        self.pill = pill(top, app)
        self.pill.pack(side="right")
        self.body = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.explain_icon = glyph_label(self.body, app, "warning", 14, "caution")
        self.explain_icon.pack(side="left", padx=(64, 8), pady=(0, 14), anchor="n")
        holder = ctk.CTkFrame(self.body, fg_color="transparent")
        holder.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=(0, 14))
        self.explain = wrapping(label(holder, "", app.fonts.small, "text"))
        self.explain.pack(fill="x")
        self.leave = button(self.body, app, app.t("leave_open"), self._leave)
        self.show = button(self.body, app, app.t("show_window"), self._show, icon="window")
        self.set_waiting()

    def _style(self, text, kind):
        background, foreground = STATUS_STYLES[kind]
        self.pill.configure(text=text, fg_color=C[background], text_color=C[foreground])

    def set_waiting(self):
        self._style(self.page.app.t("status_waiting"), "neutral")

    def set_forcing(self):
        self._style(self.page.app.t("status_forcing"), "neutral")
        self.body.pack_forget()

    def set_result(self, result):
        app = self.page.app
        self.body.pack_forget()
        if result.status == core.CLOSED:
            text = (app.t("status_closed", seconds=format_seconds(app.language, result.elapsed))
                    if result.elapsed >= 0.1 else app.t("log_closed"))
            self._style(text, "success")
        elif result.status == core.FORCED:
            self._style(app.t("status_forced"), "caution")
        elif result.status == core.STILL_RUNNING:
            self._style(app.t("status_still"), "caution")
            self.explain_icon.configure(image=app.glyphs.image("warning", 14, "caution"))
            self.explain.configure(text=app.t("still_explain", seconds=self.page.timeout))
            # Packed before the explanation, which takes the width that is left.
            self.leave.pack(side="right", padx=(0, 16), pady=(0, 14), anchor="n", before=self.explain_icon)
            self.show.pack(side="right", padx=(0, 8), pady=(0, 14), anchor="n", before=self.explain_icon)
            self.body.pack(fill="x", padx=2, pady=(0, 2))
        else:  # FAILED
            self._style(app.t("status_failed"), "critical")
            text = app.t(result.error_key, detail=result.detail) if result.error_key else ""
            if result.error_key == "access_denied" and not app.is_admin:
                text += "\n" + app.t("admin_hint")
            self.explain_icon.configure(image=app.glyphs.image("warning", 14, "critical"))
            self.explain.configure(text=text[:1].upper() + text[1:])
            self.leave.pack_forget()
            self.show.pack_forget()
            self.body.pack(fill="x", padx=2, pady=(0, 2))

    def set_left_open(self):
        self._style(self.page.app.t("status_left"), "neutral")
        self.body.pack_forget()

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
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=(PAD - 10, PAD_RIGHT), pady=(20, 0))
        self.back = button(head, app, t("apps_title"), self.finish, icon="back", style="subtle", height=30,
                           font=app.fonts.small)
        self.back.pack(anchor="w")
        line = ctk.CTkFrame(head, fg_color="transparent")
        line.pack(fill="x", pady=(8, 0), padx=(10, 0))
        texts = ctk.CTkFrame(line, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True)
        self.title = label(texts, t("closing_title"), app.fonts.title)
        self.title.pack(fill="x")
        self.subtitle = label(texts, "", app.fonts.body, "text2")
        self.subtitle.pack(fill="x", pady=(2, 0))
        self.elapsed = label(line, "", app.fonts.caption, "text2")
        self.elapsed.pack(side="right", anchor="s")
        self.progress = progress_bar(self, height=4)
        self.progress.grid(row=1, column=0, sticky="ew", padx=(PAD, PAD_RIGHT), pady=(16, 16))

        self.list = scroll_area(self)
        self.list.grid(row=2, column=0, sticky="nsew", padx=(PAD - 8, PAD_RIGHT - 16))

        divider(self).grid(row=3, column=0, sticky="ew", padx=(1, OVERHANG))
        bar = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        bar.grid(row=4, column=0, sticky="ew", padx=(1, OVERHANG), pady=(0, OVERHANG))
        texts = self.bar_texts = ctk.CTkFrame(bar, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True, padx=(PAD - 1, 16), pady=14)
        self.summary = wrapping(label(texts, "", app.fonts.body_strong), minimum=80)
        self.summary.pack(fill="x")
        wrapping(label(texts, t("closing_hint"), app.fonts.caption, "text2"), minimum=80).pack(fill="x")
        self.force_button = button(bar, app, "", self.force, style="accent", icon="power", font=app.fonts.body_strong)
        self.done_button = button(bar, app, t("done"), self.finish)

    def start(self, targets, timeout):
        self.targets, self.timeout = targets, timeout
        self.results, self.left_open = {}, set()
        for row in self.rows.values():
            row.destroy()
        self.rows = {}
        for target in targets:
            row = ClosingRow(self.list, self, target)
            row.pack(fill="x", padx=(8, 12), pady=(0, 4))
            self.rows[target.key] = row
        self.title.configure(text=self.app.t("closing_title"))
        self.subtitle.configure(text=self.app.tn("closing_subtitle", len(targets)))
        self.progress.set(0)
        self.started = time.monotonic()
        if timeout:
            self._run(lambda report: core.close_processes(targets, timeout, on_result=report))
        else:
            for row in self.rows.values():
                row.set_forcing()
            self.subtitle.configure(text=self.app.tn("forcing_subtitle", len(targets)))
            self._run(lambda report: core.force_processes(targets, on_result=report))
        self._tick()

    def _run(self, work):
        """Run `work(report)` in a thread; each Result is handed back to the Tk thread."""
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
        if not self.running or not self.winfo_exists():
            return
        elapsed = time.monotonic() - self.started
        if self.timeout:
            self.progress.set(min(1.0, elapsed / self.timeout))
            self.elapsed.configure(text=self.app.t("elapsed", elapsed=min(self.timeout, int(elapsed)), seconds=self.timeout))
        self.after(200, self._tick)

    def _on_result(self, result):
        self.results[result.target.key] = result
        row = self.rows.get(result.target.key)
        if row is not None:
            row.set_result(result)
        self._update()

    def _on_finished(self):
        self.running = False
        self.app.set_busy(False)
        # Applications were just closed: bring the list of open windows up to date by itself.
        self.app.list_page.schedule_refreshes(AFTER_CLOSE_REFRESH_MS)
        self.progress.set(1)
        if self.timeout:
            self.elapsed.configure(text=self.app.t("elapsed", elapsed=self.timeout, seconds=self.timeout))
        self.title.configure(text=self.app.t("closing_done_title"))
        if not self.timeout:
            self.subtitle.configure(text=self.app.tn("forced_subtitle", len(self.targets)))
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
        self.summary.configure(text=" · ".join(parts))
        still = self.still_running()
        self.force_button.pack_forget()
        self.done_button.pack_forget()
        if still and not self.running:
            text = (app.t("force_one_named", name=app.display_name(still[0].exe_path) or app.t("process_n", pid=still[0].pid))
                    if len(still) == 1 else app.t("force_count", count=len(still)))
            self.force_button.configure(text=text)
            # Before the texts in the packing order: the buttons keep their full width.
            self.force_button.pack(side="right", padx=(0, PAD), pady=16, before=self.bar_texts)
            self.done_button.pack(side="right", padx=(0, 8), pady=16, before=self.bar_texts)
        else:
            self.done_button.pack(side="right", padx=(0, PAD), pady=16, before=self.bar_texts)
        set_enabled(self.done_button, not self.running)
        set_enabled(self.back, not self.running)

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
        self.app.show("apps")
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
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header, texts = page_header(self, app, t("log_title"))
        label(texts, str(settings_mod.log_path()), app.fonts.body, "text2").pack(fill="x", pady=(2, 0))
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.pack(side="right", anchor="n", pady=(4, 0))
        button(actions, app, t("log_open_file"), self.open_file, icon="open").pack(side="right")
        button(actions, app, t("refresh"), self.load, icon="refresh").pack(side="right", padx=(0, 8))
        self.text = ctk.CTkTextbox(self, font=app.fonts.mono, fg_color=C["card"], border_color=C["card_border"],
                                   border_width=1, corner_radius=4, text_color=C["text"], wrap="none",
                                   scrollbar_button_color=C["text3"], scrollbar_button_hover_color=C["text2"])
        self.text.grid(row=1, column=0, sticky="nsew", padx=(PAD, PAD_RIGHT), pady=(0, 28 + OVERHANG))

    def load(self):
        try:
            with open(settings_mod.log_path(), encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()[-LOG_LINES:]
        except OSError:
            lines = []
        text = "\n".join(format_log_line(self.app, line) for line in lines if line.strip()) or self.app.t("log_empty")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.configure(state="disabled")
        self.text.see("end")

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
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header, titles = page_header(self, app, t("background_title"))
        self.summary = label(titles, "", app.fonts.body, "text2")
        self.summary.pack(fill="x", pady=(2, 0))
        button(header, app, t("refresh"), self.load, icon="refresh").pack(side="right", anchor="n", pady=(4, 0))

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=1, column=0, sticky="ew", padx=(PAD, PAD_RIGHT), pady=(0, 12))
        self.include_system = ctk.BooleanVar(value=app.settings["background_include_system"])
        _box, right, _texts = settings_card(options, app, "monitor", t("background_include_system"),
                                            t("background_include_system_hint"))
        Toggle(right, self.include_system, self._on_include_system).pack(side="right")
        self.hint = infobar(options, app, t("background_hint"))
        self.hint.pack(fill="x", pady=(8, 0))

        self.list = scroll_area(self)
        self.list.grid(row=2, column=0, sticky="nsew", padx=(PAD - 8, PAD_RIGHT - 16), pady=(0, 16 + OVERHANG))
        self.report = None
        self.generation = 0   # the latest read; older ones arriving late are dropped

    def _on_include_system(self):
        self.app.update_settings(background_include_system=bool(self.include_system.get()))
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
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return   # page rebuilt meanwhile (language change)
        app, t = self.app, self.app.t
        for child in self.list.winfo_children():
            child.destroy()
        if isinstance(result, Exception):
            self.report = None
            self.summary.configure(text=t("background_error", error=result))
            return
        self.report = report = result
        if not report.top:
            self.summary.configure(text=t("background_empty"))
            return
        total = format_memory(app.language, report.total)
        self.summary.configure(text=f"{app.tn('background_top', len(report.top))} · "
                                    f"{app.tn('background_count', report.count, total=total)}")
        largest = max(report.top[0].memory, 1)
        app.preload_icons(p.exe_path for p in report.top)
        for rank, process in enumerate(report.top, 1):
            self._row(rank, process, largest)

    def _row(self, rank, process, largest):
        app = self.app
        box = card(self.list)
        box.pack(fill="x", padx=(8, 12), pady=(0, 4))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=(12, 16), pady=12)
        label(row, str(rank), app.fonts.caption, "text2", width=22, anchor="e").pack(side="left", padx=(0, 14))
        name = app.display_name(process.exe_path) if process.exe_path else process.app_name
        tile_box = tile(row, app, name, None, process.protected)
        tile_box.pack(side="left", padx=(0, 16))
        if process.exe_path and app.settings["show_icons"]:
            set_tile_icon(tile_box, app.icon_for(process.exe_path,
                                                 on_ready=lambda image, b=tile_box: set_tile_icon(b, image)))
        memory = ctk.CTkFrame(row, fg_color="transparent")
        memory.pack(side="right", padx=(16, 0))
        label(memory, format_memory(app.language, process.memory), app.fonts.body_strong, anchor="e").pack(fill="x")
        bar = progress_bar(memory, width=160, height=4)
        bar.set(process.memory / largest)
        bar.pack(pady=(6, 2))
        texts = ctk.CTkFrame(row, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True)
        line = ctk.CTkFrame(texts, fg_color="transparent")
        line.pack(fill="x")
        label(line, name, app.fonts.body_strong, "text2" if process.protected else "text").pack(side="left")
        if process.protected:
            ctk.CTkLabel(line, text=app.t("protected_badge"), font=app.fonts.caption, height=20, corner_radius=4,
                         fg_color=C["neutral_bg"], text_color=C["text2"], padx=6).pack(side="left", padx=(8, 0))
        label(texts, f"{process.name} · {app.t('pid', pid=process.pid)}", app.fonts.caption, "text2").pack(fill="x")


# ====================================================================== settings

class SettingsPage(Page):
    def __init__(self, app):
        super().__init__(app)
        t, s = app.t, app.settings
        self.save_job = None
        scroll = self.scroll = scroll_area(self)
        scroll.pack(fill="both", expand=True, padx=(PAD - 12, OVERHANG + 4), pady=(0, OVERHANG))
        content = ctk.CTkFrame(scroll, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=(12, 20), pady=(28, 28))
        label(content, t("settings_title"), app.fonts.title).pack(fill="x")
        wrapping(label(content, t("settings_subtitle", path=settings_mod.data_dir()), app.fonts.body, "text2")).pack(
            fill="x", pady=(2, 8))

        # ---- display
        section_header(content, app, t("section_display"))
        self.language_values = list(LANGUAGE_NAMES.items())
        _box, right, _ = settings_card(content, app, "globe", t("language"), t("language_hint"))
        language = combo(right, app, [name for _, name in self.language_values], self._on_language)
        language.set(LANGUAGE_NAMES[s["language"]])
        language.pack()
        self.theme_values = [(code, t(f"theme_{code}")) for code in settings_mod.THEMES]
        _box, right, _ = settings_card(content, app, "color", t("theme"), t("theme_hint"))
        theme = combo(right, app, [name for _, name in self.theme_values], self._on_theme)
        theme.set(dict(self.theme_values)[s["theme"]])
        theme.pack()
        supported = app.mica_supported
        _box, right, _ = settings_card(content, app, "transparency", t("mica"),
                                       t("mica_hint") if supported else t("mica_unavailable"))
        self._toggle(right, "mica", enabled=supported)

        # ---- closing
        section_header(content, app, t("section_closing"))
        self._switch_card(content, "check", "confirm_before_terminate", t("confirm_before_terminate"), t("confirm_hint"))
        self._switch_card(content, "lightning", "instant_force", t("instant_force"), t("instant_force_hint"))
        _box, right, _ = settings_card(content, app, "timer", t("close_timeout"), t("timeout_hint"))
        self.timeout_value = label(right, t("seconds_value", seconds=s["close_timeout"]), app.fonts.body, width=44,
                                   anchor="e")
        self.timeout_value.pack(side="right", padx=(12, 0))
        slider = ctk.CTkSlider(right, from_=settings_mod.TIMEOUT_MIN, to=settings_mod.TIMEOUT_MAX, width=200, height=20,
                               number_of_steps=settings_mod.TIMEOUT_MAX - settings_mod.TIMEOUT_MIN,
                               command=self._on_timeout, progress_color=C["accent"], button_color=C["accent"],
                               button_hover_color=C["accent_hover"], fg_color=C["control_strong"])
        slider.set(s["close_timeout"])
        slider.pack(side="right")

        # ---- window list
        section_header(content, app, t("section_list"))
        self._switch_card(content, "list", "group_by_app", t("group_by_app"), t("group_hint"))
        self._switch_card(content, "image", "show_icons", t("show_icons"), t("icons_hint"))

        # ---- shortcut
        section_header(content, app, t("section_shortcut"))
        box, right, texts = settings_card(content, app, "link", t("shortcut_card"), t("shortcut_hint"))
        self.pin_button = button(right, app, t("shortcut_pin"), self._pin_shortcut, icon="pin")
        self.pin_button.pack(side="right")
        button(right, app, t("shortcut_create"), self._create_shortcut).pack(side="right", padx=(0, 8))
        self.shortcut_status = wrapping(label(texts, "", app.fonts.caption, "text2"))
        self.shortcut_status.pack(fill="x", pady=(4, 0))
        # Named in the language of its creation: look for every language's name, current first.
        self.shortcut_file = shortcut.find_any([t("shortcut_name")] + [
            texts_["shortcut_name"] for code, texts_ in TEXT.items() if code != app.language])
        self._show_shortcut_status()

        # ---- about
        section_header(content, app, t("section_about"))
        about = card(content)
        about.pack(fill="x", pady=(0, 4))
        head = ctk.CTkFrame(about, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=14)
        logo = app.app_logo(32)
        ctk.CTkLabel(head, text="", image=logo, width=32).pack(side="left", padx=(0, 14))
        project = ctk.CTkLabel(head, text=updater.PROJECT_PAGE.removeprefix("https://"), font=app.fonts.body,
                               text_color=C["link"], cursor="hand2", anchor="e")
        project.pack(side="right")
        project.bind("<Button-1>", lambda _e: self._open_project())
        names = ctk.CTkFrame(head, fg_color="transparent")
        names.pack(side="left", fill="x", expand=True)
        label(names, "CloseAllPython", app.fonts.body_strong).pack(fill="x")
        label(names, t("about_line", version=__version__), app.fonts.caption, "text2").pack(fill="x")

        rights = t("rights_admin") if app.is_admin else t("rights_user")
        row = self._about_row(about, t("rights_line", rights=rights))
        if not app.is_admin:
            button(row, app, t("admin_restart"), app.restart_as_admin, icon="shield").pack(side="right")
        row = self._about_row(about, t("log_line", name=settings_mod.log_path().name))
        button(row, app, t("open_log"), lambda: app.show("log")).pack(side="right")
        row = self._about_row(about, t("log_window_titles"), t("log_window_titles_hint"))
        self._toggle(row, "log_window_titles")
        row = self._about_row(about, t("auto_update"), t("auto_update_hint"))
        self._toggle(row, "auto_update")
        self.check_button = button(row, app, t("check_updates"), app.updates.check, icon="sync")
        self.check_button.pack(side="right", padx=(0, 16))
        self.update_status = wrapping(label(row.texts, "", app.fonts.caption, "text2"))
        self.update_status.pack(fill="x")
        app.updates.on_status = self._show_update_status
        self._show_update_status()

    def _about_row(self, about, title, description=None):
        divider(about).pack(fill="x", padx=1)
        row = ctk.CTkFrame(about, fg_color="transparent")
        row.pack(fill="x", padx=(62, 16), pady=10)
        texts = ctk.CTkFrame(row, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True)
        label(texts, title, self.app.fonts.body).pack(fill="x")
        if description:
            wrapping(label(texts, description, self.app.fonts.caption, "text2")).pack(fill="x")
        row.texts = texts
        return row

    def _toggle(self, master, key, enabled=True):
        variable = ctk.BooleanVar(value=self.app.settings[key] and enabled)
        toggle = Toggle(master, variable, lambda: self.app.update_settings(**{key: bool(variable.get())}))
        if not enabled:
            toggle.configure(state="disabled")
        toggle.pack(side="right")
        return toggle

    def _switch_card(self, master, glyph, key, title, hint):
        _box, right, _texts = settings_card(master, self.app, glyph, title, hint)
        return self._toggle(right, key)

    def _open_project(self):
        import webbrowser

        webbrowser.open(updater.PROJECT_PAGE)   # a fixed constant, never text from the network

    def _show_shortcut_status(self):
        file = self.shortcut_file
        self.shortcut_status.configure(text=self.app.t("shortcut_ready", path=file) if file else "")
        if file:
            self.shortcut_status.pack(fill="x", pady=(4, 0))
        else:
            self.shortcut_status.pack_forget()
        set_enabled(self.pin_button, bool(file))

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
            self.update_status.configure(text=text)
            if text:
                self.update_status.pack(fill="x")
            else:
                self.update_status.pack_forget()
            set_enabled(self.check_button, not (updates.running or updates.installed))
        except tk.TclError:
            pass   # page destroyed (language change): the new page registers itself

    def _on_language(self, value):
        code = next(code for code, name in self.language_values if name == value)
        self.app.update_settings(language=code)

    def _on_theme(self, value):
        code = next(code for code, name in self.theme_values if name == value)
        self.app.update_settings(theme=code)

    def _on_timeout(self, value):
        seconds = int(round(value))
        self.timeout_value.configure(text=self.app.t("seconds_value", seconds=seconds))
        if self.save_job is not None:
            self.after_cancel(self.save_job)
        self.save_job = self.after(300, lambda: self.app.update_settings(close_timeout=seconds))


# ====================================================================== updates

class Updates:
    """Checks GitHub for a newer release and installs it, off the Tk thread.

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
        self.app.destroy()


# ====================================================================== window

class NavItem(ctk.CTkFrame):
    """A NavigationView item: icon and label; the selected one gets a fill and an accent mark."""

    def __init__(self, master, app, name, glyph, text):
        super().__init__(master, fg_color="transparent", corner_radius=4, height=36)
        self.app, self.name, self.active = app, name, False
        self.pack_propagate(False)
        self.mark = ctk.CTkFrame(self, width=3, height=16, corner_radius=2, fg_color=C["accent"])
        self.icon = glyph_label(self, app, glyph, 16, width=20)
        self.icon.pack(side="left", padx=(14, 14))
        self.text = label(self, text, app.fonts.body)
        self.text.pack(side="left", fill="x", expand=True)
        for widget in (self, self.icon, self.text):
            widget.bind("<Button-1>", lambda _e: app.show(name))
            widget.bind("<Enter>", lambda _e: self._hover(True))
            widget.bind("<Leave>", lambda _e: self._hover(False))

    def _hover(self, inside):
        if not self.active:
            self.configure(fg_color=C["nav_hover"] if inside else "transparent")

    def set_active(self, active):
        self.active = active
        self.configure(fg_color=C["nav_selected"] if active else "transparent")
        if active:
            self.mark.place(x=0, rely=0.5, anchor="w")
        else:
            self.mark.place_forget()

    def set_compact(self, compact):
        if compact:
            self.text.pack_forget()
        else:
            self.text.pack(side="left", fill="x", expand=True)


class App(ctk.CTk):
    def __init__(self):
        self.settings = settings_mod.load_settings()
        try:
            self.mica_supported = bool(winapi.backdrop_supported())
        except Exception:
            self.mica_supported = False
        self.mica = self.settings["mica"] and self.mica_supported
        apply_palette(self.mica)
        super().__init__(fg_color=C["bg"])
        core.log_titles = self.settings["log_window_titles"]
        ctk.set_appearance_mode(self.settings["theme"])
        self.is_admin = winapi.is_admin()
        self.own_pids = core.own_pids(include_ancestors=False)
        self.icon_cache = {}          # lower-case path -> CTkImage or None
        self.icon_waiters = {}        # lower-case path -> callbacks waiting for that icon
        self.icon_pending = set()     # lower-case paths queued for extraction
        self.icon_jobs = None         # queue of paths for the icon thread (started on first use)
        self.dialogs = 0              # open Dialog windows
        self.names = {}
        self.callbacks = queue.Queue()
        self.busy = False
        self.current = "apps"
        self.nav_compact = False
        self.appearance = None        # theme the backdrop was last set for
        self._logos = {}
        self.title(f"CloseAllPython {__version__}")
        self.geometry("1180x740")
        self.minsize(860, 580)
        try:
            self.iconbitmap(resource_path("app.ico"))
        except tk.TclError:
            pass
        self.window_icon = WindowIcon(self)   # replaces Tk's 16/32 px icons with sharp ones
        self.fonts = Fonts(self)
        try:
            windows_dir = winapi.windows_directory()
        except Exception:
            windows_dir = None
        self.glyphs = Glyphs(windows_dir)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.nav_pane = None
        self.list_page = None
        self.updates = Updates(self)
        updater.cleanup()   # leftovers of an update installed by the previous run
        self.build()
        self.bind("<F5>", lambda _e: self.list_page.refresh() if self.current == "apps" else None)
        self.bind("<Control-f>", lambda _e: (self.show("apps"), self.list_page.focus_search()))
        self.after(POLL_MS, self._poll)
        self.after(50, self.apply_backdrop)
        if self.settings["auto_update"] and updater.current_executable() is not None:
            self.after(UPDATE_STARTUP_DELAY_MS, lambda: self.updates.check(automatic=True))

    # ---------------------------------------------------------------- helpers
    @property
    def language(self):
        return self.settings["language"]

    def t(self, key, **values):
        return translate(self.language, key, **values)

    def tn(self, key, count, **values):
        return translate_n(self.language, key, count, **values)

    def call_soon(self, callback):
        """Thread-safe: run `callback` on the Tk thread."""
        self.callbacks.put(callback)

    def _poll(self):
        while True:
            try:
                callback = self.callbacks.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:
                self.report_callback_exception(*sys.exc_info())
        if self.mica and ctk.get_appearance_mode() != self.appearance:
            self.apply_backdrop()   # Windows (or the setting) switched between light and dark
        self.after(POLL_MS, self._poll)

    def report_callback_exception(self, exc, value, tb):
        """Tk calls this when an interface callback raises: save the details and say so,
        instead of a silent failure (the windowed executable has no console)."""
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

    def app_logo(self, size):
        """CloseAllPython's own icon as a CTkImage (None if the .ico cannot be read)."""
        if size not in self._logos:
            try:
                picture = appicon.icon_image(resource_path("app.ico"), size * 2)
                self._logos[size] = ctk.CTkImage(light_image=picture, dark_image=mica_image(picture),
                                                 size=(size, size))
            except Exception:
                self._logos[size] = None
        return self._logos[size]

    def icon_for(self, exe_path, on_ready=None):
        """CTkImage of an executable's icon if already extracted, else None.

        Icons are extracted on a background thread so the window never waits on the disk;
        `on_ready(image)` is called on the Tk thread once this one is available.
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
        image = None
        if picture is not None:
            image = ctk.CTkImage(light_image=picture, dark_image=mica_image(picture), size=(ICON_SIZE, ICON_SIZE))
        self.icon_cache[key] = image
        for callback in self.icon_waiters.pop(key, []):
            if image is not None:
                callback(image)

    # ---------------------------------------------------------------- Mica
    def apply_backdrop(self, window=None):
        """Mica behind `window` (default: this one) in the dark theme, opaque otherwise.

        Under Mica every dark colour was converted for the backdrop (gui_theme.apply_palette): if
        Windows refuses the backdrop, the palette goes back to plain colours and the window is
        rebuilt, so it never shows those converted colours alone.
        """
        if not self.mica:
            return
        dark = ctk.get_appearance_mode() == "Dark"
        targets = [window] if window is not None else [self] + [w for w in self.winfo_children()
                                                                 if isinstance(w, Dialog)]
        if window is None:
            self.appearance = ctk.get_appearance_mode()
        for target in targets:
            try:
                ok = winapi.set_backdrop(int(target.wm_frame(), 16), dark)
            except Exception:
                log.debug("backdrop failed", exc_info=True)
                ok = False
            if not ok and dark and target is self:
                log.info("Mica refused by Windows: plain colours")
                self.mica = False
                self.mica_supported = False
                self.after(10, self.build)
                return

    # ---------------------------------------------------------------- layout
    def build(self):
        state = self.list_page.state() if self.list_page is not None else None
        if self.nav_pane is not None:
            self.nav_pane.destroy()
            self.content.destroy()
        apply_palette(self.mica)
        self.icon_cache.clear()
        self.glyphs.cache.clear()
        self._logos.clear()
        self.configure(fg_color=C["bg"])
        t = self.t
        self.nav_pane = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0,
                                     width=NAV_COMPACT_WIDTH if self.nav_compact else NAV_WIDTH)
        self.nav_pane.grid(row=0, column=0, sticky="ns")
        self.nav_pane.pack_propagate(False)
        toggle = icon_button(self.nav_pane, self, "menu", self.toggle_nav, size=36)
        toggle.pack(anchor="w", padx=(8, 0), pady=(4, 6))
        self.nav = {
            "apps": NavItem(self.nav_pane, self, "apps", "apps", t("nav_apps")),
            "background": NavItem(self.nav_pane, self, "background", "memory", t("nav_background")),
            "log": NavItem(self.nav_pane, self, "log", "log", t("nav_log")),
            "settings": NavItem(self.nav_pane, self, "settings", "settings", t("nav_settings")),
        }
        for name in ("apps", "background", "log"):
            self.nav[name].pack(fill="x", padx=(4, 8), pady=2)
        self.nav["settings"].pack(side="bottom", fill="x", padx=(4, 8), pady=(2, 10))
        for item in self.nav.values():
            item.set_compact(self.nav_compact)
        self.content = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.list_page = ListPage(self, state)
        self.pages = {"apps": self.list_page, "closing": ClosingPage(self), "background": BackgroundPage(self),
                      "log": LogPage(self), "settings": SettingsPage(self)}
        self.list_page.refresh()
        self.show(self.current if self.current != "closing" else "apps")
        self.appearance = None   # set the backdrop again for the new colours

    def toggle_nav(self):
        self.nav_compact = not self.nav_compact
        self.nav_pane.configure(width=NAV_COMPACT_WIDTH if self.nav_compact else NAV_WIDTH)
        for item in self.nav.values():
            item.set_compact(self.nav_compact)

    def show(self, name):
        if self.busy and name != "closing":
            return
        self.current = name
        if name == "log":
            self.pages["log"].load()
        elif name == "background":
            self.pages["background"].load()
        self.pages[name].tkraise()
        for key, item in self.nav.items():
            item.set_active(key == name or (name == "closing" and key == "apps"))

    def set_busy(self, busy):
        self.busy = busy
        self.configure(cursor="watch" if busy else "")

    # ---------------------------------------------------------------- actions
    def start_closing(self, targets, timeout):
        self.show("closing")
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
        if new["theme"] != old["theme"]:
            ctk.set_appearance_mode(new["theme"])
        mica = new["mica"] and self.mica_supported
        if new["language"] != old["language"] or mica != self.mica:
            if mica != self.mica:
                self.mica = mica
                if not mica:   # back to an opaque window before the plain colours arrive
                    try:
                        winapi.set_backdrop(int(self.wm_frame(), 16), False)
                    except Exception:
                        log.debug("backdrop reset failed", exc_info=True)
            # Rebuilt after the current callback returns: the settings page is replaced too.
            self.after(10, self.build)
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
            self.destroy()
        else:
            Dialog(self, self.t("error"), self.t("admin_failed"))


def main():
    app = App()
    app.mainloop()
    return 0
