"""Settings file and action log, both stored in the user's roaming profile."""
import json
import logging
import os
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .i18n import TEXT

DEFAULT_SETTINGS = {
    "language": "en",
    "theme": "system",
    "group_by_app": True,
    "show_icons": True,
    "confirm_before_terminate": True,
    "instant_force": True,
    "close_timeout": 5,
}
THEMES = ("system", "light", "dark")
BOOL_KEYS = ("group_by_app", "show_icons", "confirm_before_terminate", "instant_force")
TIMEOUT_MIN, TIMEOUT_MAX = 1, 60

LOGGER_NAME = "closeallpython"


def data_dir():
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "CloseAllPython"


def settings_path():
    return data_dir() / "settings.json"


def log_path():
    return data_dir() / "closeallpython.log"


def parse_settings(raw):
    """Validate a decoded settings object; anything invalid falls back to its default."""
    values = DEFAULT_SETTINGS.copy()
    if not isinstance(raw, dict):
        return values
    if raw.get("language") in TEXT:
        values["language"] = raw["language"]
    if raw.get("theme") in THEMES:
        values["theme"] = raw["theme"]
    elif isinstance(raw.get("dark_mode"), bool):
        # Settings written by version 1.1 and earlier.
        values["theme"] = "dark" if raw["dark_mode"] else "light"
    for key in BOOL_KEYS:
        # Only real JSON booleans are accepted: bool("false") would be True.
        if isinstance(raw.get(key), bool):
            values[key] = raw[key]
    timeout = raw.get("close_timeout")
    if isinstance(timeout, int) and not isinstance(timeout, bool) and TIMEOUT_MIN <= timeout <= TIMEOUT_MAX:
        values["close_timeout"] = timeout
    return values


def load_settings(path=None):
    try:
        raw = json.loads((path or settings_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = None
    return parse_settings(raw)


def save_settings(values, path=None):
    """Write the settings atomically so a crash never leaves a truncated file."""
    path = Path(path or settings_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(parse_settings(values), ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def setup_logging():
    """Log every close/stop action to a small rotating file next to the settings."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=256_000, backupCount=3, encoding="utf-8", delay=True)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    return logger
