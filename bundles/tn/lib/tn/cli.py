"""The entry point: global flags, dispatch, help, errors and exit codes (spec §2, §5.8, §6.8)."""

from __future__ import annotations

import argparse
import difflib
import os
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, term
from .config import Config
from .context import Context, logical_cwd
from .errors import Fail, TnError, UsageError
from .options import Options, state
from .output import dumps, out
from .plugin import RESERVED_FLAGS, Command, Plugin
from . import loader


# -- global flags ----------------------------------------------------------------------------


@dataclass
class Globals:
    json: bool = False
    dry_run: bool = False
    yes: bool = False
    quiet: bool = False
    verbose: int = 0
    no_color: bool = False
    version: bool = False
    cdirs: list = field(default_factory=list)
    rest: list = field(default_factory=list)


_LONG = {"--json": "json", "--dry-run": "dry_run", "--yes": "yes", "--quiet": "quiet",
         "--no-color": "no_color", "--version": "version"}
_SHORT = {"n": "dry_run", "y": "yes", "q": "quiet"}


def parse_globals(argv: list) -> Globals:
    """Take the global flags out of ``argv`` (anywhere before ``--``); the rest is kept."""
    g = Globals()
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            g.rest.extend(argv[i:])
            break
        if tok in _LONG:
            setattr(g, _LONG[tok], True)
        elif tok == "--verbose":
            g.verbose += 1
        elif tok == "-C":
            if i + 1 >= len(argv):
                raise UsageError("-C needs a directory")
            g.cdirs.append(argv[i + 1])
            i += 1
        elif tok.startswith("-C") and len(tok) > 2:
            g.cdirs.append(tok[2:])
        elif len(tok) > 1 and tok[0] == "-" and tok[1] != "-" \
                and all(c in "nyqv" for c in tok[1:]):
            for c in tok[1:]:
                if c == "v":
                    g.verbose += 1
                else:
                    setattr(g, _SHORT[c], True)
        else:
            g.rest.append(tok)
        i += 1
    return g


def resolve_cwd(cdirs: list) -> Path:
    """The cwd after every ``-C`` (each resolved against the previous); chdir()s there."""
    cur = logical_cwd()
    for d in cdirs:
        p = os.path.expanduser(d)
        nxt = Path(os.path.normpath(os.path.join(str(cur), p)))
        if not nxt.is_dir():
            raise UsageError("-C %s: no such directory" % d)
        cur = nxt
    if cdirs:
        os.chdir(str(cur))
    return cur


# -- errors ----------------------------------------------------------------------------------


def print_error(e: TnError) -> None:
    if state.options.json:
        sys.stderr.write(dumps(e.to_json(), indent=None) + "\n")
        return
    lines = ["tn: " + e.message]
    if e.fix:
        lines.append("  run: " + e.fix)
    if e.hint:
        lines.append("  hint: " + e.hint)
    if e.choices:
        lines.append("  choices: " + ", ".join(e.choices))
    sys.stderr.write("\n".join(lines) + "\n")


def internal_error(exc: BaseException) -> int:
    where = " in %s" % state.plugin if state.plugin else ""
    if state.debug:
        traceback.print_exc(file=sys.stderr)
    msg = "internal error%s: %s: %s" % (where, type(exc).__name__, exc)
    if state.options.json:
        sys.stderr.write(dumps({"error": {"code": 1, "message": msg, "fix": None,
                                          "hint": "TN_DEBUG=1 for the traceback",
                                          "choices": None}}, indent=None) + "\n")
    else:
        sys.stderr.write("tn: %s (TN_DEBUG=1 for the traceback)\n" % msg)
    return 1


# -- argparse --------------------------------------------------------------------------------


class Parser(argparse.ArgumentParser):
    """argparse with usage errors raised as ``UsageError`` (exit 2) and help on stdout."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("allow_abbrev", False)
        if sys.version_info >= (3, 14):
            kwargs.setdefault("color", state.options.color)
        super().__init__(*args, **kwargs)

    def error(self, message: str):  # type: ignore[override]
        raise UsageError(message, hint="%s --help" % self.prog)


def build_parser(cmd: Command, group: str) -> Parser:
    prog = " ".join(["tn", group] + cmd.words)
    p = Parser(prog=prog, description=cmd.help)
    for a in cmd.args:
        bad = [n for n in a.names if n in RESERVED_FLAGS]
        if bad:
            raise Fail("the %s plugin declares the reserved flag %s on %s"
                       % (cmd.plugin.name, bad[0], prog))
        p.add_argument(*a.names, **a.kwargs)
    return p


def parse_command(cmd: Command, group: str, tokens: list) -> argparse.Namespace:
    parser = build_parser(cmd, group)
    if cmd.passthrough:
        if "--" in tokens:
            i = tokens.index("--")
            head, tail = tokens[:i], tokens[i + 1:]
        else:
            head, tail = tokens, []
        ns, extra = parser.parse_known_args(head)
        ns.rest = list(extra) + list(tail)
        return ns
    return parser.parse_args(tokens)


# -- help ------------------------------------------------------------------------------------

BUILTIN_HELP = [
    ("status", "where you are: context, machine, and each plugin's state here"),
    ("doctor", "check tn, its config and every plugin's prerequisites"),
    ("sessions", "Claude and Codex sessions on this machine; sessions attach [name]"),
    ("plugins", "installed plugins, their groups and state (--repo: also the repo's)"),
    ("config", "config get|set|edit|show"),
    ("shell", "shell init zsh|bash|pwsh: the cd wrapper and completion"),
]

GLOBAL_HELP = [
    ("-C DIR", "run as if started in DIR"),
    ("--json", "machine output (no prompts)"),
    ("-n, --dry-run", "print what would change, change nothing"),
    ("-y, --yes", "answer yes to every confirmation"),
    ("-q, --quiet", "no progress or hints on stderr"),
    ("-v, --verbose", "more progress; -vv echoes commands and prints tracebacks"),
    ("--no-color", "no colour (as NO_COLOR=1)"),
    ("--version", "tn's version"),
]


def _cols(rows: list) -> list:
    w = max((len(r[0]) for r in rows), default=0)
    return [("  %s  %s" % (r[0].ljust(w), r[1])).rstrip() for r in rows]


def top_help(reg: loader.Registry) -> str:
    lines = ["usage: tn [global flags] <group> <verb> [target] [flags] [-- args...]",
             "       tn [global flags] <built-in> ...", "", "global flags:"]
    lines += _cols(GLOBAL_HELP)
    lines += ["", "built-ins:"] + _cols(BUILTIN_HELP)
    groups = []
    for info in reg.sorted_plugins():
        if info.broken:
            continue
        for g in info.groups:
            if g in reg.clashes:
                groups.append((g, "(refused: claimed by %s)" % ", ".join(reg.clashes[g])))
            else:
                groups.append((g, info.help or info.name))
    lines += ["", "groups:"]
    if groups:
        lines += _cols(sorted(groups))
    else:
        lines.append("  (no plugins installed: dot apply <bundle> copies one in)")
    broken = [i for i in reg.sorted_plugins() if i.broken]
    for i in broken:
        lines.append("  (%s: broken: %s)" % (i.name, i.broken))
    lines += ["", "tn <group> --help for its commands"]
    return "\n".join(lines)


def group_help(plugin: Plugin, group: str) -> str:
    lines = ["usage: tn %s <verb> [target] [flags]" % group]
    if plugin.help:
        lines += ["", plugin.help]
    rows = []
    default = plugin.default_command(group)
    for c in plugin.group_commands(group):
        if c.name == "":
            continue
        rows.append((c.name, c.help or ""))
    if default is not None:
        usage = build_parser(default, group).format_usage().strip()
        usage = usage[len("usage: "):] if usage.startswith("usage: ") else usage
        lines += ["", "default command:", "  " + usage + ("  " + default.help if default.help else "")]
    if rows:
        lines += ["", "commands:"] + _cols(rows)
    lines += ["", "tn %s <verb> --help for a command's flags" % group]
    return "\n".join(lines)


# -- dispatch --------------------------------------------------------------------------------


def load_context(cwd: Path, opts: Options, *, lenient: bool = False) -> Context:
    cfg = Config.load(lenient=lenient)
    return Context.build(cwd, opts, cfg, lenient=lenient)


def missing_group(word: str, reg: loader.Registry) -> TnError:
    repo_infos = loader.repo_plugins()
    for info in repo_infos:
        if not info.broken and word in info.groups:
            bundle = os.path.basename(info.path)
            from .errors import Missing
            return Missing('"%s" comes from the %s bundle, which is not applied on this machine'
                           % (word, bundle), "dot apply %s" % bundle)
    candidates = set(reg.groups) | set(loader.BUILTINS)
    for info in repo_infos:
        candidates.update(info.groups)
    close = difflib.get_close_matches(word, sorted(candidates), n=1)
    hint = ('did you mean "%s"? (tn --help lists the groups)' % close[0]) if close \
        else "tn --help lists the groups"
    return UsageError('unknown command "%s"' % word, hint=hint)


def run_group(plugin: Plugin, group: str, args: list, ctx: Context) -> int:
    cmds = plugin.group_commands(group)
    default = plugin.default_command(group)
    verbs = {c.name: c for c in cmds if c.name}
    if args and args[0] in ("-h", "--help"):
        out.line(group_help(plugin, group))
        return 0
    cmd, rest = None, args
    if args:
        if len(args) >= 2 and ("%s %s" % (args[0], args[1])) in verbs:
            cmd, rest = verbs["%s %s" % (args[0], args[1])], args[2:]
        elif args[0] in verbs:
            cmd, rest = verbs[args[0]], args[1:]
        elif default is None:
            subs = sorted(v for v in verbs if " " in v and v.split()[0] == args[0])
            if subs:
                raise UsageError('"tn %s %s" needs one more word' % (group, args[0]),
                                 choices=subs, hint="tn %s --help" % group)
    if cmd is None:
        if default is not None:
            cmd, rest = default, args
        elif not args:
            raise UsageError("which %s command?" % group, choices=sorted(verbs),
                             hint="tn %s --help" % group)
        else:
            raise UsageError('unknown command "%s %s"' % (group, args[0]), choices=sorted(verbs),
                             hint="tn %s --help" % group)
    ns = parse_command(cmd, group, rest)
    state.plugin = plugin.name
    rc = cmd.fn(ctx, ns)
    return 0 if rc is None else int(rc)


def dispatch(g: Globals) -> int:
    opts = state.options
    rest = g.rest
    if rest and rest[0] == "__complete":
        from . import complete
        return complete.main(rest[1:], g)
    cwd = resolve_cwd(g.cdirs)
    if g.version:
        from .builtins import cmd_version
        return cmd_version()
    reg = loader.discover()
    loader.setup_namespace(reg)
    loader.debug_notes(reg)
    if not rest or rest[0] in ("-h", "--help"):
        out.line(top_help(reg))
        return 0
    word = rest[0]
    if word == "--":
        raise UsageError("no command given", hint="tn --help")
    if word.startswith("-"):
        raise UsageError("unknown option %s" % word, hint="tn --help")
    if word in loader.BUILTINS:
        from . import builtins
        return builtins.run(word, rest[1:], cwd, reg)
    if word in reg.clashes:
        raise Fail(loader.clash_message(reg, word))
    info = reg.owner(word)
    if info is None:
        for i in reg.sorted_plugins():
            if i.broken and (word in i.groups or word == i.name):
                raise Fail("the %s plugin is broken: %s" % (i.name, i.broken),
                           hint="file: %s" % i.path)
        raise missing_group(word, reg)
    plugin = loader.load(reg, info.name)
    if word not in plugin.groups:
        raise Fail("the %s plugin does not provide the %s group its Plugin() declares"
                   % (plugin.name, word))
    ctx = load_context(cwd, opts)
    return run_group(plugin, word, rest[1:], ctx)


IS_WINDOWS = os.name == "nt"


def utf8_stdio() -> None:
    """stdout and stderr in UTF-8 (unencodable characters replaced). Windows encodes a piped or
    redirected stream in the ANSI code page with errors='strict': an author name holding "ễ" in
    ``tn repo show --json | ConvertFrom-Json`` was an internal error, and completion (which
    pipes ``tn.cmd __complete``) silently returned nothing."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError, LookupError):
            pass


def main(argv: list | None = None) -> int:
    """Run tn with ``argv`` (default ``sys.argv[1:]``); returns the exit status."""
    if IS_WINDOWS:
        utf8_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    state.options = Options()
    state.plugin = None
    state.debug = os.environ.get("TN_DEBUG") == "1"
    try:
        try:
            g = parse_globals(argv)
            state.options = Options(json=g.json, dry_run=g.dry_run, yes=g.yes, quiet=g.quiet,
                                    verbose=g.verbose, color=term.color_allowed(g.no_color))
            state.debug = state.debug or g.verbose >= 2
            return dispatch(g)
        except TnError as e:
            print_error(e)
            return e.code
    except KeyboardInterrupt:
        try:
            sys.stderr.write("\n")
        except (OSError, ValueError):
            pass
        return 130
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        sys.stderr.write("%s\n" % code)
        return 1
    except BrokenPipeError:
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except (OSError, ValueError, AttributeError):
            pass
        return 1
    except Exception as e:  # noqa: BLE001 - the internal-error boundary
        return internal_error(e)
