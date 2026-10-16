"""Errors made visible. The windowed executable has no console: without this module a failure
at startup, or in an interface callback, would leave no trace on screen."""
import ctypes
import logging
import sys
import traceback

from . import __version__, settings as settings_mod
from .i18n import translate

log = logging.getLogger(settings_mod.LOGGER_NAME)

MB_ICONERROR = 0x10


def crash_path():
    return settings_mod.data_dir() / "crash.txt"


def write_report(details):
    """Save `details` to crash.txt next to the settings (and the log). Returns the path, or None."""
    path = crash_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"CloseAllPython {__version__}\n{details.rstrip()}\n", encoding="utf-8")
    except OSError:
        path = None
    log.error("unexpected error: %s", details.strip().splitlines()[-1] if details.strip() else "?")
    return path


def message_box(text, title="CloseAllPython"):
    """Native Windows message box (works before and without Tk), else stderr."""
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(None, text, title, MB_ICONERROR)
            return
        except (AttributeError, OSError):
            pass
    if sys.stderr is not None:
        sys.stderr.write(f"{title}: {text}\n")


def report_fatal(language="en", error=None):
    """The program cannot go on: save the traceback and tell the user why."""
    details = traceback.format_exc() if error is None else "".join(traceback.format_exception(error))
    path = write_report(details)
    reason = details.strip().splitlines()[-1] if details.strip() else "?"
    message_box(translate(language, "fatal_message", error=reason, path=path or "-"))
