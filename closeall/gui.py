"""CustomTkinter user interface: application list, closing screen, log and settings."""
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
from .gui_theme import (ACCENT, ACCENT_HOVER, C, WARN_FILL, WARN_FILL_HOVER, WARN_ON, WHITE, Fonts,
                        tile_color, tile_letter)
from .i18n import LANGUAGE_NAMES, format_memory, format_seconds, translate, translate_n

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


# ====================================================================== small building blocks

def label(master, text="", font=None, color="text", **kwargs):
    kwargs.setdefault("anchor", "w")
    kwargs.setdefault("justify", "left")
    return ctk.CTkLabel(master, text=text, font=font, text_color=C[color], **kwargs)


def ghost_button(master, app, text, command, font=None, **kwargs):
    kwargs.setdefault("height", 40)
    return ctk.CTkButton(master, text=text, command=command, font=font or app.fonts.body, height=kwargs.pop("height"),
                         corner_radius=8, border_width=1, border_color=C["border_strong"], fg_color="transparent",
                         hover_color=C["hover"], text_color=C["text"], **kwargs)


def primary_button(master, app, text, command, **kwargs):
    return ctk.CTkButton(master, text=text, command=command, font=app.fonts.body_bold, height=44, corner_radius=8,
                         fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=WHITE,
                         text_color_disabled=("#eef2fb", "#9aa1ad"), **kwargs)


def icon_button(master, app, glyph, command, size=40, **kwargs):
    return ctk.CTkButton(master, text=app.fonts.glyph(glyph), command=command, font=app.fonts.icon_small,
                         width=size, height=size, corner_radius=8, fg_color="transparent", hover_color=C["hover"],
                         text_color=C["muted"], **kwargs)


def segmented(master, app, values, command, fill=False):
    return ctk.CTkSegmentedButton(master, values=values, command=command, font=app.fonts.body, height=36,
                                  corner_radius=8, border_width=3, fg_color=C["inset"], selected_color=C["seg_selected"],
                                  selected_hover_color=C["seg_selected"], unselected_color=C["inset"],
                                  unselected_hover_color=C["hover"], text_color=C["text"], dynamic_resizing=not fill)


def tile(master, app, name, image=None, protected=False):
    """34 px square: the application's icon, or its initial on a coloured background."""
    if image is not None:
        box = ctk.CTkFrame(master, width=34, height=34, corner_radius=8, fg_color=C["tile"])
        inner = ctk.CTkLabel(box, text="", image=image, width=24, height=24, fg_color="transparent")
    else:
        box = ctk.CTkFrame(master, width=34, height=34, corner_radius=8,
                           fg_color=C["tile"] if protected else tile_color(name))
        inner = ctk.CTkLabel(box, text=tile_letter(name), font=app.fonts.tile, width=24, height=24,
                             fg_color="transparent", text_color=C["muted"] if protected else WHITE)
    box.pack_propagate(False)
    inner.place(relx=0.5, rely=0.5, anchor="center")
    box.inner = inner
    return box


def set_tile_icon(box, image):
    """Show an icon that arrived after the tile was drawn with the application's initial."""
    try:
        if image is not None and box.winfo_exists():
            box.configure(fg_color=C["tile"])
            box.inner.configure(text="", image=image)
    except tk.TclError:
        pass  # the card was rebuilt in the meantime


def pill(master, app):
    return ctk.CTkLabel(master, text="", font=app.fonts.small_bold, height=28, corner_radius=14, padx=12)


class Dialog(ctk.CTkToplevel):
    """Modal message in the application's style (confirmation when `confirm_text` is given)."""

    def __init__(self, app, title, message, items=(), confirm_text=None, on_confirm=None, cancel_text=None):
        super().__init__(app, fg_color=C["bg"])
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
        body.pack(fill="both", expand=True, padx=24, pady=22)
        label(body, title, app.fonts.h2).pack(fill="x")
        label(body, message, app.fonts.body, "muted", wraplength=440).pack(fill="x", pady=(6, 0))
        items = list(items)
        if items:
            shown, hidden = core.truncate(items, MAX_DIALOG_ITEMS)
            box = ctk.CTkFrame(body, fg_color=C["inset"], corner_radius=8)
            box.pack(fill="x", pady=(14, 0))
            for item in shown:
                label(box, f"•  {shorten(item, 70)}", app.fonts.body).pack(fill="x", padx=12, pady=(6, 0))
            if hidden:
                label(box, app.t("more_items", count=hidden), app.fonts.small, "muted").pack(fill="x", padx=12, pady=(6, 0))
            ctk.CTkFrame(box, fg_color="transparent", height=8).pack()
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", pady=(20, 0))
        if confirm_text:
            primary_button(buttons, app, confirm_text, self._confirm).pack(side="right")
            ghost_button(buttons, app, cancel_text or app.t("cancel"), self.destroy, height=44).pack(
                side="right", padx=(0, 10))
        else:
            primary_button(buttons, app, app.t("ok"), self.destroy, width=100).pack(side="right")
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
    window_count: int = 1


class AppCard(ctk.CTkFrame):
    def __init__(self, master, page, entry, image):
        super().__init__(master, fg_color=C["surface"], border_color=C["border"], border_width=1, corner_radius=10)
        app = page.app
        self.page, self.entry, self.windows_frame = page, entry, None
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=6)
        clickable = [row]
        if entry.protected:
            lock = label(row, app.fonts.glyph("lock"), app.fonts.icon_small, "faint", width=24)
            lock.pack(side="left", padx=(6, 8))
            self.check = None
        else:
            self.check = ctk.CTkCheckBox(row, text="", width=24, checkbox_width=20, checkbox_height=20, corner_radius=5,
                                         border_width=2, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                         border_color=C["faint"], checkmark_color=WHITE, command=self._on_check)
            self.check.pack(side="left", padx=(6, 8))
        icon = tile(row, app, entry.name, image, entry.protected)
        icon.pack(side="left", padx=(0, 14), pady=4)
        self.tile = icon
        texts = ctk.CTkFrame(row, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True)
        name = label(texts, entry.name, app.fonts.name, "muted" if entry.protected else "text")
        name.pack(fill="x")
        meta = label(texts, entry.meta, app.fonts.small, "faint" if entry.protected else "muted")
        meta.pack(fill="x")
        clickable += [icon, icon.inner, texts, name, meta]
        self.chevron = None
        if entry.titles:
            self.chevron = icon_button(row, app, "chevron_right", self.toggle_expand, size=40)
            self.chevron.pack(side="right")
        if not entry.protected:
            for widget in clickable:
                widget.bind("<Button-1>", lambda _e: self.check.toggle())
        if entry.protected:
            self.configure(border_color=C["border"], fg_color=C["bg"])

    def _on_check(self):
        self.page.set_selected(self.entry.proc_key, bool(self.check.get()))

    def show_selected(self, selected):
        if self.check is None:
            return
        if selected:
            self.check.select()
        else:
            self.check.deselect()
        self.configure(fg_color=C["sel_bg"] if selected else C["surface"],
                       border_color=C["sel_border"] if selected else C["border"])

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
        self.chevron.configure(text=app.fonts.glyph("chevron_down" if expanded else "chevron_right"))
        if expanded and self.windows_frame is None:
            # Built on first use: most cards are never expanded.
            self.windows_frame = ctk.CTkFrame(self, fg_color="transparent")
            for title in self.entry.titles:
                row = ctk.CTkFrame(self.windows_frame, fg_color=C["inset"], corner_radius=6)
                row.pack(fill="x", pady=(0, 3))
                label(row, f"•   {shorten(title)}", app.fonts.small).pack(fill="x", padx=12, pady=6)
        if self.windows_frame is not None:
            if expanded:
                self.windows_frame.pack(fill="x", padx=(86, 16), pady=(0, 10))
            else:
                self.windows_frame.pack_forget()


class ListPage(ctk.CTkFrame):
    def __init__(self, app, state=None):
        super().__init__(app, fg_color=C["bg"], corner_radius=0)
        self.app = app
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
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(22, 14))
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        label(titles, t("apps_title"), app.fonts.title).pack(fill="x")
        self.summary = label(titles, "", app.fonts.body, "muted")
        self.summary.pack(fill="x", pady=(2, 0))
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.pack(side="right", anchor="s")
        refresh = ctk.CTkButton(actions, text=app.fonts.glyph("refresh"), command=self.refresh, width=40, height=40,
                                corner_radius=8, border_width=1, border_color=C["border_strong"],
                                fg_color=C["surface"], hover_color=C["hover"], text_color=C["text"],
                                font=app.fonts.icon_small)
        refresh.pack(side="right")
        if not app.is_admin:
            admin = ctk.CTkButton(actions, text=f"{t('admin_button')}", command=app.restart_as_admin, height=40,
                                  corner_radius=8, border_width=1, border_color=C["border_strong"],
                                  fg_color=C["surface"], hover_color=C["hover"], text_color=C["text"],
                                  font=app.fonts.body)
            admin.pack(side="right", padx=(0, 8))

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 14))
        search = ctk.CTkFrame(toolbar, fg_color=C["inset"], border_color=C["border_strong"], border_width=1,
                              corner_radius=8, height=40)
        search.pack(side="left", fill="x", expand=True, padx=(0, 12))
        label(search, app.fonts.glyph("search"), app.fonts.icon_small, "faint", width=20).pack(side="left", padx=(12, 4))
        self.search = ctk.CTkEntry(search, placeholder_text=t("search_placeholder"), font=app.fonts.body, height=36,
                                   border_width=0, fg_color=C["inset"], text_color=C["text"],
                                   placeholder_text_color=C["faint"])
        self.search.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=2)
        if state.get("query"):
            self.search.insert(0, state["query"])
        self.search.bind("<KeyRelease>", self._schedule_filter)
        self.search.bind("<Escape>", self._clear_search)
        self.filter_button = segmented(toolbar, app, ["all", "selected"], self._on_filter)
        self.filter_button.pack(side="right")

        self.list = ctk.CTkScrollableFrame(self, fg_color=C["bg"], corner_radius=0,
                                           scrollbar_button_color=C["scroll"],
                                           scrollbar_button_hover_color=C["scroll_hover"])
        self.list.grid(row=2, column=0, sticky="nsew", padx=(20, 8))
        self.empty = label(self.list, "", app.fonts.body, "muted", anchor="center", justify="center")
        self.protected_header = ctk.CTkFrame(self.list, fg_color="transparent")
        label(self.protected_header, app.fonts.glyph("lock"), app.fonts.icon_small, "muted", width=18).pack(side="left")
        label(self.protected_header, t("protected_header").upper(), app.fonts.small_bold, "muted").pack(side="left", padx=6)

        bar = ctk.CTkFrame(self, fg_color=C["bar"], corner_radius=0, border_width=0)
        bar.grid(row=3, column=0, sticky="ew")
        texts = ctk.CTkFrame(bar, fg_color="transparent")
        self.selection_line = label(texts, "", app.fonts.body_bold)
        self.selection_line.pack(fill="x")
        self.hint = label(texts, "", app.fonts.small, "muted")
        self.hint.pack(fill="x")
        self.close_button = primary_button(bar, app, "", self.close_selected)
        self.close_button.pack(side="right", padx=(0, 28))
        self.clear_button = ghost_button(bar, app, t("clear_selection"), self.clear_selection, height=44)
        self.explorer_button = ghost_button(bar, app, t("close_explorer"), self.close_explorer, height=44)
        self.explorer_button.pack(side="right", padx=(0, 10))
        # Packed after the buttons: they keep their full width and the texts take what is left.
        texts.pack(side="left", fill="x", expand=True, padx=28, pady=14)
        texts.bind("<Configure>", self._wrap_bar_texts)

    def _wrap_bar_texts(self, event):
        # Narrow window or long translation: wrap the texts instead of cutting them off.
        width = max(80, int(event.width / self._get_widget_scaling()))
        for widget in (self.selection_line, self.hint):
            if widget.cget("wraplength") != width:
                widget.configure(wraplength=width)

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
                                     first.exe_path, first.protected, len(windows)))
        else:
            for w in self.windows:
                app_name = app.display_name(w.exe_path) or t("process_n", pid=w.pid)
                meta = f"{app_name} · {t('pid', pid=w.pid)}"
                entries.append(Entry(("window", w.hwnd), w.key, shorten(w.title), meta,
                                     f"{w.title} {app_name}".casefold(), [], w.exe_path, w.protected, 1))
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
            card = old.pop(entry.card_key, None)
            if card is not None and (rebuild or card.entry != entry):
                card.destroy()
                card = None
            if card is None:
                image = None
                if self.app.settings["show_icons"]:
                    image = self.app.icon_for(entry.exe_path, lambda img, key=entry.card_key: self._icon_ready(key, img))
                card = AppCard(self.list, self, entry, image)
                card.show_expanded(entry.card_key in self.expanded)
            card.show_selected(entry.proc_key in self.selected)
            self.cards[entry.card_key] = card
        for card in old.values():
            card.destroy()

    def _icon_ready(self, card_key, image):
        card = self.cards.get(card_key)
        if card is not None:
            set_tile_icon(card.tile, image)

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

    def _on_filter(self, value):
        self.filter = "selected" if value == self.filter_button.cget("values")[1] else "all"
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
            self.cards[entry.card_key].pack(fill="x", padx=(0, 12), pady=(0, 8))
        if protected:
            self.protected_header.pack(fill="x", padx=4, pady=(14, 8))
            for entry in protected:
                self.cards[entry.card_key].pack(fill="x", padx=(0, 12), pady=(0, 8))
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
        values = [t("filter_all", count=self.selectable_count), t("filter_selected", count=len(self.selected))]
        self.filter_button.configure(values=values)
        self.filter_button.set(values[1] if self.filter == "selected" else values[0])
        count = len(self.selected)
        windows = sum(1 for w in self.windows if w.key in self.selected)
        if count:
            self.selection_line.configure(text=f"{app.tn('n_selected', count)} · {app.tn('n_windows', windows)}")
            self.close_button.configure(text=app.tn("close_button", count), state="normal")
            self.clear_button.pack(side="right", padx=(0, 10), after=self.close_button)
        else:
            self.selection_line.configure(text=t("selection_none"))
            self.close_button.configure(text=t("close_button_none"), state="disabled")
            self.clear_button.pack_forget()
        if self.notice:
            self.selection_line.configure(text=self.notice)
        self.hint.configure(text=t("close_hint_instant") if app.settings["instant_force"]
                            else t("close_hint", seconds=app.settings["close_timeout"]))

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
            Dialog(app, app.t("confirm_title"), app.t("confirm_message_instant" if instant else "confirm_message", seconds=timeout), items,
                   app.tn("close_button", len(targets)), start)
        else:
            start()

    def close_explorer(self):
        """Close File Explorer windows only; explorer.exe (desktop, taskbar) keeps running."""
        app = self.app
        if app.busy:
            return
        count = core.close_explorer_windows()
        self.notice = app.tn("explorer_closed", count) if count else app.t("explorer_none")
        if self.notice_job is not None:
            self.after_cancel(self.notice_job)
        self.notice_job = self.after(NOTICE_MS, self._end_notice)
        self.update_counts()
        self.schedule_refreshes(EXPLORER_REFRESH_MS)

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
        super().__init__(master, fg_color=C["surface"], border_color=C["border"], border_width=1, corner_radius=10)
        app = page.app
        self.page, self.target = page, target
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=12)
        name = app.display_name(target.exe_path) or app.t("process_n", pid=target.pid)
        image = None
        if app.settings["show_icons"]:
            image = app.icon_for(target.exe_path, lambda img: set_tile_icon(self.tile, img))
        self.tile = tile(top, app, name, image)
        self.tile.pack(side="left", padx=(0, 14))
        texts = ctk.CTkFrame(top, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True)
        label(texts, name, app.fonts.name).pack(fill="x")
        meta = " · ".join([shorten(", ".join(target.titles), 80), app.t("pid", pid=target.pid)])
        label(texts, meta, app.fonts.small, "muted").pack(fill="x")
        self.pill = pill(top, app)
        self.pill.pack(side="right")
        self.body = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.explain = label(self.body, "", app.fonts.small, "warn_text", wraplength=470)
        self.explain.pack(side="left", fill="x", expand=True, padx=(64, 12), pady=(0, 14))
        self.leave = ghost_button(self.body, app, app.t("leave_open"), self._leave, height=40)
        self.show = ghost_button(self.body, app, f"{app.t('show_window')}", self._show, height=40)
        self.set_waiting()

    def _style(self, text, bg, fg, border):
        self.pill.configure(text=text, fg_color=C[bg], text_color=C[fg])
        self.configure(border_color=C[border])

    def set_waiting(self):
        self._style(self.page.app.t("status_waiting"), "neutral_bg", "muted", "border")

    def set_forcing(self):
        self._style(self.page.app.t("status_forcing"), "neutral_bg", "muted", "border")
        self.body.pack_forget()

    def set_result(self, result):
        app = self.page.app
        self.body.pack_forget()
        self.configure(fg_color=C["surface"])
        if result.status == core.CLOSED:
            text = (app.t("status_closed", seconds=format_seconds(app.language, result.elapsed))
                    if result.elapsed >= 0.1 else app.t("log_closed"))
            self._style(text, "ok_bg", "ok_fg", "border")
        elif result.status == core.FORCED:
            self._style(app.t("status_forced"), "warn_pill", "warn_fg", "border")
        elif result.status == core.STILL_RUNNING:
            self._style(app.t("status_still"), "warn_pill", "warn_fg", "warn_border")
            self.configure(fg_color=C["warn_bg"])
            self.explain.configure(text=app.t("still_explain", seconds=self.page.timeout), text_color=C["warn_text"])
            self.leave.pack(side="right", padx=(0, 16), pady=(0, 14))
            self.show.pack(side="right", padx=(0, 8), pady=(0, 14))
            self.body.pack(fill="x", padx=2, pady=(0, 2))
        else:  # FAILED
            self._style(app.t("status_failed"), "err_bg", "err_fg", "err_border")
            text = app.t(result.error_key, detail=result.detail) if result.error_key else ""
            if result.error_key == "access_denied" and not app.is_admin:
                text += "\n" + app.t("admin_hint")
            self.explain.configure(text=text[:1].upper() + text[1:], text_color=C["err_fg"])
            self.leave.pack_forget()
            self.show.pack_forget()
            self.body.pack(fill="x", padx=2, pady=(0, 2))

    def set_left_open(self):
        self._style(self.page.app.t("status_left"), "neutral_bg", "muted", "border")
        self.configure(fg_color=C["surface"])
        self.body.pack_forget()

    def _leave(self):
        self.page.leave_open(self.target)

    def _show(self):
        hwnds = core.windows_of(self.target)
        if hwnds:
            winapi.bring_to_front(hwnds[0])


class ClosingPage(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color=C["bg"], corner_radius=0)
        self.app = app
        t = app.t
        self.rows, self.results, self.left_open = {}, {}, set()
        self.targets, self.timeout, self.running, self.started = [], 0, False, 0.0
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=36, pady=(24, 0))
        self.back = ctk.CTkButton(head, text=f"‹  {t('apps_title')}", command=self.finish, height=28, anchor="w",
                                  fg_color="transparent", hover_color=C["hover"], text_color=C["muted"],
                                  font=app.fonts.small, width=0)
        self.back.pack(anchor="w")
        line = ctk.CTkFrame(head, fg_color="transparent")
        line.pack(fill="x", pady=(10, 0))
        texts = ctk.CTkFrame(line, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True)
        self.title = label(texts, t("closing_title"), app.fonts.title)
        self.title.pack(fill="x")
        self.subtitle = label(texts, "", app.fonts.body, "muted")
        self.subtitle.pack(fill="x", pady=(2, 0))
        self.elapsed = label(line, "", app.fonts.mono, "muted")
        self.elapsed.pack(side="right", anchor="s")
        self.progress = ctk.CTkProgressBar(self, height=6, corner_radius=3, fg_color=C["inset"], progress_color=ACCENT)
        self.progress.grid(row=1, column=0, sticky="ew", padx=36, pady=(16, 18))

        self.list = ctk.CTkScrollableFrame(self, fg_color=C["bg"], corner_radius=0,
                                           scrollbar_button_color=C["scroll"],
                                           scrollbar_button_hover_color=C["scroll_hover"])
        self.list.grid(row=2, column=0, sticky="nsew", padx=(28, 8))

        bar = ctk.CTkFrame(self, fg_color=C["bar"], corner_radius=0)
        bar.grid(row=3, column=0, sticky="ew")
        texts = ctk.CTkFrame(bar, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True, padx=36, pady=14)
        self.summary = label(texts, "", app.fonts.body_bold)
        self.summary.pack(fill="x")
        label(texts, t("closing_hint"), app.fonts.small, "muted").pack(fill="x")
        self.force_button = ctk.CTkButton(bar, text="", command=self.force, font=app.fonts.body_bold, height=44,
                                          corner_radius=8, fg_color=WARN_FILL, hover_color=WARN_FILL_HOVER,
                                          text_color=WARN_ON)
        self.done_button = ghost_button(bar, app, t("done"), self.finish, height=44)

    def start(self, targets, timeout):
        self.targets, self.timeout = targets, timeout
        self.results, self.left_open = {}, set()
        for row in self.rows.values():
            row.destroy()
        self.rows = {}
        for target in targets:
            row = ClosingRow(self.list, self, target)
            row.pack(fill="x", padx=(0, 12), pady=(0, 10))
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
            self.force_button.pack(side="right", padx=(0, 36))
            self.done_button.pack(side="right", padx=(0, 10))
        else:
            self.done_button.pack(side="right", padx=(0, 36))
        state = "disabled" if self.running else "normal"
        self.done_button.configure(state=state)
        self.back.configure(state=state)

    def leave_open(self, target):
        self.left_open.add(target.key)
        self.rows[target.key].set_left_open()
        log.info("left_open pid=%s exe=%s titles=%r", target.pid, target.exe_path, target.titles)
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
                      r"pid=(\d+) exe=(.*?) titles=(\[.*?\])(?: error=(\S+)(?: (.*))?)?$")


def format_log_line(app, line):
    match = LOG_LINE.match(line.rstrip("\n"))
    if not match:
        return line.rstrip("\n")
    when, status, pid, exe, titles, error_key, detail = match.groups()
    name = app.display_name(exe) if exe and exe != "None" else app.t("process_n", pid=pid)
    try:
        titles = "; ".join(ast.literal_eval(titles))
    except (ValueError, SyntaxError):
        pass
    status_text = app.t("status_left") if status == "left_open" else app.t(f"log_{status}")
    text = f"{when}   {status_text:<18} {name} ({pid})   {shorten(titles, 90)}"
    if error_key:
        try:
            text += f"   — {app.t(error_key, detail=detail or '')}"
        except KeyError:
            text += f"   — {error_key} {detail or ''}"
    return text


class LogPage(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color=C["bg"], corner_radius=0)
        self.app = app
        t = app.t
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(22, 14))
        texts = ctk.CTkFrame(header, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True)
        label(texts, t("log_title"), app.fonts.title).pack(fill="x")
        label(texts, str(settings_mod.log_path()), app.fonts.small, "muted").pack(fill="x", pady=(2, 0))
        ghost_button(header, app, t("log_open_file"), self.open_file).pack(side="right")
        ghost_button(header, app, t("refresh"), self.load).pack(side="right", padx=(0, 8))
        self.text = ctk.CTkTextbox(self, font=app.fonts.mono, fg_color=C["surface"], border_color=C["border"],
                                   border_width=1, corner_radius=10, text_color=C["text"], wrap="none",
                                   scrollbar_button_color=C["scroll"], scrollbar_button_hover_color=C["scroll_hover"])
        self.text.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 24))

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

class BackgroundPage(ctk.CTkFrame):
    """The background processes (no window) using the most memory."""

    def __init__(self, app):
        super().__init__(app, fg_color=C["bg"], corner_radius=0)
        self.app = app
        t = app.t
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(22, 10))
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        label(titles, t("background_title"), app.fonts.title).pack(fill="x")
        self.summary = label(titles, "", app.fonts.body, "muted")
        self.summary.pack(fill="x", pady=(2, 0))
        ghost_button(header, app, t("refresh"), self.load).pack(side="right", anchor="n")

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 12))
        self.include_system = ctk.BooleanVar(value=app.settings["background_include_system"])
        ctk.CTkSwitch(options, text=t("background_include_system"), variable=self.include_system,
                      command=self._on_include_system, font=app.fonts.body, text_color=C["text"],
                      switch_width=40, switch_height=22, progress_color=ACCENT, button_color=WHITE,
                      button_hover_color="#f0f2f5", fg_color=("#b8c0cc", "#4a505c")).pack(fill="x")
        self.hint = label(options, t("background_hint"), app.fonts.small, "muted", wraplength=680)
        self.hint.pack(fill="x", pady=(6, 0))

        self.list = ctk.CTkScrollableFrame(self, fg_color=C["bg"], corner_radius=0, scrollbar_button_color=C["scroll"],
                                           scrollbar_button_hover_color=C["scroll_hover"])
        self.list.grid(row=2, column=0, sticky="nsew", padx=(20, 8), pady=(0, 20))
        self.report = None

    def _on_include_system(self):
        self.app.update_settings(background_include_system=bool(self.include_system.get()))
        self.load()

    def load(self):
        app, t = self.app, self.app.t
        for child in self.list.winfo_children():
            child.destroy()
        try:
            self.report = core.background_processes(core.list_windows(),
                                                    include_system=app.settings["background_include_system"])
        except OSError as exc:
            self.report = None
            self.summary.configure(text=t("background_error", error=exc))
            return
        report = self.report
        if not report.top:
            self.summary.configure(text=t("background_empty"))
            return
        self.summary.configure(text=app.tn("background_summary", report.count, shown=len(report.top),
                                           total=format_memory(app.language, report.total)))
        largest = max(report.top[0].memory, 1)
        app.preload_icons(p.exe_path for p in report.top)
        for rank, process in enumerate(report.top, 1):
            self._row(rank, process, largest)

    def _row(self, rank, process, largest):
        app = self.app
        card = ctk.CTkFrame(self.list, fg_color=C["surface"], border_color=C["border"], border_width=1, corner_radius=10)
        card.pack(fill="x", padx=8, pady=(0, 8))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)
        label(row, str(rank), app.fonts.mono, "faint", width=24, anchor="e").pack(side="left", padx=(0, 12))
        name = app.display_name(process.exe_path) if process.exe_path else process.app_name
        box = tile(row, app, name, None, process.protected)
        box.pack(side="left", padx=(0, 14), pady=2)
        if process.exe_path and app.settings["show_icons"]:
            set_tile_icon(box, app.icon_for(process.exe_path, on_ready=lambda image, box=box: set_tile_icon(box, image)))
        memory = ctk.CTkFrame(row, fg_color="transparent", width=170)
        memory.pack(side="right", padx=(12, 4))
        label(memory, format_memory(app.language, process.memory), app.fonts.body_bold, anchor="e").pack(fill="x")
        bar = ctk.CTkProgressBar(memory, width=160, height=6, corner_radius=3, progress_color=ACCENT,
                                 fg_color=C["inset"])
        bar.set(process.memory / largest)
        bar.pack(pady=(4, 2))
        texts = ctk.CTkFrame(row, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True)
        label(texts, name, app.fonts.name, "muted" if process.protected else "text").pack(fill="x")
        meta = f"{process.name} · {app.t('pid', pid=process.pid)}"
        if process.protected:
            meta += f" · {app.t('background_windows')}"
        label(texts, meta, app.fonts.small, "faint" if process.protected else "muted").pack(fill="x")


# ====================================================================== settings

class SettingsPage(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color=C["bg"], corner_radius=0)
        self.app = app
        t, s = app.t, app.settings
        self.save_job = None
        scroll = ctk.CTkScrollableFrame(self, fg_color=C["bg"], corner_radius=0, scrollbar_button_color=C["scroll"],
                                        scrollbar_button_hover_color=C["scroll_hover"])
        scroll.pack(fill="both", expand=True, padx=(20, 8))
        label(scroll, t("settings_title"), app.fonts.title).pack(fill="x", padx=8, pady=(22, 0))
        label(scroll, t("settings_subtitle", path=settings_mod.data_dir()), app.fonts.body, "muted").pack(
            fill="x", padx=8, pady=(2, 18))
        grid = ctk.CTkFrame(scroll, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=(8, 12))
        grid.grid_columnconfigure((0, 1), weight=1, uniform="col")

        display = self._section(grid, t("section_display"), 0, 0)
        self._caption(display, t("language"))
        self.language_values = list(LANGUAGE_NAMES.items())
        language = segmented(display, app, [name for _, name in self.language_values], self._on_language, fill=True)
        language.set(LANGUAGE_NAMES[s["language"]])
        language.pack(fill="x", pady=(6, 16))
        self._caption(display, t("theme"))
        self.theme_values = [(code, t(f"theme_{code}")) for code in settings_mod.THEMES]
        theme = segmented(display, app, [name for _, name in self.theme_values], self._on_theme, fill=True)
        theme.set(dict(self.theme_values)[s["theme"]])
        theme.pack(fill="x", pady=(6, 4))

        listing = self._section(grid, t("section_list"), 0, 1)
        self._switch(listing, "group_by_app", t("group_by_app"), t("group_hint"))
        self._switch(listing, "show_icons", t("show_icons"), t("icons_hint"))

        closing = self._section(grid, t("section_closing"), 1, 0)
        self._switch(closing, "confirm_before_terminate", t("confirm_before_terminate"), t("confirm_hint"))
        self._switch(closing, "instant_force", t("instant_force"), t("instant_force_hint"))
        line = ctk.CTkFrame(closing, fg_color="transparent")
        line.pack(fill="x", pady=(12, 0))
        label(line, t("close_timeout"), app.fonts.body).pack(side="left")
        self.timeout_value = label(line, t("seconds_value", seconds=s["close_timeout"]), app.fonts.mono, anchor="e")
        self.timeout_value.pack(side="right")
        slider = ctk.CTkSlider(closing, from_=settings_mod.TIMEOUT_MIN, to=settings_mod.TIMEOUT_MAX,
                               number_of_steps=settings_mod.TIMEOUT_MAX - settings_mod.TIMEOUT_MIN,
                               command=self._on_timeout, progress_color=ACCENT, button_color=ACCENT,
                               button_hover_color=ACCENT_HOVER, fg_color=C["border_strong"])
        slider.set(s["close_timeout"])
        slider.pack(fill="x", pady=(10, 4))
        label(closing, t("timeout_hint"), app.fonts.small, "muted").pack(fill="x")

        about = self._section(grid, t("section_about"), 1, 1)
        facts = ctk.CTkFrame(about, fg_color="transparent")
        facts.pack(fill="x")
        facts.grid_columnconfigure(1, weight=1)
        rows = ((t("version"), __version__), (t("rights"), t("rights_admin") if app.is_admin else t("rights_user")),
                (t("log_file"), settings_mod.log_path().name))
        for index, (name, value) in enumerate(rows):
            label(facts, name, app.fonts.small, "muted").grid(row=index, column=0, sticky="w", pady=3, padx=(0, 24))
            label(facts, value, app.fonts.small).grid(row=index, column=1, sticky="w", pady=3)
        buttons = ctk.CTkFrame(about, fg_color="transparent")
        buttons.pack(fill="x", pady=(14, 0))
        ghost_button(buttons, app, t("open_log"), lambda: app.show("log")).pack(side="left")
        if not app.is_admin:
            ghost_button(buttons, app, t("admin_restart"), app.restart_as_admin).pack(side="left", padx=(8, 0))
        updates = ctk.CTkFrame(about, fg_color="transparent")
        updates.pack(fill="x", pady=(16, 0))
        self._switch(updates, "auto_update", t("auto_update"), t("auto_update_hint"))
        line = ctk.CTkFrame(updates, fg_color="transparent")
        line.pack(fill="x", pady=(8, 0))
        self.check_button = ghost_button(line, app, t("check_updates"), app.updates.check)
        self.check_button.pack(side="left")
        self.update_status = label(updates, "", app.fonts.small, "muted", wraplength=360)
        self.update_status.pack(fill="x", pady=(8, 0))
        app.updates.on_status = self._show_update_status
        self._show_update_status()

        link = self._section(grid, t("section_shortcut"), 2, 0, columnspan=2)
        label(link, t("shortcut_hint"), app.fonts.small, "muted", wraplength=640).pack(fill="x")
        line = ctk.CTkFrame(link, fg_color="transparent")
        line.pack(fill="x", pady=(12, 0))
        ghost_button(line, app, t("shortcut_create"), self._create_shortcut).pack(side="left")
        self.pin_button = ghost_button(line, app, t("shortcut_pin"), self._pin_shortcut)
        self.pin_button.pack(side="left", padx=(8, 0))
        self.shortcut_status = label(link, "", app.fonts.small, "muted", wraplength=640)
        self.shortcut_status.pack(fill="x", pady=(8, 0))
        self.shortcut_file = shortcut.find(t("shortcut_name"))
        self._show_shortcut_status()

    def _show_shortcut_status(self):
        file = self.shortcut_file
        self.shortcut_status.configure(text=self.app.t("shortcut_ready", path=file) if file else "")
        self.pin_button.configure(state="normal" if file else "disabled")

    def _create_shortcut(self):
        t = self.app.t
        try:
            self.shortcut_file = shortcut.create(t("shortcut_name"), t("shortcut_description"))
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
            self.update_status.configure(text=updates.status_text())
            self.check_button.configure(state="disabled" if updates.running or updates.installed else "normal")
        except tk.TclError:
            pass   # page destroyed (language change): the new page registers itself

    def _section(self, grid, title, row, column, columnspan=1):
        box = ctk.CTkFrame(grid, fg_color=C["surface"], border_color=C["border"], border_width=1, corner_radius=12)
        padx = (0, 0) if columnspan > 1 else (0 if column == 0 else 8, 8 if column == 0 else 0)
        box.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", padx=padx, pady=(0, 16))
        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=18)
        label(inner, title, self.app.fonts.h2).pack(fill="x", pady=(0, 12))
        return inner

    def _caption(self, master, text):
        label(master, text, self.app.fonts.small, "muted").pack(fill="x")

    def _switch(self, master, key, title, hint):
        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(fill="x", pady=6)
        variable = ctk.BooleanVar(value=self.app.settings[key])
        switch = ctk.CTkSwitch(row, text="", variable=variable, width=46, switch_width=40, switch_height=22,
                               progress_color=ACCENT, button_color=WHITE, button_hover_color="#f0f2f5",
                               fg_color=("#b8c0cc", "#4a505c"),
                               command=lambda: self.app.update_settings(**{key: bool(variable.get())}))
        switch.pack(side="right", padx=(12, 0))
        texts = ctk.CTkFrame(row, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True)
        title_label = label(texts, title, self.app.fonts.body)
        title_label.pack(fill="x")
        hint_label = label(texts, hint, self.app.fonts.small, "muted")
        hint_label.pack(fill="x")
        for widget in (texts, title_label, hint_label):
            widget.bind("<Button-1>", lambda _e: switch.toggle())

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
                     lambda exc: self._failed(exc, automatic))

    def _failed(self, exc, automatic):
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

        webbrowser.open(release.page)

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
                     lambda exc: self._failed(exc, not restart))

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

class NavButton(ctk.CTkFrame):
    def __init__(self, master, app, name, glyph, text):
        super().__init__(master, fg_color="transparent", corner_radius=10, width=64, height=58)
        self.app, self.name = app, name
        self.pack_propagate(False)
        self.icon = ctk.CTkLabel(self, text=app.fonts.glyph(glyph), font=app.fonts.icon, text_color=C["muted"])
        self.icon.pack(pady=(9, 0))
        self.text = ctk.CTkLabel(self, text=text, font=app.fonts.tiny, text_color=C["muted"], height=14)
        self.text.pack()
        for widget in (self, self.icon, self.text):
            widget.bind("<Button-1>", lambda _e: app.show(name))
        self.enabled = True

    def set_active(self, active):
        self.configure(fg_color=C["rail_active"] if active else "transparent")
        color = C["text"] if active else C["muted"]
        self.icon.configure(text_color=color)
        self.text.configure(text_color=color)


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=C["bg"])
        self.settings = settings_mod.load_settings()
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
        self.title(f"CloseAllPython {__version__}")
        self.geometry("1040x700")
        self.minsize(820, 560)
        try:
            self.iconbitmap(resource_path("app.ico"))
        except tk.TclError:
            pass
        self.window_icon = WindowIcon(self)   # replaces Tk's 16/32 px icons with sharp ones
        self.fonts = Fonts(self)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.rail = None
        self.list_page = None
        self.updates = Updates(self)
        updater.cleanup()   # leftovers of an update installed by the previous run
        self.build()
        self.bind("<F5>", lambda _e: self.list_page.refresh() if self.current == "apps" else None)
        self.bind("<Control-f>", lambda _e: (self.show("apps"), self.list_page.focus_search()))
        self.after(POLL_MS, self._poll)
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
            image = ctk.CTkImage(light_image=picture, dark_image=picture, size=(ICON_SIZE, ICON_SIZE))
        self.icon_cache[key] = image
        for callback in self.icon_waiters.pop(key, []):
            if image is not None:
                callback(image)

    # ---------------------------------------------------------------- layout
    def build(self):
        state = self.list_page.state() if self.list_page is not None else None
        if self.rail is not None:
            self.rail.destroy()
            for page in self.pages.values():
                page.destroy()
        self.rail = ctk.CTkFrame(self, fg_color=C["rail"], corner_radius=0, width=80)
        self.rail.grid(row=0, column=0, sticky="ns")
        self.rail.grid_propagate(False)
        self.nav = {
            "apps": NavButton(self.rail, self, "apps", "apps", self.t("nav_apps")),
            "background": NavButton(self.rail, self, "background", "memory", self.t("nav_background")),
            "log": NavButton(self.rail, self, "log", "log", self.t("nav_log")),
            "settings": NavButton(self.rail, self, "settings", "settings", self.t("nav_settings")),
        }
        self.nav["apps"].pack(pady=(14, 4))
        self.nav["background"].pack(pady=4)
        self.nav["log"].pack(pady=4)
        self.nav["settings"].pack(side="bottom", pady=14)
        self.list_page = ListPage(self, state)
        self.pages = {"apps": self.list_page, "closing": ClosingPage(self), "background": BackgroundPage(self),
                      "log": LogPage(self),
                      "settings": SettingsPage(self)}
        for page in self.pages.values():
            page.grid(row=0, column=1, sticky="nsew")
        self.list_page.refresh()
        self.show(self.current if self.current != "closing" else "apps")

    def show(self, name):
        if self.busy and name != "closing":
            return
        self.current = name
        if name == "log":
            self.pages["log"].load()
        elif name == "background":
            self.pages["background"].load()
        self.pages[name].tkraise()
        for key, button in self.nav.items():
            button.set_active(key == name or (name == "closing" and key == "apps"))

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
        if new["theme"] != old["theme"]:
            ctk.set_appearance_mode(new["theme"])
        if new["language"] != old["language"]:
            # Rebuilt after the current callback returns: the settings page is replaced too.
            self.after(10, self.build)
            return
        if new["group_by_app"] != old["group_by_app"] or new["show_icons"] != old["show_icons"]:
            self.list_page.refresh(rebuild=True)
        elif new["close_timeout"] != old["close_timeout"]:
            self.list_page.update_counts()

    def restart_as_admin(self):
        if winapi.relaunch_as_admin():
            self.destroy()
        else:
            Dialog(self, self.t("error"), self.t("admin_failed"))


def main():
    app = App()
    app.mainloop()
    return 0
