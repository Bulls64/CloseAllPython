@echo off
setlocal
cd /d "%~dp0"
echo === CloseAllPython - Windows build ===

where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python Launcher "py" was not found. Install Python 3.14 from python.org.
  goto failed
)

rem Isolated build environment: never touches the global Python installation.
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment .venv ...
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
set "PY=.venv\Scripts\python.exe"
"%PY%" --version

echo Installing pinned dependencies...
"%PY%" -m pip install --disable-pip-version-check --require-hashes --only-binary=:all: -r requirements-build.txt
if errorlevel 1 goto failed

echo Running tests...
"%PY%" -m unittest discover -s tests -t .
if errorlevel 1 goto failed

echo Building the graphical application...
"%PY%" -m PyInstaller --noconfirm --clean --distpath dist --workpath build CloseAllPython.spec
if errorlevel 1 goto failed

echo Building the command-line executable...
"%PY%" -m PyInstaller --noconfirm --clean --distpath dist --workpath build CloseAllPython-CLI.spec
if errorlevel 1 goto failed

rem Optional code signing (reduces antivirus false positives):
rem   set SIGN_CERT=C:\path\to\certificate.pfx
rem   set SIGN_PASSWORD=...
if defined SIGN_CERT (
  echo Signing executables...
  signtool sign /f "%SIGN_CERT%" /p "%SIGN_PASSWORD%" /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 dist\CloseAllPython.exe dist\CloseAllPython-CLI.exe
  if errorlevel 1 goto failed
)

echo.
echo Build complete:
echo   dist\CloseAllPython.exe       graphical application
echo   dist\CloseAllPython-CLI.exe   command line
echo Examples:
echo   dist\CloseAllPython-CLI.exe --no-ui --close "notepad" --dry-run
echo   dist\CloseAllPython-CLI.exe --no-ui --close "notepad"
pause
exit /b 0

:failed
echo ERROR: build failed.
pause
exit /b 1
