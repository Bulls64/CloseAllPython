"""In-memory stand-in for closeall.winapi so the logic can be tested on any OS."""
import ntpath
import os
import sys
import types
from collections import namedtuple

SystemProcess = namedtuple("SystemProcess", "pid ppid name created private_memory working_set session",
                           defaults=(1,))


class FakeWinError(OSError):
    def __init__(self, code):
        super().__init__(code, f"winerror {code}")
        self.winerror = code


class FakeSystem:
    def __init__(self):
        self.processes = {}
        self.windows = []
        self.uwp = {}
        self.posted = []
        self.terminated = []
        self.shown = []
        self.console = 0
        self.calls = []   # ("terminate" | "wait", pid), in call order

    def add_process(self, pid, path, created=1000, ppid=0, exits_on_close=True, deny=False, memory=0, name=None,
                    session=1):
        self.processes[pid] = {"path": path, "created": created, "ppid": ppid, "alive": True,
                               "exits_on_close": exits_on_close, "deny": deny, "memory": memory,
                               "name": name if name is not None else ntpath.basename(path or ""),
                               "session": session}

    def add_window(self, hwnd, pid, title, task=True, cls="", visible=True):
        self.windows.append({"hwnd": hwnd, "pid": pid, "title": title, "task": task, "cls": cls, "visible": visible})

    def start_explorer(self):
        self.calls.append(("start_explorer", None))
        pid = 9000 + len(self.calls)
        self.add_process(pid, r"C:\Windows\explorer.exe", created=pid)

    def _window(self, hwnd):
        return next((w for w in self.windows if w["hwnd"] == hwnd), None)

    def module(self):
        system = self
        mod = types.ModuleType("closeall.winapi")
        mod.PROCESS_TERMINATE = 0x1
        mod.PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        mod.SYNCHRONIZE = 0x100000
        mod.ERROR_ACCESS_DENIED = 5
        mod.ERROR_INVALID_PARAMETER = 87
        mod.UWP_FRAME_HOST = "applicationframehost.exe"

        def open_process(pid, access):
            proc = system.processes.get(pid)
            if proc is None or not proc["alive"]:
                raise FakeWinError(87)
            if proc["deny"]:
                raise FakeWinError(5)
            return ("handle", pid)

        def process_info(pid):
            proc = system.processes.get(pid)
            if proc is None or proc["deny"]:
                return None, 0
            return proc["path"], proc["created"]

        def terminate(handle, exit_code=1):
            system.processes[handle[1]]["alive"] = False
            system.terminated.append((handle[1], exit_code))
            system.calls.append(("terminate", handle[1]))

        def wait(handle, ms):
            system.calls.append(("wait", handle[1]))
            return not system.processes[handle[1]]["alive"]

        def top_level_windows():
            # The windows of a process that has exited are gone too.
            return [w["hwnd"] for w in system.windows
                    if system.processes.get(w["pid"], {"alive": True})["alive"]]

        def post_close(hwnd):
            system.posted.append(hwnd)
            window = system._window(hwnd)
            if window:
                proc = system.processes.get(system.uwp.get(hwnd, window["pid"]))
                if proc and proc["exits_on_close"]:
                    proc["alive"] = False
            return True

        mod.open_process = open_process
        mod.close_handle = lambda handle: None
        mod.creation_time = lambda handle: system.processes[handle[1]]["created"]
        mod.wait = wait
        mod.terminate = terminate
        mod.process_info = process_info
        mod.process_table = lambda: {pid: (p["ppid"], os.path.basename(p["path"] or "")) for pid, p in system.processes.items()}
        mod.system_processes = lambda: [SystemProcess(pid, p["ppid"], p["name"], p["created"], p["memory"], p["memory"],
                                                      p["session"])
                                        for pid, p in system.processes.items() if p["alive"]]
        mod.current_session = lambda: 1
        mod.start_explorer = system.start_explorer
        mod.console_window = lambda: system.console
        mod.top_level_windows = top_level_windows
        mod.is_task_window = lambda hwnd: system._window(hwnd)["task"]
        mod.window_title = lambda hwnd: system._window(hwnd)["title"]
        mod.window_pid = lambda hwnd: system._window(hwnd)["pid"] if system._window(hwnd) else 0
        mod.uwp_app_pid = lambda hwnd, frame_pid: system.uwp.get(hwnd, 0)
        mod.post_close = post_close
        mod.window_class = lambda hwnd: system._window(hwnd)["cls"]
        mod.is_window_visible = lambda hwnd: system._window(hwnd)["visible"]
        mod.bring_to_front = lambda hwnd: system.shown.append(hwnd) or True
        return mod


_current = FakeSystem()
sys.modules["closeall.winapi"] = _current.module()


def install(system):
    """Point the already-imported fake module at a fresh FakeSystem."""
    import closeall
    module = system.module()
    sys.modules["closeall.winapi"] = module
    closeall.winapi = module
    import closeall.core as core
    core.winapi = module
    return system
