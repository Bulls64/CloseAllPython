"""Updates from the GitHub releases of the project.

The latest release is read from the GitHub API. Its executable is downloaded next to the running
one, checked against the SHA-256 digest GitHub publishes for it, then swapped in: Windows lets a
running executable be renamed (not overwritten), so the current file becomes `<name>.old`, the new
one takes its name, and the leftover is removed at the next start. Only the frozen executables can
update themselves; from source, the caller points to `git pull` or the release page.
"""
import hashlib
import json
import logging
import ntpath
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .settings import LOGGER_NAME

log = logging.getLogger(LOGGER_NAME)

REPOSITORY = "Bulls64/CloseAllPython"
PROJECT_PAGE = f"https://github.com/{REPOSITORY}"   # shown in Settings › About
LATEST_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"
GUI_ASSET, CLI_ASSET = "CloseAllPython.exe", "CloseAllPython-CLI.exe"
API_TIMEOUT, DOWNLOAD_TIMEOUT = 10, 60
CHUNK = 256 * 1024
MAX_SIZE = 200 * 1024 * 1024
OLD_SUFFIX, NEW_SUFFIX, PART_SUFFIX = ".old", ".new", ".part"


class UpdateError(Exception):
    """`key` is an i18n key (update_err_*); `values` fill its placeholders."""

    def __init__(self, key, **values):
        super().__init__(key, values)
        self.key, self.values = key, values


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int
    sha256: str | None


@dataclass
class Release:
    tag: str
    version: tuple
    page: str
    assets: dict = field(default_factory=dict)   # lower-case name -> Asset

    @property
    def label(self):
        return ".".join(map(str, self.version))


def is_project_url(url, section):
    """True only for https://github.com/Bulls64/CloseAllPython/<section>/... with a clean path.

    The release data comes from the network: a download or a page address is accepted only when
    it points to this repository on github.com. No user name, port, query, backslash, encoded
    character or "." / ".." segment (which would let ".../releases/download/../../other/repo"
    reach another repository).
    """
    if not isinstance(url, str):
        return False
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or parts.netloc.lower() != "github.com" or port is not None:
        return False
    if parts.query or parts.fragment or "\\" in url or "%" in parts.path:
        return False
    segments = parts.path.split("/")[1:]
    if any(segment in ("", ".", "..") for segment in segments):
        return False
    owner, repository = REPOSITORY.lower().split("/")
    expected = [owner, repository, *section.lower().split("/")]
    # GitHub ignores the case of owner and repository names; something must follow the section.
    return len(segments) > len(expected) and [s.lower() for s in segments[:len(expected)]] == expected


def release_page(url):
    """`url` when it is a page of this repository's releases, else the latest-release page."""
    return url if is_project_url(url, "releases") else RELEASES_PAGE


def parse_version(text):
    """'v1.6.0' / '1.6' -> (1, 6, 0) / (1, 6); None when it is not a plain version number."""
    match = re.fullmatch(r"v?(\d+(?:\.\d+){0,3})", (text or "").strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def _padded(version):
    return tuple(version) + (0,) * (4 - len(version))


def is_newer(release, current=__version__):
    return _padded(release.version) > _padded(parse_version(current) or (0,))


def _request(url, accept):
    return urllib.request.Request(url, headers={"Accept": accept, "User-Agent": f"CloseAllPython/{__version__}"})


def _connection_error(exc, clock=time.time):
    """The UpdateError for a failed request: GitHub's request limit and HTTP errors are named."""
    if isinstance(exc, urllib.error.HTTPError):
        headers = exc.headers or {}
        if exc.code == 429 or (exc.code == 403 and headers.get("X-RateLimit-Remaining") == "0"):
            # Without a token GitHub allows 60 API requests an hour per IP address: an office
            # sharing one address can use them up. Say when it resets instead of "unreachable".
            try:
                if headers.get("X-RateLimit-Reset"):
                    reset = float(headers["X-RateLimit-Reset"])
                else:
                    reset = clock() + float(headers.get("Retry-After"))
            except (TypeError, ValueError):
                reset = None
            if reset and reset > clock():
                return UpdateError("update_err_rate_limit", time=time.strftime("%H:%M", time.localtime(reset)))
            return UpdateError("update_err_rate_limit_soon")
        return UpdateError("update_err_http", code=exc.code)
    return UpdateError("update_err_network", detail=getattr(exc, "reason", exc))


def fetch_latest(opener=urllib.request.urlopen):
    """The latest published release (GitHub's /latest skips drafts and pre-releases)."""
    try:
        with opener(_request(LATEST_API, "application/vnd.github+json"), timeout=API_TIMEOUT) as response:
            data = json.loads(response.read(2_000_000).decode("utf-8"))
    except (urllib.error.URLError, OSError) as exc:
        raise _connection_error(exc) from exc
    except ValueError as exc:
        raise UpdateError("update_err_response") from exc
    try:
        version = parse_version(data["tag_name"])
        if version is None:
            raise ValueError(data["tag_name"])
        assets = {}
        for item in data.get("assets") or ():
            digest = item.get("digest") or ""
            assets[item["name"].lower()] = Asset(
                item["name"], item["browser_download_url"], int(item["size"]),
                digest[7:].lower() if digest.startswith("sha256:") else None)
        return Release(data["tag_name"], version, release_page(data.get("html_url")), assets)
    except (KeyError, TypeError, ValueError) as exc:
        raise UpdateError("update_err_response") from exc


def current_executable():
    """Path of the running executable, or None when running from source."""
    return Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None


def asset_for(release, exe_path):
    """The release file that replaces `exe_path` (same name; a renamed copy is matched by kind)."""
    name = ntpath.basename(str(exe_path)).lower()
    asset = release.assets.get(name)
    if asset is None:
        asset = release.assets.get((CLI_ASSET if "cli" in name else GUI_ASSET).lower())
    if asset is None:
        raise UpdateError("update_err_no_asset", name=ntpath.basename(str(exe_path)))
    if not asset.sha256:
        raise UpdateError("update_err_unverifiable", name=asset.name)
    if not is_project_url(asset.url, "releases/download") or not 0 < asset.size <= MAX_SIZE:
        raise UpdateError("update_err_response")
    return asset


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def download(asset, destination, opener=urllib.request.urlopen, progress=None):
    """Download `asset` to `destination`, checking its size, SHA-256 digest and executable header.
    `progress(done, total)` is called from this thread. Nothing is left behind on failure."""
    destination = Path(destination)
    part = destination.with_name(destination.name + PART_SUFFIX)
    digest, done = hashlib.sha256(), 0
    try:
        with opener(_request(asset.url, "application/octet-stream"), timeout=DOWNLOAD_TIMEOUT) as response, \
                open(part, "wb") as handle:
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                done += len(chunk)
                if done > asset.size:
                    raise UpdateError("update_err_verify")
                if done == len(chunk) and not chunk.startswith(b"MZ"):
                    raise UpdateError("update_err_verify")
                digest.update(chunk)
                handle.write(chunk)
                if progress:
                    progress(done, asset.size)
    except UpdateError:
        _remove(part)
        raise
    except PermissionError as exc:
        _remove(part)
        raise UpdateError("update_err_write", detail=exc.strerror or exc) from exc
    except (urllib.error.URLError, OSError) as exc:
        _remove(part)
        raise _connection_error(exc) from exc
    if done != asset.size or digest.hexdigest() != asset.sha256:
        _remove(part)
        raise UpdateError("update_err_verify")
    os.replace(part, destination)
    return destination


def _free_old_name(exe_path):
    """`<name>.old`, or `<name>.old2`... when an earlier copy is still held by a closing instance."""
    for index in range(1, 10):
        old = exe_path.with_name(exe_path.name + OLD_SUFFIX + (str(index) if index > 1 else ""))
        try:
            _remove(old)
            return old
        except OSError:
            continue
    raise PermissionError(13, "no free name for the previous version")


def install(new_file, exe_path):
    """Swap `new_file` in place of `exe_path` (which may be running); restores it on failure."""
    exe_path = Path(exe_path)
    try:
        old = _free_old_name(exe_path)
        os.replace(exe_path, old)
    except OSError as exc:
        _remove(new_file)
        raise UpdateError("update_err_write", detail=exc.strerror or exc) from exc
    try:
        os.replace(new_file, exe_path)
    except OSError as exc:
        os.replace(old, exe_path)
        _remove(new_file)
        raise UpdateError("update_err_write", detail=exc.strerror or exc) from exc
    return exe_path


def update(exe_path, release, opener=urllib.request.urlopen, progress=None):
    """Download and install the release's executable over `exe_path`."""
    exe_path = Path(exe_path)
    asset = asset_for(release, exe_path)
    new_file = exe_path.with_name(exe_path.name + NEW_SUFFIX)
    download(asset, new_file, opener, progress)
    install(new_file, exe_path)
    log.info("updated to %s from %s exe=%s", release.tag, __version__, exe_path)
    return exe_path


def cleanup(exe_path=None):
    """Remove what an earlier update left next to the executable (the replaced file, a partial
    download). Silent: the previous instance may still be closing and holding the old file."""
    exe_path = exe_path or current_executable()
    if exe_path is None:
        return
    exe_path = Path(exe_path)
    names = [exe_path.name + NEW_SUFFIX, exe_path.name + NEW_SUFFIX + PART_SUFFIX,
             exe_path.name + OLD_SUFFIX] + [f"{exe_path.name}{OLD_SUFFIX}{index}" for index in range(2, 10)]
    for name in names:
        try:
            _remove(exe_path.with_name(name))
        except OSError:
            pass


def relaunch(exe_path, args=()):
    """Start the (updated) executable as a fresh, independent PyInstaller process."""
    env = dict(os.environ)
    # PyInstaller 6.9+: without this, a onefile child reuses its parent's temporary folder.
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen([str(exe_path), *args], env=env, close_fds=True)  # noqa: S603 - our own executable
