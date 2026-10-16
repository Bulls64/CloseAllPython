"""Command-line parsing and the --no-ui mode."""
import argparse
import sys

from . import __version__, settings as settings_mod
from .i18n import translate

CONFIRM_ANSWERS = frozenset({"y", "yes", "o", "oui"})


def build_parser(language):
    def t(key):
        return translate(language, key)

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
    return parser


def parse_args(argv, language):
    parser = build_parser(language)
    args = parser.parse_args(argv)
    cli_only = (args.close is not None or args.all or args.close_explorer or args.yes or args.force or args.graceful or args.dry_run
                or args.timeout is not None)
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


def run_cli(args, prefs, out=None, err=None, stdin=None):
    """Execute --no-ui. Exit codes: 0 success, 1 something left running or failed / aborted,
    2 confirmation impossible."""
    from . import core

    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    stdin = sys.stdin if stdin is None else stdin
    language = prefs["language"]

    def t(key, **values):
        return translate(language, key, **values)

    def label(target):
        return target.app_name or "?"

    if args.close_explorer:
        count = 0 if args.dry_run else core.close_explorer_windows()
        _emit(out, t("cli_explorer_closed", count=count if not args.dry_run else len(core.explorer_windows())))
        return 0

    windows = core.list_windows(core.own_pids(include_ancestors=True))
    if not args.all:
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
            _emit(err, t("cli_still_running", pid=r.target.pid, name=name))
        elif r.status == core.FAILED:
            _emit(err, t("cli_failed", pid=r.target.pid, name=name,
                         error=t(r.error_key, detail=r.detail)))
    counts = core.summarize(results)
    _emit(out, "\n" + t("cli_summary", closed=counts[core.CLOSED], forced=counts[core.FORCED],
                        still=counts[core.STILL_RUNNING], failed=counts[core.FAILED],
                        skipped=len(protected) + counts[core.PROTECTED]))
    return 1 if counts[core.FAILED] or counts[core.STILL_RUNNING] else 0


def run(argv=None):
    settings_mod.setup_logging()
    prefs = settings_mod.load_settings()
    args = parse_args(sys.argv[1:] if argv is None else argv, prefs["language"])
    if args.no_ui:
        return run_cli(args, prefs)
    try:
        from . import gui
        return gui.main()
    except Exception:
        # No console in the windowed executable: show the reason instead of vanishing.
        from . import crash
        crash.report_fatal(prefs["language"])
        return 1
