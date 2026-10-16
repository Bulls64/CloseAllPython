"""Window discovery and application shutdown. All OS access goes through `winapi`."""
import logging
import ntpath
import os
import time
from dataclasses import dataclass, field

from . import winapi
from .settings import LOGGER_NAME

log = logging.getLogger(LOGGER_NAME)

# Processes that keep Windows usable. Their windows are listed but can never be closed.
PROTECTED_EXECUTABLES = frozenset({
    "applicationframehost.exe", "csrss.exe", "ctfmon.exe", "dwm.exe", "explorer.exe",
    "fontdrvhost.exe", "lockapp.exe", "logonui.exe", "lsass.exe", "runtimebroker.exe",
    "searchapp.exe", "searchhost.exe", "searchui.exe", "services.exe", "shellexperiencehost.exe",
    "shellhost.exe", "sihost.exe", "smss.exe", "startmenuexperiencehost.exe", "svchost.exe",
    "taskhostw.exe", "textinputhost.exe", "wininit.exe", "winlogon.exe",
})
SYSTEM_PIDS = frozenset({0, 4})
EXPLORER_WINDOW_CLASSES = frozenset({"cabinetwclass", "exploremwclass"})

CLOSED, FORCED, STILL_RUNNING, FAILED, PROTECTED = "closed", "forced", "still_running", "failed", "protected"
FORCE_WAIT_MS = 3000


def _exe_name(path):
    return ntpath.basename(path).lower() if path else ""


def _is_protected(pid, exe_path):
    return pid in SYSTEM_PIDS or _exe_name(exe_path) in PROTECTED_EXECUTABLES


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    hwnd_pid: int      # process owning the HWND (ApplicationFrameHost for UWP apps)
    pid: int           # process to close
    created: int       # creation time of `pid`: detects PID reuse before acting
    title: str
    exe_path: str | None

    @property
    def key(self):
        return self.pid, self.created

    @property
    def app_name(self):
        return ntpath.splitext(ntpath.basename(self.exe_path))[0] if self.exe_path else ""

    @property
    def protected(self):
        return _is_protected(self.pid, self.exe_path)


@dataclass
class Target:
    pid: int
    created: int
    exe_path: str | None
    titles: list = field(default_factory=list)
    hwnds: list = field(default_factory=list)

    @property
    def key(self):
        return self.pid, self.created

    @property
    def app_name(self):
        return ntpath.splitext(ntpath.basename(self.exe_path))[0] if self.exe_path else ""

    @property
    def protected(self):
        return _is_protected(self.pid, self.exe_path)


@dataclass
class Result:
    target: Target
    status: str
    error_key: str | None = None
    detail: str = ""
    elapsed: float = 0.0   # seconds between the close request and the outcome


class ProcessError(Exception):
    def __init__(self, key, detail=""):
        super().__init__(key, detail)
        self.key, self.detail = key, detail


def _classify(exc):
    code = getattr(exc, "winerror", None)
    if code == winapi.ERROR_ACCESS_DENIED:
        return ProcessError("access_denied")
    if code == winapi.ERROR_INVALID_PARAMETER:
        return ProcessError("process_gone")
    return ProcessError("os_error", str(exc))


# --------------------------------------------------------------------------- discovery

def own_pids(include_ancestors):
    """PIDs that must never be closed by this program.

    Always: this process, plus the PyInstaller one-file bootloader that started it.
    With `include_ancestors` (command line): every parent process (shell, terminal...)
    and the console window owner, so the CLI never kills the terminal running it.
    """
    me = os.getpid()
    pids = {me}
    table = winapi.process_table()
    if include_ancestors:
        pid, seen = me, set()
        while pid in table and pid not in seen and len(seen) < 64:
            seen.add(pid)
            parent = table[pid][0]
            if not parent:
                break
            pids.add(parent)
            pid = parent
        console = winapi.console_window()
        if console:
            pids.add(winapi.window_pid(console))
    else:
        parent = table.get(me, (0, ""))[0]
        if parent and table.get(parent, (0, ""))[1].lower() == table.get(me, (0, ""))[1].lower():
            pids.add(parent)
    pids.discard(0)
    return frozenset(pids)


def list_windows(exclude_pids=frozenset()):
    """Return the windows a user would see in Alt+Tab, with their real owning process."""
    cache = {}

    def info(pid):
        if pid not in cache:
            cache[pid] = winapi.process_info(pid)
        return cache[pid]

    windows = []
    for hwnd in winapi.top_level_windows():
        if not winapi.is_task_window(hwnd):
            continue
        title = winapi.window_title(hwnd).strip()
        hwnd_pid = winapi.window_pid(hwnd)
        if not title or not hwnd_pid:
            continue
        pid = hwnd_pid
        path, created = info(pid)
        if _exe_name(path) == winapi.UWP_FRAME_HOST:
            app_pid = winapi.uwp_app_pid(hwnd, hwnd_pid)
            if app_pid:
                pid = app_pid
                path, created = info(pid)
        if pid in exclude_pids or hwnd_pid in exclude_pids:
            continue
        windows.append(WindowInfo(hwnd, hwnd_pid, pid, created, title, path))
    return windows


def filter_by_title(windows, pattern):
    needle = (pattern or "").strip().casefold()
    if not needle:
        raise ValueError("empty pattern")
    return [w for w in windows if needle in w.title.casefold()]


def group_targets(windows):
    """One target per process, keeping the titles of its selected windows."""
    targets = {}
    for w in windows:
        target = targets.setdefault(w.key, Target(w.pid, w.created, w.exe_path))
        target.titles.append(w.title)
        target.hwnds.append(w.hwnd)
    return sorted(targets.values(), key=lambda t: (t.app_name.casefold(), t.pid))


def truncate(items, limit):
    """Return (first `limit` items, number left out)."""
    items = list(items)
    return items[:limit], max(0, len(items) - limit)


# --------------------------------------------------------------------------- shutdown

def _open_verified(target, access):
    """Open the target process, making sure the PID still designates the same process."""
    if not target.created:
        # Without a creation time the PID cannot be verified: refuse rather than guess.
        raise ProcessError("access_denied")
    try:
        handle = winapi.open_process(target.pid, access | winapi.PROCESS_QUERY_LIMITED_INFORMATION
                                     | winapi.SYNCHRONIZE)
    except OSError as exc:
        raise _classify(exc) from exc
    try:
        if winapi.creation_time(handle) != target.created:
            raise ProcessError("process_changed")
        if winapi.wait(handle, 0):
            raise ProcessError("process_gone")
    except OSError as exc:
        winapi.close_handle(handle)
        raise _classify(exc) from exc
    except ProcessError:
        winapi.close_handle(handle)
        raise
    return handle


def _error_result(target, error):
    # A process that is already gone is exactly what the user asked for.
    if error.key == "process_gone":
        return Result(target, CLOSED)
    return Result(target, FAILED, error.key, error.detail)


def _log(result):
    t = result.target
    log.info("%s pid=%s exe=%s titles=%r%s", result.status, t.pid, t.exe_path, t.titles,
             f" error={result.error_key} {result.detail}".rstrip() if result.error_key else "")
    return result


def force_stop(target):
    """Force-stop one target (waits up to FORCE_WAIT_MS for it to disappear)."""
    return force_processes([target])[0]


def force_processes(targets, on_result=None):
    """Force-stop every target immediately; `on_result` gets each Result as soon as it is known.

    Every process is terminated first, then all of them are awaited against one shared deadline:
    N applications slow to die cost FORCE_WAIT_MS in total, not N times FORCE_WAIT_MS.
    """
    results, stopping, start = [], [], time.monotonic()

    def report(result):
        result.elapsed = time.monotonic() - start
        _log(result)
        results.append(result)
        if on_result:
            on_result(result)

    for target in targets:
        if target.protected:
            report(Result(target, PROTECTED))
            continue
        try:
            handle = _open_verified(target, winapi.PROCESS_TERMINATE)
        except ProcessError as error:
            report(_error_result(target, error))
            continue
        try:
            winapi.terminate(handle, 1)
        except OSError as exc:
            winapi.close_handle(handle)
            report(_error_result(target, _classify(exc)))
            continue
        stopping.append((target, handle))
    deadline = start + FORCE_WAIT_MS / 1000
    for target, handle in stopping:
        try:
            winapi.wait(handle, max(0, int((deadline - time.monotonic()) * 1000)))
        except OSError:
            pass
        finally:
            winapi.close_handle(handle)
        report(Result(target, FORCED))
    return results


def explorer_windows():
    """HWNDs of File Explorer folder windows (not the desktop, taskbar or other shell windows)."""
    hwnds = []
    for hwnd in winapi.top_level_windows():
        if winapi.window_class(hwnd).casefold() not in EXPLORER_WINDOW_CLASSES:
            continue
        if not winapi.is_window_visible(hwnd):
            continue
        path, _ = winapi.process_info(winapi.window_pid(hwnd))
        if _exe_name(path) == "explorer.exe":
            hwnds.append(hwnd)
    return hwnds


def close_explorer_windows():
    """Close every File Explorer window (all its tabs) without touching explorer.exe itself,
    so the desktop, taskbar and Start menu keep running. Returns the number of windows closed."""
    hwnds = explorer_windows()
    closed = sum(1 for hwnd in hwnds if winapi.post_close(hwnd))
    log.info("explorer_windows_closed count=%s", closed)
    return closed


def windows_of(target):
    """Current top-level windows of a target (fresh list: HWNDs change over time)."""
    return [w.hwnd for w in list_windows() if w.key == target.key]


def close_processes(targets, timeout, force=False, on_result=None, sleep=None, clock=time.monotonic):
    """Ask each application to close (WM_CLOSE on all its windows), wait up to `timeout`
    seconds, then force-stop the survivors when `force` is set.

    Survivors are otherwise reported as STILL_RUNNING so the caller can decide.
    `on_result` is called with each Result as soon as it is known (from this thread).
    Without `sleep` (tests pass a fake one), the wait sleeps on a survivor's process handle:
    the kernel wakes it the moment that process exits, with no polling delay.
    """
    results, opened = [], []
    start = clock()

    def add(result):
        result.elapsed = clock() - start
        results.append(result)
        if on_result:
            on_result(result)

    for target in targets:
        if target.protected:
            add(_log(Result(target, PROTECTED)))
            continue
        try:
            opened.append((target, _open_verified(target, 0)))
        except ProcessError as error:
            add(_log(_error_result(target, error)))
    try:
        if not opened:
            return results
        # Fresh window list: HWNDs may have changed since the user made the selection.
        hwnds = {}
        for w in list_windows():
            hwnds.setdefault(w.key, []).append(w.hwnd)
        for target, _ in opened:
            for hwnd in hwnds.get(target.key, []):
                winapi.post_close(hwnd)
        deadline = start + max(0, timeout)
        pending = opened
        while True:
            still = []
            for target, handle in pending:
                try:
                    exited = winapi.wait(handle, 0)
                except OSError as exc:
                    add(_log(_error_result(target, _classify(exc))))
                    continue
                if exited:
                    add(_log(Result(target, CLOSED)))
                else:
                    still.append((target, handle))
            pending = still
            remaining = deadline - clock()
            if not pending or remaining <= 0:
                break
            if sleep is not None:
                sleep(min(0.1, remaining))
            else:
                try:
                    winapi.wait(pending[0][1], int(min(0.1, remaining) * 1000) + 1)
                except OSError:
                    time.sleep(min(0.1, remaining))
        if force:
            for result in force_processes([target for target, _ in pending]):
                add(result)
        else:
            for target, _ in pending:
                add(_log(Result(target, STILL_RUNNING)))
    finally:
        for _, handle in opened:
            winapi.close_handle(handle)
    return results


def summarize(results):
    counts = {CLOSED: 0, FORCED: 0, STILL_RUNNING: 0, FAILED: 0, PROTECTED: 0}
    for result in results:
        counts[result.status] += 1
    return counts
