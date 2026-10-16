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
