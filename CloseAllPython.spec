# -*- mode: python ; coding: utf-8 -*-
# Used by build.bat. Run: python -m PyInstaller --noconfirm --clean CloseAllPython.spec
import sys

sys.path.insert(0, SPECPATH)
from build_support import EXCLUDES, trim_qt, version_resource  # noqa: E402

a = Analysis(
    ['closeallpython.py'],
    pathex=[],
    binaries=[],
    datas=[('app.ico', '.')],
    hiddenimports=['win32com.client'],  # the "close everything" shortcut (WScript.Shell)
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
a.binaries = trim_qt(a.binaries)
a.datas = trim_qt(a.datas)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CloseAllPython',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed executables trigger antivirus false positives
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app.ico'],
    version=version_resource('CloseAllPython', 'CloseAllPython'),
)
