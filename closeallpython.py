"""CloseAllPython entry point: GUI by default, command line with --no-ui."""
import sys

if sys.platform != "win32":
    sys.exit("CloseAllPython only runs on Windows.")

try:
    import win32gui  # noqa: F401  (checked here to give a clear message)
except ImportError:
    # sys.exit's message is invisible in the windowed executable: show it in a message box too.
    from closeall.crash import message_box
    message = "Missing dependency: pywin32. Run build.bat or: py -m pip install -r requirements.txt"
    message_box(message)
    sys.exit(message)

from closeall.cli import run

if __name__ == "__main__":
    raise SystemExit(run())
