"""Helpers shared by the PyInstaller .spec files (not bundled into the executables)."""
import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

ROOT = Path(__file__).resolve().parent


def project_version():
    """Read __version__ from closeall/__init__.py so the .exe always matches the code."""
    text = (ROOT / "closeall" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def version_resource(internal_name, description):
    version = project_version()
    numbers = tuple(int(part) for part in version.split(".")[:4])
    numbers += (0,) * (4 - len(numbers))
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers, mask=0x3F, flags=0x0, OS=0x40004,
                          fileType=0x1, subtype=0x0, date=(0, 0)),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("FileDescription", description),
                StringStruct("FileVersion", version),
                StringStruct("InternalName", internal_name),
                StringStruct("LegalCopyright", "Copyright (c) 2026 Bulls64. MIT License."),
                StringStruct("OriginalFilename", internal_name + ".exe"),
                StringStruct("ProductName", "CloseAllPython"),
                StringStruct("ProductVersion", version),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )


# Qt modules and tools the interface never uses (it needs QtCore, QtGui and QtWidgets only).
EXCLUDES = ['build_support', 'tkinter', '_tkinter', 'PIL.ImageTk', 'PIL.ImageQt',
            'PySide6.QtNetwork', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtSql',
            'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets', 'PySide6.QtPdf', 'PySide6.QtSvg', 'PySide6.QtDBus',
            'PySide6.QtPrintSupport', 'PySide6.QtTest', 'PySide6.QtXml', 'PySide6.QtConcurrent',
            'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtUiTools']
KEPT_TRANSLATIONS = ('_en.qm', '_fr.qm')   # the languages of the interface


def trim_qt(entries):
    """Leave out of the executables what the Qt interface does not need: the software OpenGL
    renderer (widgets are drawn without OpenGL) and the translations of other languages."""
    kept = []
    for entry in entries:
        name = entry[0].replace("\\", "/").lower()
        if name.endswith("opengl32sw.dll"):
            continue
        if "/translations/" in name and name.endswith(".qm") and not name.endswith(KEPT_TRANSLATIONS):
            continue
        kept.append(entry)
    return kept
