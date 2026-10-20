"""Thin Win32 layer. Every call into the operating system goes through this module.

Process functions use ctypes so access rights, return values and error codes are
explicit. Window enumeration uses pywin32.
"""
import ctypes
import os
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass

import win32gui
import win32process

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")
try:
    dwmapi = ctypes.WinDLL("dwmapi")
except OSError:  # pragma: no cover - DWM is always present on supported Windows versions
    dwmapi = None

# Process access rights and status codes
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0x0
WAIT_TIMEOUT = 0x102
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_PARAMETER = 87
ERROR_INSUFFICIENT_BUFFER = 122
TH32CS_SNAPPROCESS = 0x2
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# Window messages and styles
WM_CLOSE = 0x0010
WM_SETICON = 0x0080
ICON_SMALL, ICON_BIG = 0, 1
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x00000080, 0x00040000
GW_OWNER = 4
SW_RESTORE = 9
DWMWA_CLOAKED = 14
DI_NORMAL = 0x3
UWP_FRAME_HOST = "applicationframehost.exe"
UWP_CORE_WINDOW = "Windows.UI.Core.CoreWindow"


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", ctypes.c_void_p)]


class SYSTEM_PROCESS_INFORMATION(ctypes.Structure):
    """Leading part of the record NtQuerySystemInformation returns per process (winternl.h)."""
    _fields_ = [
        ("NextEntryOffset", wintypes.ULONG),
        ("NumberOfThreads", wintypes.ULONG),
        ("WorkingSetPrivateSize", ctypes.c_longlong),
        ("HardFaultCount", wintypes.ULONG),
        ("NumberOfThreadsHighWatermark", wintypes.ULONG),
        ("CycleTime", ctypes.c_ulonglong),
        ("CreateTime", ctypes.c_longlong),
        ("UserTime", ctypes.c_longlong),
        ("KernelTime", ctypes.c_longlong),
        ("ImageName", UNICODE_STRING),
        ("BasePriority", ctypes.c_long),
        ("UniqueProcessId", ctypes.c_void_p),
        ("InheritedFromUniqueProcessId", ctypes.c_void_p),
        ("HandleCount", wintypes.ULONG),
        ("SessionId", wintypes.ULONG),
        ("UniqueProcessKey", ctypes.c_size_t),
        ("PeakVirtualSize", ctypes.c_size_t),
        ("VirtualSize", ctypes.c_size_t),
        ("PageFaultCount", wintypes.ULONG),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivatePageCount", ctypes.c_size_t),
    ]


@dataclass(frozen=True)
class SystemProcess:
    pid: int
    ppid: int
    name: str            # image name ("OneDrive.exe"); "" for the idle process
    created: int         # same FILETIME value as creation_time()
    private_memory: int  # private working set in bytes (the Task Manager's "Memory" column)
    working_set: int
    session: int = 0     # Windows session (each signed-in user has their own)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                ("hbmMask", wintypes.HBITMAP), ("hbmColor", wintypes.HBITMAP)]


def _proto(func, restype, *argtypes):
    func.restype = restype
    func.argtypes = list(argtypes)


_proto(kernel32.OpenProcess, wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_proto(kernel32.CloseHandle, wintypes.BOOL, wintypes.HANDLE)
_proto(kernel32.TerminateProcess, wintypes.BOOL, wintypes.HANDLE, wintypes.UINT)
_proto(kernel32.WaitForSingleObject, wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD)
_proto(kernel32.GetProcessTimes, wintypes.BOOL, wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4))
_proto(kernel32.QueryFullProcessImageNameW, wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD,
       wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
_proto(kernel32.CreateToolhelp32Snapshot, wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD)
_proto(kernel32.Process32FirstW, wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
_proto(kernel32.Process32NextW, wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
_proto(ntdll.NtQuerySystemInformation, ctypes.c_ulong, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG,
       ctypes.POINTER(wintypes.ULONG))
_proto(kernel32.GetConsoleWindow, wintypes.HWND)
_proto(kernel32.ProcessIdToSessionId, wintypes.BOOL, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
_proto(user32.InternalGetWindowText, ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_proto(user32.GetDC, wintypes.HDC, wintypes.HWND)
_proto(user32.ReleaseDC, ctypes.c_int, wintypes.HWND, wintypes.HDC)
_proto(user32.DrawIconEx, wintypes.BOOL, wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON,
       ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT)
_proto(gdi32.CreateCompatibleDC, wintypes.HDC, wintypes.HDC)
_proto(gdi32.CreateDIBSection, wintypes.HBITMAP, wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
       ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
_proto(gdi32.SelectObject, wintypes.HGDIOBJ, wintypes.HDC, wintypes.HGDIOBJ)
_proto(gdi32.DeleteObject, wintypes.BOOL, wintypes.HGDIOBJ)
_proto(gdi32.DeleteDC, wintypes.BOOL, wintypes.HDC)
_proto(gdi32.CreateBitmap, wintypes.HBITMAP, ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.UINT, ctypes.c_void_p)
_proto(user32.CreateIconIndirect, wintypes.HICON, ctypes.POINTER(ICONINFO))
_proto(user32.DestroyIcon, wintypes.BOOL, wintypes.HICON)
_proto(user32.SendMessageW, wintypes.LPARAM, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_proto(shell32.ShellExecuteW, wintypes.HINSTANCE, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
       wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int)


def _last_error():
    return ctypes.WinError(ctypes.get_last_error())


# --------------------------------------------------------------------------- processes

def open_process(pid, access):
    """Return a raw process handle or raise OSError (winerror 5 = denied, 87 = no such process)."""
    handle = kernel32.OpenProcess(access, False, pid)
    if not handle:
        raise _last_error()
    return handle


def close_handle(handle):
    if handle:
        kernel32.CloseHandle(handle)


def image_path(handle):
    # Almost every path fits in 1024 characters; long paths (up to 32 767) get a second try.
    for length in (1024, 32768):
        size = wintypes.DWORD(length)
        buffer = ctypes.create_unicode_buffer(length)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value[:size.value]
        error = ctypes.get_last_error()
        if error != ERROR_INSUFFICIENT_BUFFER:
            break
    raise ctypes.WinError(error)


def creation_time(handle):
    times = [wintypes.FILETIME() for _ in range(4)]
    if not kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
        raise _last_error()
    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime


def wait(handle, milliseconds):
    """Return True when the process has exited, False on timeout."""
    result = kernel32.WaitForSingleObject(handle, milliseconds)
    if result == WAIT_OBJECT_0:
        return True
    if result == WAIT_TIMEOUT:
        return False
    raise _last_error()


def terminate(handle, exit_code=1):
    if not kernel32.TerminateProcess(handle, exit_code):
        raise _last_error()


def process_info(pid):
    """Return (executable path or None, creation time or 0) using the least privileged access."""
    try:
        handle = open_process(pid, PROCESS_QUERY_LIMITED_INFORMATION)
    except OSError:
        return None, 0
    try:
        try:
            path = image_path(handle)
        except OSError:
            path = None
        try:
            created = creation_time(handle)
        except OSError:
            created = 0
        return path, created
    finally:
        close_handle(handle)


def file_description(path):
    """FileDescription of an executable's version resource ("Visual Studio Code"), or None."""
    import win32api

    try:
        translations = win32api.GetFileVersionInfo(path, "\\VarFileInfo\\Translation") or []
    except win32api.error:
        return None
    for language, codepage in translations:
        try:
            value = win32api.GetFileVersionInfo(
                path, f"\\StringFileInfo\\{language:04x}{codepage:04x}\\FileDescription")
        except win32api.error:
            continue
        if value and value.strip():
            return value.strip()
    return None


def process_table():
    """Return {pid: (parent pid, executable name)} for every running process."""
    table = {}
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        return table
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            table[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        close_handle(snapshot)
    return table


SYSTEM_PROCESS_INFORMATION_CLASS = 5
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004


def system_processes():
    """Every running process with its memory use, read in one call that needs no access to the
    processes themselves (so it also covers services and other users' processes)."""
    size = 512 * 1024
    for _ in range(8):   # the list can grow between the size query and the read
        buffer = ctypes.create_string_buffer(size)
        needed = wintypes.ULONG(0)
        status = ntdll.NtQuerySystemInformation(SYSTEM_PROCESS_INFORMATION_CLASS, buffer, size, ctypes.byref(needed))
        if status == STATUS_INFO_LENGTH_MISMATCH:
            size = max(size * 2, needed.value + 64 * 1024)
            continue
        if status:
            raise OSError(f"NtQuerySystemInformation failed (status 0x{status:08X})")
        break
    else:
        raise OSError("the process list keeps growing")
    processes, offset = [], 0
    while True:
        info = SYSTEM_PROCESS_INFORMATION.from_buffer(buffer, offset)
        image = info.ImageName
        name = ctypes.wstring_at(image.Buffer, image.Length // 2) if image.Buffer and image.Length else ""
        processes.append(SystemProcess(info.UniqueProcessId or 0, info.InheritedFromUniqueProcessId or 0, name,
                                       info.CreateTime, max(0, info.WorkingSetPrivateSize), info.WorkingSetSize,
                                       info.SessionId))
        if not info.NextEntryOffset:
            return processes
        offset += info.NextEntryOffset


def current_session():
    """Windows session of this process."""
    session = wintypes.DWORD(0)
    if not kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
        raise _last_error()
    return session.value


def start_explorer():
    """Start the Windows shell (desktop, taskbar, Start menu)."""
    windows = os.environ.get("SystemRoot") or r"C:\Windows"
    subprocess.Popen([os.path.join(windows, "explorer.exe")], close_fds=True)  # noqa: S603 - fixed system path


def console_window():
    return kernel32.GetConsoleWindow() or 0


def is_admin():
    try:
        return bool(shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def relaunch_as_admin():
    """Start this program again with a UAC prompt. Return True if Windows accepted the request."""
    if getattr(sys, "frozen", False):
        executable, params = sys.executable, ""
    else:
        executable = sys.executable
        windowed = os.path.join(os.path.dirname(executable), "pythonw.exe")
        if os.path.exists(windowed):
            executable = windowed
        params = subprocess.list2cmdline([os.path.abspath(sys.argv[0])])
    result = shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
    return (result or 0) > 32


# --------------------------------------------------------------------------- windows

def top_level_windows():
    handles = []

    def collect(hwnd, _):
        handles.append(hwnd)
        return True

    win32gui.EnumWindows(collect, None)
    return handles


def window_title(hwnd):
    """Title of a window. InternalGetWindowText sends no message to the window, so a frozen
    application cannot stall the listing, and needs a single call."""
    buffer = ctypes.create_unicode_buffer(512)
    copied = user32.InternalGetWindowText(hwnd, buffer, len(buffer))
    return buffer.value[:max(0, copied)]


def is_window_visible(hwnd):
    try:
        return bool(win32gui.IsWindowVisible(hwnd))
    except win32gui.error:
        return False


def window_class(hwnd):
    try:
        return win32gui.GetClassName(hwnd)
    except win32gui.error:
        return ""


def window_pid(hwnd):
    try:
        return win32process.GetWindowThreadProcessId(hwnd)[1]
    except win32gui.error:
        return 0


def is_cloaked(hwnd):
    """Cloaked windows are 'visible' but not shown (suspended UWP apps, other desktops...)."""
    if dwmapi is None:
        return False
    value = wintypes.DWORD()
    result = dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), wintypes.DWORD(DWMWA_CLOAKED),
                                          ctypes.byref(value), ctypes.sizeof(value))
    return result == 0 and value.value != 0


def is_task_window(hwnd):
    """Approximate the windows shown in Alt+Tab / the taskbar."""
    try:
        if not win32gui.IsWindowVisible(hwnd):
            return False
        ex_style = win32gui.GetWindowLong(hwnd, GWL_EXSTYLE)
        app_window = bool(ex_style & WS_EX_APPWINDOW)
        if ex_style & WS_EX_TOOLWINDOW and not app_window:
            return False
        owner = win32gui.GetWindow(hwnd, GW_OWNER)
        # Owned windows (dialogs, palettes) are skipped unless their owner is hidden,
        # which is how some frameworks implement their main window.
        if owner and not app_window and win32gui.IsWindowVisible(owner):
            return False
    except win32gui.error:
        return False
    return not is_cloaked(hwnd)


def uwp_app_pid(frame_hwnd, frame_pid):
    """Return the real process of a UWP app hosted by ApplicationFrameHost, or 0."""
    found = []

    def collect(child, _):
        try:
            if win32gui.GetClassName(child) == UWP_CORE_WINDOW:
                pid = window_pid(child)
                if pid and pid != frame_pid:
                    found.append(pid)
        except win32gui.error:
            pass
        return True

    try:
        win32gui.EnumChildWindows(frame_hwnd, collect, None)
    except win32gui.error:
        pass
    return found[0] if found else 0


def bring_to_front(hwnd):
    """Restore a window if minimized and give it the focus (works while we are the foreground app)."""
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return True
    except win32gui.error:
        return False


def post_close(hwnd):
    """Ask a window to close, exactly like its title-bar X button."""
    try:
        win32gui.PostMessage(hwnd, WM_CLOSE, 0, 0)
        return True
    except win32gui.error:
        return False


# --------------------------------------------------------------------------- icons

def _bitmap_info(width, height):
    """32-bit top-down DIB header."""
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height  # top-down rows
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    return info


def _draw_icon(hicon, size, background):
    """Draw an icon on a solid background and return the raw BGRA pixels."""
    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    info = _bitmap_info(size, size)
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(memory, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
    old = None
    try:
        if not bitmap or not bits.value:
            return None
        old = gdi32.SelectObject(memory, bitmap)
        ctypes.memset(bits, background, size * size * 4)
        if not user32.DrawIconEx(memory, 0, 0, hicon, size, size, 0, None, DI_NORMAL):
            return None
        return ctypes.string_at(bits, size * size * 4)
    finally:
        if old:
            gdi32.SelectObject(memory, old)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)


def render_icon(hicon, size):
    """Render an HICON as an RGBA Pillow image, keeping its transparency.

    The icon is drawn on black and on white: the difference between both renders gives
    the alpha channel, whatever the icon format (alpha, mask or palette).
    """
    from PIL import Image

    on_black = _draw_icon(hicon, size, 0x00)
    on_white = _draw_icon(hicon, size, 0xFF)
    if on_black is None or on_white is None:
        return None
    pixels = bytearray(size * size * 4)
    for i in range(0, len(pixels), 4):
        b0, g0, r0 = on_black[i], on_black[i + 1], on_black[i + 2]
        b1, g1, r1 = on_white[i], on_white[i + 1], on_white[i + 2]
        alpha = 255 - min(255, max(0, ((r1 - r0) + (g1 - g0) + (b1 - b0)) // 3))
        if alpha:
            pixels[i] = min(255, r0 * 255 // alpha)
            pixels[i + 1] = min(255, g0 * 255 // alpha)
            pixels[i + 2] = min(255, b0 * 255 // alpha)
            pixels[i + 3] = alpha
    return Image.frombytes("RGBA", (size, size), bytes(pixels))


def exe_icon_image(path, size):
    """First icon of an executable as a Pillow image, or None."""
    try:
        large, small = win32gui.ExtractIconEx(path, 0, 1)
    except win32gui.error:
        return None
    try:
        icons = (large or small) if size > 20 else (small or large)
        return render_icon(int(icons[0]), size) if icons else None
    finally:
        for icon in list(large) + list(small):
            try:
                win32gui.DestroyIcon(icon)
            except win32gui.error:
                pass


def window_dpi(hwnd):
    """DPI of the monitor a window is on (96 = 100 %); 96 when Windows cannot tell."""
    try:
        return user32.GetDpiForWindow(wintypes.HWND(hwnd)) or 96
    except AttributeError:  # Windows older than 10 1607
        return 96


def icon_from_image(image):
    """HICON built from an RGBA Pillow image (the caller destroys it with destroy_icon)."""
    width, height = image.size
    pixels = image.convert("RGBA").tobytes("raw", "BGRA")
    info = _bitmap_info(width, height)
    bits = ctypes.c_void_p()
    screen = user32.GetDC(None)
    color = gdi32.CreateDIBSection(screen, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
    user32.ReleaseDC(None, screen)
    if not color or not bits.value:
        return None
    ctypes.memmove(bits, pixels, len(pixels))
    mask = gdi32.CreateBitmap(width, height, 1, 1, None)  # unused: the alpha channel decides
    try:
        return user32.CreateIconIndirect(ctypes.byref(ICONINFO(True, 0, 0, mask, color))) or None
    finally:
        gdi32.DeleteObject(color)
        gdi32.DeleteObject(mask)


def destroy_icon(hicon):
    if hicon:
        user32.DestroyIcon(hicon)


def set_window_icons(hwnd, big, small):
    """Give a window its large (taskbar, Alt+Tab) and small (title bar) icons. Returns the
    icons it had before, so the caller can destroy the ones it created earlier."""
    old_big = user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big or 0)
    old_small = user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small or 0)
    return old_big, old_small
