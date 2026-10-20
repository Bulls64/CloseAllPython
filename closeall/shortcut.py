"""The "close everything" shortcut.

A .lnk on the desktop that starts CloseAllPython without any window and force-closes every
window (`--no-ui --all -y`, the command-line mode). Windows gives programs no way to pin
something to the taskbar by themselves, so pinning stays a right-click for the user:
`reveal` shows the shortcut in Explorer, where "Pin to taskbar" is one click away.
"""
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import updater
from .settings import LOGGER_NAME

log = logging.getLogger(LOGGER_NAME)

ARGUMENTS = ("--no-ui", "--all", "-y")
PROJECT_DIR = Path(__file__).resolve().parent.parent
WINDOW_MINIMIZED = 7
INVALID_NAME_CHARS = '<>:"/\\|?*'


class ShortcutError(Exception):
    """The shortcut could not be created; `detail` says why."""

    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class Launcher:
    target: str
    arguments: str
    directory: str
    icon: str


def launcher(exe_path=None, python=None, project_dir=None):
    """What the shortcut runs: the installed executable, or pythonw + the script from source."""
    exe_path = exe_path or updater.current_executable()
    arguments = " ".join(ARGUMENTS)
    if exe_path is not None:
        exe_path = Path(exe_path)
        return Launcher(str(exe_path), arguments, str(exe_path.parent), f"{exe_path},0")
    project_dir = Path(project_dir or PROJECT_DIR)
    python = Path(python or sys.executable)
    windowless = python.with_name("pythonw.exe")   # no console flash
    target = windowless if windowless.exists() else python
    icon = project_dir / "app.ico"
    return Launcher(str(target), f'"{project_dir / "closeallpython.py"}" {arguments}', str(project_dir),
                    f"{icon},0" if icon.exists() else f"{target},0")


def _wscript_shell():
    import win32com.client

    return win32com.client.Dispatch("WScript.Shell")


def _file_name(name):
    cleaned = "".join("-" if char in INVALID_NAME_CHARS else char for char in name).strip(" .")
    return f"{cleaned or 'CloseAllPython'}.lnk"


def desktop_folder(factory=None):
    """The user's desktop (follows a OneDrive-redirected one); None when it cannot be found."""
    try:
        folder = (factory or _wscript_shell)().SpecialFolders("Desktop")
    except Exception:
        log.exception("desktop folder lookup failed")
        return None
    return Path(folder) if folder else None


def find_any(names, folder=None, factory=None):
    """The first of these shortcuts that exists, else None (one desktop lookup for all)."""
    folder = Path(folder) if folder else desktop_folder(factory)
    if folder is None:
        return None
    return next((path for path in (folder / _file_name(name) for name in names) if path.is_file()), None)


def create(name, description="", folder=None, factory=None):
    """Create (or replace) the shortcut on the desktop; returns its path."""
    try:
        shell = (factory or _wscript_shell)()
        folder = Path(folder or shell.SpecialFolders("Desktop") or Path.home() / "Desktop")
        path = folder / _file_name(name)
        spec = launcher()
        link = shell.CreateShortcut(str(path))
        link.TargetPath = spec.target
        link.Arguments = spec.arguments
        link.WorkingDirectory = spec.directory
        link.IconLocation = spec.icon
        link.Description = description
        link.WindowStyle = WINDOW_MINIMIZED
        link.Save()
    except Exception as exc:   # ImportError without pywin32, com_error, read-only folder...
        log.exception("shortcut creation failed")
        raise ShortcutError(getattr(exc, "strerror", None) or str(exc)) from exc
    log.info("shortcut created: %s -> %s %s", path, spec.target, spec.arguments)
    return path


def reveal(path):
    """Open Explorer with the shortcut selected."""
    subprocess.Popen(f'explorer /select,"{path}"')   # noqa: S603 - fixed command, our own path
