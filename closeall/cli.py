"""Command-line parsing and the --no-ui mode."""
import argparse
import io
import sys
from functools import partial

from . import __version__, settings as settings_mod
from .i18n import translate

CONFIRM_ANSWERS = frozenset({"y", "yes", "o", "oui"})
MAX_BOX_LINES = 12


def build_parser(language):
    t = partial(translate, language)

    parser = argparse.ArgumentParser(prog="CloseAllPython", description=t("cli_description"))
    parser.add_argument("--version", action="version", version=f"CloseAllPython {__version__}")
    parser.add_argument("--no-ui", action="store_true", help=t("cli_help_no_ui"))
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--close", metavar="TEXT", help=t("cli_help_close"))
    target.add_argument("--all", action="store_true", help=t("cli_help_all"))
    target.add_argument("--close-explorer", action="store_true", help=t("cli_help_explorer"))
    parser.add_argument("-y", "--yes", action="store_true", help=t("cli_help_yes"))
    parser.add_argument("--force", action="store_true", help=t("cli_help_force"))
    parser.add_argument("--graceful", action="store_true", help=t("cli_help_graceful"))
    parser.add_argument("--dry-run", action="store_true", help=t("cli_help_dry_run"))
    parser.add_argument("--timeout", type=int, metavar="SECONDS", help=t("cli_help_timeout"))
    parser.add_argument("--update", action="store_true", help=t("cli_help_update"))
    # Used by the release workflow to check a freshly built executable before publishing it.
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    return parser


def parse_args(argv, language):
    parser = build_parser(language)
    args = parser.parse_args(argv)
    cli_only = (args.close is not None or args.all or args.close_explorer or args.yes or args.force or args.graceful or args.dry_run
                or args.timeout is not None)
    if args.self_test:
        if cli_only or args.no_ui or args.update:
            parser.error("--self-test is used on its own")
        return args
    if args.update:
        if cli_only or args.no_ui:
            parser.error(translate(language, "cli_update_alone"))
        return args
    if cli_only and not args.no_ui:
        parser.error(translate(language, "cli_requires_no_ui"))
    if args.no_ui:
        if args.close is None and not args.all and not args.close_explorer:
            parser.error(translate(language, "cli_need_target"))
        if args.close is not None and not args.close.strip():
            parser.error(translate(language, "cli_empty_pattern"))
        if args.force and args.graceful:
            parser.error(translate(language, "cli_force_graceful"))
        if args.timeout is not None and not 0 <= args.timeout <= 600:
            parser.error(translate(language, "cli_bad_timeout"))
    return args


def _emit(stream, text, end="\n"):
    # The windowed executable has no console: sys.stdout / sys.stderr are None there.
    if stream is not None:
        stream.write(text + end)
        stream.flush()


def run_cli(args, prefs, out=None, err=None, stdin=None, problems=None):
    """Execute --no-ui. Exit codes: 0 success, 1 something left running or failed / aborted,
    2 confirmation impossible. `problems`, when given, receives the lines that explain a
    non-zero exit code (shown in a message box when there is no console)."""
    problems = [] if problems is None else problems
    from . import core

    core.log_titles = prefs.get("log_window_titles", False)

    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    stdin = sys.stdin if stdin is None else stdin
    language = prefs["language"]
    t = partial(translate, language)

    def label(target):
        return target.app_name or "?"

    if args.close_explorer:
        count = 0 if args.dry_run else core.close_explorer_windows()
        _emit(out, t("cli_explorer_closed", count=count if not args.dry_run else len(core.explorer_windows())))
        return 0

    windows = core.list_windows(core.own_pids(include_ancestors=True))
    if args.all:
        # "Everything" never includes this program: the desktop shortcut must not close the
        # CloseAllPython window the user has open.
        windows = [w for w in windows if not core.is_closeallpython(w.exe_path)]
    else:
        windows = core.filter_by_title(windows, args.close)
    targets = core.group_targets(windows)
    protected = [x for x in targets if x.protected]
    targets = [x for x in targets if not x.protected]
    for x in protected:
        _emit(err, t("cli_skipped_protected", pid=x.pid, name=label(x), titles="; ".join(x.titles)))
    if not targets:
        _emit(out, t("cli_no_match"))
        return 0
    for x in targets:
        _emit(out, t("cli_target", pid=x.pid, name=label(x), titles="; ".join(x.titles)))
    if args.dry_run:
        return 0
    if not args.yes:
        if stdin is None or not stdin.isatty():
            _emit(err, t("cli_no_tty"))
            problems.append(t("cli_no_tty"))
            return 2
        _emit(out, t("cli_confirm", count=len(targets)), end="")
        if stdin.readline().strip().casefold() not in CONFIRM_ANSWERS:
            _emit(out, t("cli_aborted"))
            return 1

    if args.graceful:
        timeout = args.timeout if args.timeout is not None else prefs["close_timeout"]
        results = core.close_processes(targets, timeout, force=False)
    else:
        results = core.force_processes(targets)
    for r in results:
        name = label(r.target)
        if r.status == core.CLOSED:
            _emit(out, t("cli_closed", pid=r.target.pid, name=name))
        elif r.status == core.FORCED:
            _emit(out, t("cli_forced", pid=r.target.pid, name=name))
        elif r.status == core.STILL_RUNNING:
            problems.append(t("cli_still_running", pid=r.target.pid, name=name))
            _emit(err, problems[-1])
        elif r.status == core.FAILED:
            problems.append(t("cli_failed", pid=r.target.pid, name=name, error=t(r.error_key, detail=r.detail)))
            _emit(err, problems[-1])
    counts = core.summarize(results)
    summary = t("cli_summary", closed=counts[core.CLOSED], forced=counts[core.FORCED],
                still=counts[core.STILL_RUNNING], failed=counts[core.FAILED],
                skipped=len(protected) + counts[core.PROTECTED])
    _emit(out, "\n" + summary)
    if counts[core.FAILED] or counts[core.STILL_RUNNING]:
        problems.append(summary)
        return 1
    return 0


def run_windowless(args, prefs, show=None):
    """--no-ui without a console (windowed executable, pythonw: the desktop shortcut). Nothing
    can be printed, so a failure is shown in a message box instead of passing unnoticed."""
    problems = []
    code = run_cli(args, prefs, out=io.StringIO(), err=io.StringIO(), problems=problems)
    if code and problems:
        if show is None:
            from .crash import MB_ICONWARNING, message_box

            def show(text):
                message_box(text, icon=MB_ICONWARNING)
        lines = problems if len(problems) <= MAX_BOX_LINES else problems[:MAX_BOX_LINES - 2] + ["…", problems[-1]]
        show(translate(prefs["language"], "cli_windowless_failed", details="\n".join(lines)))
    return code


def run_update(prefs, out=None, err=None, updater=None, exe_path=None):
    """--update: install the latest GitHub release over this executable. Exit code 0 when up to
    date or updated, 1 on failure."""
    if updater is None:
        from . import updater
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    language = prefs["language"]
    t = partial(translate, language)

    try:
        release = updater.fetch_latest()
        if not updater.is_newer(release):
            _emit(out, t("cli_update_latest", version=__version__))
            return 0
        _emit(out, t("cli_update_available", version=release.label, current=__version__))
        exe_path = exe_path or updater.current_executable()
        if exe_path is None:
            _emit(out, t("cli_update_source", url=release.page))
            return 0
        _emit(out, t("cli_update_downloading", name=updater.asset_for(release, exe_path).name))
        updater.update(exe_path, release)
    except updater.UpdateError as exc:
        _emit(err, t("cli_update_failed", error=t(exc.key, **exc.values)))
        return 1
    _emit(out, t("cli_update_done", version=release.label))
    return 0


def self_test_checks():
    """What a built executable must manage: every module bundled, and each kind of system call
    (window list, process memory, sessions, protected folders, the COM object behind the desktop shortcut)."""
    import importlib
    import os

    def gui():
        importlib.import_module("closeall.gui")

    def windows():
        from . import core
        core.list_windows()

    def processes():
        from . import winapi
        pids = {p.pid for p in winapi.system_processes()}
        if os.getpid() not in pids:
            raise RuntimeError("this process is missing from the process list")

    def session():
        from . import winapi
        winapi.current_session()

    def folders():
        from . import winapi
        found = winapi.protected_folders()
        if len(found) < 2 or not all(os.path.isdir(folder) for folder in found):
            raise RuntimeError(f"Windows and Program Files folders not found: {found}")

    def shortcut_com():
        from . import shortcut
        if not shortcut._wscript_shell().SpecialFolders("Desktop"):
            raise RuntimeError("no desktop folder")

    return [("interface", gui), ("windows", windows), ("processes", processes), ("session", session),
            ("folders", folders), ("shortcut", shortcut_com)]


def run_self_test(out=None, err=None, checks=None):
    """--self-test: 0 when every check passes, 1 otherwise. Never shows a window or a message box,
    so a build server can run the windowed executable too."""
    import traceback

    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    failed = 0
    for name, check in checks if checks is not None else self_test_checks():
        try:
            check()
        except Exception:
            failed += 1
            _emit(err, f"FAIL {name}\n{traceback.format_exc()}")
        else:
            _emit(out, f"ok   {name}")
    _emit(out, f"CloseAllPython {__version__} self-test: {'FAILED' if failed else 'passed'}")
    return 1 if failed else 0


def run(argv=None):
    settings_mod.setup_logging()
    prefs = settings_mod.load_settings()
    args = parse_args(sys.argv[1:] if argv is None else argv, prefs["language"])
    if args.self_test:
        return run_self_test()
    if args.update:
        return run_update(prefs)
    if args.no_ui:
        if sys.stdout is None:
            return run_windowless(args, prefs)
        return run_cli(args, prefs)
    try:
        from . import gui
        return gui.main()
    except Exception:
        # No console in the windowed executable: show the reason instead of vanishing.
        from . import crash
        crash.report_fatal(prefs["language"])
        return 1
