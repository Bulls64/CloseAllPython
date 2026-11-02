"""Screenshots of the interface for the README, taken on Windows.

The application runs for real (Qt, Windows fonts, Fluent icons, title bar, Mica) on a made-up list of
applications and processes, the same on every run. GitHub Actions runs it (workflow
"Screenshots"); it also works on any Windows PC:

    python tools/screenshots.py OUT_DIR [--wallpaper]

--wallpaper first sets a bright wallpaper and turns Windows' transparency effects on, so the
pictures show the backdrop (it changes the desktop: for a build machine).

Each picture is taken in a fresh process. The names match the files in docs/screenshots.
"""
import ctypes
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SHOTS = [
    # file name, language, theme, scene
    ("applications-dark", "en", "dark", "applications"),
    ("applications-light", "en", "light", "applications"),
    ("applications-fr", "fr", "dark", "applications"),
    ("confirmation-dark", "en", "dark", "confirmation"),
    ("closing-dark", "en", "dark", "closing"),
    ("closing-fr", "fr", "dark", "closing"),
    ("background-dark", "en", "dark", "background"),
    ("settings-dark", "en", "dark", "settings"),
    ("settings-light", "fr", "light", "settings"),
]

MB = 1024 * 1024
APPS = [   # pid, path, titles (en, fr), closes when asked
    (4120, r"C:\Program Files\Microsoft VS Code\Code.exe", [("main.py — my-project — Visual Studio Code",) * 2], True),
    (7344, r"C:\Program Files\Mozilla Firefox\firefox.exe",
     [("Python documentation — Mozilla Firefox",) * 2, ("GitHub — Mozilla Firefox",) * 2], True),
    (2208, r"C:\Windows\System32\notepad.exe", [("notes.txt — Notepad", "notes.txt — Bloc-notes"),
                                                ("todo.txt — Notepad", "todo.txt — Bloc-notes")], True),
    (5512, r"C:\Windows\System32\mspaint.exe", [("Untitled — Paint", "Sans titre — Paint")], False),
    (6630, r"C:\Program Files\WindowsApps\CalculatorApp.exe", [("Calculator", "Calculatrice")], True),
    (8016, r"C:\Program Files\VideoLAN\VLC\vlc.exe", [("VLC media player",) * 2], True),
    (3390, r"C:\Program Files\LibreOffice\program\soffice.bin", [("report.odt — LibreOffice Writer",
                                                                 "rapport.odt — LibreOffice Writer")], False),
]
NAMES = {"Code.exe": "Visual Studio Code", "firefox.exe": "Firefox", "notepad.exe": ("Notepad", "Bloc-notes"),
         "mspaint.exe": "Paint", "CalculatorApp.exe": ("Calculator", "Calculatrice"), "vlc.exe": "VLC media player",
         "soffice.bin": "LibreOffice", "explorer.exe": ("Windows Explorer", "Explorateur Windows"),
         "ms-teams.exe": "Microsoft Teams", "steam.exe": "Steam", "OneDrive.exe": "Microsoft OneDrive",
         "Discord.exe": "Discord", "Dropbox.exe": "Dropbox", "MsMpEng.exe": "Antimalware Service Executable",
         "msedgewebview2.exe": "Microsoft Edge WebView2"}
BACKGROUND = (("ms-teams.exe", 410), ("MsMpEng.exe", 310), ("steam.exe", 260), ("steamwebhelper.exe", 240),
              ("msedgewebview2.exe", 190), ("Discord.exe", 160), ("Dropbox.exe", 140), ("OneDrive.exe", 118),
              ("NVIDIA Share.exe", 75), ("PhoneExperienceHost.exe", 52), ("SearchIndexer.exe", 38), ("tiny.exe", 2))


def real_winapi():
    path = os.path.join(ROOT, "closeall", "winapi.py")
    spec = importlib.util.spec_from_file_location("real_winapi", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frame_bounds(hwnd):
    rect = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(rect), ctypes.sizeof(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def child(name, language, theme, scene, out_dir):
    os.environ["APPDATA"] = tempfile.mkdtemp()
    sys.path.insert(0, ROOT)
    from PIL import ImageGrab

    real = real_winapi()
    from tests import fakewin

    french = language == "fr"
    system = fakewin.FakeSystem()
    system.add_process(os.getpid(), sys.executable)
    hwnd = 1
    for pid, path, titles, closes in APPS:
        system.add_process(pid, path, created=pid * 10, exits_on_close=closes)
        for title in titles:
            system.add_window(hwnd, pid, title[1 if french else 0])
            hwnd += 1
    system.add_process(10, r"C:\Windows\explorer.exe", created=5, exits_on_close=False)
    system.add_window(900, 10, "Program Manager")
    system.add_process(90, None, name="Memory Compression", memory=1400 * MB)
    for index, (exe, size) in enumerate(BACKGROUND):
        system.add_process(1000 + index, rf"C:\Program Files\{exe[:-4]}\{exe}", created=5000 + index,
                           memory=size * MB)
    fakewin.install(system)
    module = sys.modules["closeall.winapi"]
    for attr in ("backdrop_supported", "set_backdrop", "set_dark_title_bar", "accent_palette", "windows_directory"):
        setattr(module, attr, getattr(real, attr))
    module.is_admin = lambda: False
    module.exe_icon_image = lambda path, size: None

    def description(path):
        value = NAMES.get(path.split("\\")[-1])
        return value[1 if french else 0] if isinstance(value, tuple) else value

    module.file_description = description

    from closeall import gui, settings

    gui.winapi = module
    gui.core.winapi = module
    shown_dir = r"C:\Users\User\AppData\Roaming\CloseAllPython"
    real_dir = settings.data_dir()
    settings.save_settings({"language": language, "theme": theme, "close_timeout": 3,
                            "instant_force": scene != "closing"})
    class Shown(type(real_dir)):   # the real folder, displayed as a typical user's
        def __str__(self):
            return shown_dir + ("" if self.name == "CloseAllPython" else "\\" + self.name)

        def __fspath__(self):
            return type(real_dir).__str__(self)

    settings.data_dir = lambda: Shown(real_dir)
    settings.log_path = lambda: Shown(real_dir / "closeallpython.log")

    app = gui.App()
    area = app.screen().availableGeometry()
    width, height = min(1180, area.width() - 60), min(740, area.height() - 90)
    app.resize(width, height)
    app.move(area.x() + 20, area.y() + 20)
    app.show()

    def pump(seconds, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end and not (until and until()):
            app.qapp.processEvents()
            time.sleep(0.02)

    pump(1.5)
    page = app.list_page

    def card(app_name):
        return next(c for c in page.cards.values() if c.entry.name == app_name)

    notepad = "Bloc-notes" if french else "Notepad"
    if scene in ("applications", "confirmation"):
        for app_name in (notepad, "Paint", "LibreOffice"):
            card(app_name).check.setChecked(True)
        card("Firefox").toggle_expand()
        if scene == "confirmation":
            page.close_selected()
    elif scene == "closing":
        for app_name in (notepad, "Paint", "LibreOffice", "VLC media player"):
            card(app_name).check.setChecked(True)
        page.close_selected()
        pump(0.5)
        app.findChildren(gui.Dialog)[0]._confirm()
        pump(0.3)
        pump(10, until=lambda: not app.pages["closing"].running)
    elif scene == "background":
        app.show_page("background")
        pump(10, until=lambda: app.pages["background"].report is not None)
    elif scene == "settings":
        app.show_page("settings")
    hwnd = int(app.winId())
    user32 = ctypes.windll.user32
    # Above every other window, without recreating it (Qt would lose the Mica attributes).
    user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
    user32.SetForegroundWindow(wintypes.HWND(hwnd))
    app.activateWindow()
    pump(3)
    box = frame_bounds(hwnd)
    ImageGrab.grab(all_screens=True).crop(box).save(os.path.join(out_dir, f"{name}.png"))
    print(json.dumps({"name": name, "mica": app.mica, "window": box, "screen": [area.width(), area.height()]}))
    app.close()


def colourful_desktop(out_dir):
    """A bright wallpaper and Windows' transparency effects on, so the pictures show what the
    backdrop lets through. Only for a build machine (option --wallpaper): it changes the desktop."""
    import winreg

    from PIL import Image, ImageDraw

    width, height = 1600, 1000
    picture = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(picture)
    for x in range(width):   # orange to violet
        t = x / width
        draw.line([(x, 0), (x, height)], fill=(int(255 - 120 * t), int(140 - 100 * t), int(40 + 200 * t)))
    for i, colour in enumerate(((0, 200, 255), (60, 220, 120), (255, 230, 60))):
        draw.ellipse([200 + i * 420, 150 + (i % 2) * 380, 560 + i * 420, 510 + (i % 2) * 380], fill=colour)
    path = os.path.join(tempfile.gettempdir(), "closeall-wallpaper.png")
    picture.save(path)
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
    winreg.SetValueEx(key, "EnableTransparency", 0, winreg.REG_DWORD, 1)
    winreg.CloseKey(key)
    ctypes.windll.user32.SystemParametersInfoW(0x0014, 0, path, 0x01 | 0x02)   # SPI_SETDESKWALLPAPER
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 0x0002, 3000, None)
    time.sleep(2)


def main(out_dir, wallpaper=False):
    os.makedirs(out_dir, exist_ok=True)
    if wallpaper:
        colourful_desktop(out_dir)
    results = []
    for name, language, theme, scene in SHOTS:
        run = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", name, language, theme, scene,
                              out_dir], capture_output=True, text=True, timeout=180)
        lines = [line for line in run.stdout.splitlines() if line.startswith("{")]
        entry = json.loads(lines[-1]) if lines else {"name": name}
        entry["exit_code"] = run.returncode
        if run.returncode:
            entry["stderr"] = run.stderr[-3000:]
        results.append(entry)
        print(json.dumps(entry), flush=True)
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    return 1 if any(entry["exit_code"] for entry in results) else 0


if __name__ == "__main__":
    if sys.argv[1] == "--child":
        child(*sys.argv[2:7])
    else:
        sys.exit(main(sys.argv[1], wallpaper="--wallpaper" in sys.argv[2:]))
