"""Built-in commands (spec §6): status, doctor, sessions, plugins, config, shell, --version."""

from __future__ import annotations

import os
import platform
import re
import shlex
import sys
import tomllib
from pathlib import Path
from typing import Any, Callable

import tn

from . import clock, config as _config, fs, loader, shell as _shell
from .cli import Parser, load_context
from .config import Config, ConfigError, PROJECT_TEMPLATE, USER_TEMPLATE
from .context import Context, machine_name
from .errors import Fail, Missing, Problem, TnError, UsageError
from .match import match
from .options import state
from .output import dumps, fmt_value, home_short, out, paint, table
from .plugin import Plugin, Session, check_label
from .prompt import pick
from . import proc, tomlw


def run(word: str, args: list, cwd: Path, reg: loader.Registry) -> int:
    fn = {"status": cmd_status, "doctor": cmd_doctor, "sessions": cmd_sessions,
          "plugins": cmd_plugins, "config": cmd_config, "shell": cmd_shell}[word]
    return fn(args, cwd, reg)


# -- hook boundary ---------------------------------------------------------------------------


def call_hook(plugin: Plugin, fn: Callable, ctx: Context) -> tuple:
    """(result, error message or None): every hook runs inside its own exception boundary."""
    prev = state.plugin
    state.plugin = plugin.name
    try:
        return fn(ctx), None
    except TnError as e:
        return None, e.message
    except Problem as e:
        return None, e.message
    except KeyboardInterrupt:
        raise
    except Exception as e:  # noqa: BLE001
        if state.debug:
            import traceback
            traceback.print_exc(file=sys.stderr)
        return None, "%s: %s" % (type(e).__name__, e)
    finally:
        state.plugin = prev


def _hook_error(plugin: str, msg: str) -> None:
    out.error("%s: error: %s" % (plugin, msg))


# -- status ----------------------------------------------------------------------------------


def cmd_status(args: list, cwd: Path, reg: loader.Registry) -> int:
    p = Parser(prog="tn status", description="where you are, and each plugin's state here")
    p.parse_args(args)
    ctx = load_context(cwd, state.options)
    plugins, errors = loader.load_all(reg)
    lines: dict = {}
    labels: dict = {}
    for pl in plugins:
        for hook in pl.status_hooks:
            res, err = call_hook(pl, hook, ctx)
            if err:
                errors[pl.name] = err
                continue
            if res is None:
                continue
            items = [res] if isinstance(res, str) else [str(x) for x in res]
            items = [x for x in items if x]
            if items:
                lines.setdefault(pl.name, []).extend(items)
                labels[pl.name] = pl.groups[0]
    if state.options.json:
        out.json({"context": ctx.to_json(), "plugins": lines, "errors": errors})
        return 0
    rows = [["context", ctx.name or "-", home_short(ctx.path)],
            ["machine", ctx.machine or "-"]]
    for name in sorted(lines):
        for i, text in enumerate(lines[name]):
            rows.append([labels[name] if i == 0 else "", text])
    width = max(len(r[0]) for r in rows) + 2
    name_w = max(len(rows[0][1]), 1) + 2
    for r in rows:
        if r[0] == "context":
            out.line((r[0].ljust(width) + r[1].ljust(name_w) + r[2]).rstrip())
        else:
            out.line((r[0].ljust(width) + r[1]).rstrip())
    for name in sorted(errors):
        _hook_error(name, errors[name])
    return 0


# -- doctor ----------------------------------------------------------------------------------


class _Rows:
    def __init__(self) -> None:
        self.rows: list = []

    def add(self, plugin: str, check: str, status: str, detail: str | None = None,
            fix: str | None = None) -> None:
        self.rows.append({"plugin": plugin, "check": check, "status": status,
                          "detail": detail, "fix": fix})


def _core_checks(rows: _Rows, reg: loader.Registry, ctx: Context | None, cfg_issues: list,
                 load_errors: dict) -> None:
    v = sys.version_info
    ver = "%d.%d.%d" % v[:3]
    rows.add("core", "Python %s (3.11+ needed)" % ver, "ok" if v >= (3, 11) else "fail",
             None, None if v >= (3, 11) else "dot apply common")

    lib = _config.tn_home() / "lib"
    running = Path(tn.__file__).resolve().parent.parent
    if (lib / "tn" / "__init__.py").is_file():
        rows.add("core", "tn library in %s" % home_short(lib), "ok")
    else:
        rows.add("core", "tn library in %s" % home_short(lib), "warn",
                 "missing; running from %s" % home_short(running), "dot apply tn")

    readable, count = True, len(reg.plugins)
    for d, reason in reg.unreadable:
        readable = False
        rows.add("core", "plugin directory %s readable" % home_short(d), "fail", reason)
    if readable:
        where = ", ".join(home_short(d) for d in reg.dirs)
        rows.add("core", "plugin directories readable (%d plugin%s in %s)"
                 % (count, "" if count == 1 else "s", where), "ok")

    for info in reg.sorted_plugins():
        missing = [r for r in info.requires if r not in reg.plugins]
        if info.broken:
            rows.add("core", "plugin %s indexes" % info.name, "fail", info.broken,
                     "dot apply %s" % loader.bundle_of(info.name))
        elif missing:
            rows.add("core", "plugin %s has its requires" % info.name, "fail",
                     "needs the %s plugin" % missing[0], "dot apply %s" % loader.bundle_of(missing[0]))
        elif info.name in load_errors:
            rows.add("core", "plugin %s imports" % info.name, "fail", load_errors[info.name],
                     "dot apply %s" % loader.bundle_of(info.name))
    if reg.plugins and not any(r["status"] == "fail" and r["check"].startswith("plugin ")
                               for r in rows.rows):
        rows.add("core", "every plugin indexes and imports", "ok")

    for g in sorted(reg.clashes):
        rows.add("core", "group %s has one owner" % g, "fail", loader.clash_message(reg, g),
                 "dot remove <bundle>")
    if not reg.clashes:
        rows.add("core", "no group clashes", "ok")

    fails = [i for i in cfg_issues if i.level == "fail"]
    for i in cfg_issues:
        where = "%s: " % home_short(i.file) if i.file else ""
        rows.add("core", "config", i.level, where + i.message,
                 "tn config edit" if i.level == "fail" else None)
    if not fails:
        rows.add("core", "config files parse", "ok")

    bindir = Path.home() / ".local" / "bin"
    entries = [os.path.normcase(os.path.normpath(p))
               for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    on_path = os.path.normcase(os.path.normpath(str(bindir))) in entries
    exe_name = "tn.cmd" if os.name == "nt" else "tn"
    found = proc.which(exe_name)
    if not on_path:
        rows.add("core", "%s on PATH" % home_short(bindir), "warn", None, "dot apply common")
    elif not found or os.path.normcase(os.path.dirname(found)) != os.path.normcase(str(bindir)):
        rows.add("core", "%s on PATH" % home_short(bindir), "warn",
                 "tn resolves to %s" % (home_short(found) if found else "nothing"), "dot apply tn")
    else:
        rows.add("core", "%s on PATH" % home_short(bindir), "ok")

    if machine_name():
        rows.add("core", "MY_MACHINE is %s" % machine_name(), "ok")
    else:
        rows.add("core", "MY_MACHINE set", "warn", None, "tn config set machine <name>")

    if os.environ.get("TN_SHELL") == "1":
        rows.add("core", "shell integration loaded", "ok")
    else:
        fix = _shell.init_fix(os.name == "nt")
        rows.add("core", "shell integration loaded", "warn", "tn cannot change directory", fix)


def _plugin_checks(rows: _Rows, plugins: list, ctx: Context) -> None:
    for pl in plugins:
        group = pl.groups[0]
        for hook in pl.check_hooks:
            label = check_label(hook)
            prev = state.plugin
            state.plugin = pl.name
            try:
                detail = hook(ctx)
                rows.add(group, label, "ok", str(detail) if detail else None)
            except Missing as e:
                rows.add(group, label, "fail", e.message, e.fix)
            except Problem as e:
                rows.add(group, e.message, e.level, None, e.fix)
            except TnError as e:
                rows.add(group, label, "fail", e.message, e.fix)
            except KeyboardInterrupt:
                raise
            except Exception as e:  # noqa: BLE001
                rows.add(group, label, "error", "%s: %s" % (type(e).__name__, e))
            finally:
                state.plugin = prev


def _print_doctor(rows: list) -> None:
    status_txt = {"ok": ("ok", "green"), "warn": ("warn", "yellow"), "fail": ("FAIL", "red"),
                  "error": ("error", "red")}
    pw = max((len(r["plugin"]) for r in rows), default=4) + 2
    texts = []
    for r in rows:
        t = r["check"]
        if r["detail"]:
            t = "%s: %s" % (t, r["detail"]) if r["status"] != "ok" else "%s (%s)" % (t, r["detail"])
        texts.append(t)
    cap = 60
    tw = min(max((len(t) for t, r in zip(texts, rows) if r["fix"]), default=0), cap)
    for t, r in zip(texts, rows):
        word, color = status_txt[r["status"]]
        head = paint(word.ljust(6), color) + r["plugin"].ljust(pw)
        if not r["fix"]:
            out.line(head + t)
        elif len(t) <= tw:
            out.line(head + t.ljust(tw) + "  run: " + r["fix"])
        else:
            out.line(head + t)
            out.line(" " * (6 + pw) + " " * tw + "  run: " + r["fix"])


def cmd_doctor(args: list, cwd: Path, reg: loader.Registry) -> int:
    p = Parser(prog="tn doctor", description="check tn, its config and every plugin")
    p.parse_args(args)
    rows = _Rows()
    ctx = load_context(cwd, state.options, lenient=True)
    plugins, errors = loader.load_all(reg)
    _core_checks(rows, reg, ctx, ctx.config.issues, errors)
    _plugin_checks(rows, plugins, ctx)
    if state.options.json:
        out.json(rows.rows)
    else:
        _print_doctor(rows.rows)
    return 1 if any(r["status"] in ("fail", "error") for r in rows.rows) else 0


# -- sessions --------------------------------------------------------------------------------


def all_sessions(ctx: Context, reg: loader.Registry) -> tuple:
    """([Session], {plugin: error}) from every sessions hook."""
    plugins, errors = loader.load_all(reg)
    found: list = []
    for pl in plugins:
        for hook in pl.session_hooks:
            res, err = call_hook(pl, hook, ctx)
            if err:
                errors[pl.name] = err
                continue
            for s in res or []:
                if isinstance(s, Session):
                    found.append(s)
    found.sort(key=lambda s: (s.kind, s.id))
    return found, errors


def _session_row(s: Session) -> dict:
    d = {"kind": s.kind, "id": s.id, "name": s.name, "context": s.context, "dir": s.dir,
         "started": s.started, "attached": s.attached, "status": s.status, "attach": s.attach,
         "extra": dict(s.extra or {})}
    d["age_seconds"] = clock.age_seconds(s.started)
    return d


def cmd_sessions(args: list, cwd: Path, reg: loader.Registry) -> int:
    p = Parser(prog="tn sessions", description="agent sessions on this machine")
    sub = p.add_subparsers(dest="verb")
    a = sub.add_parser("attach", help="attach this terminal to a session")
    a.add_argument("name", nargs="?")
    ns = p.parse_args(args)
    ctx = load_context(cwd, state.options)
    sessions, errors = all_sessions(ctx, reg)
    for name in sorted(errors):
        _hook_error(name, errors[name])
    if ns.verb == "attach":
        if not sessions:
            raise Fail("no sessions to attach to", hint="tn claude start")
        cands = match(ns.name, sessions, lambda s: [s.id, s.name, s.context,
                                                   str((s.extra or {}).get("uuid") or "")])
        if not cands:
            raise UsageError('no session matches "%s"' % ns.name,
                             choices=[s.id for s in sessions])
        s = pick(cands, label=lambda s: "%s  %s" % (s.id, s.name), value=lambda s: s.id,
                 prompt="session", what="which session?")
        if not s.attach:
            raise Fail("%s %s cannot be attached from here" % (s.kind, s.id))
        proc.handoff(s.attach)
    rows = [_session_row(s) for s in sessions]
    out.records(rows, [("kind", "KIND"), ("id", "ID"), ("name", "NAME"),
                       ("context", "CONTEXT"), ("status", "STATUS"),
                       ("age_seconds", "AGE", clock.fmt_age), ("attached", "ATTACHED")],
                empty="No agent sessions. Start one with: tn claude start [target]")
    return 0


# -- plugins ---------------------------------------------------------------------------------


def plugin_rows(reg: loader.Registry) -> list:
    rows = []
    for info in reg.sorted_plugins():
        st = "ok"
        missing = [r for r in info.requires if r not in reg.plugins]
        clash = [g for g in info.groups if g in reg.clashes]
        if info.broken:
            st = "broken: " + info.broken
        elif missing:
            st = "missing requires: " + ", ".join(missing)
        elif clash:
            others = [n for n in reg.clashes[clash[0]] if n != info.name]
            st = "clash: %s also in %s" % (clash[0], ", ".join(others))
        else:
            try:
                loader.load(reg, info.name)
            except TnError as e:
                st = "broken: " + e.message
        rows.append({"name": info.name, "groups": list(info.groups),
                     "requires": list(info.requires), "file": info.path, "state": st,
                     "help": info.help, "installed": True})
    return rows


def cmd_plugins(args: list, cwd: Path, reg: loader.Registry) -> int:
    p = Parser(prog="tn plugins", description="installed plugins")
    p.add_argument("--repo", action="store_true",
                   help="also list the plugins in $DOT_REPO/bundles and whether each is installed")
    ns = p.parse_args(args)
    rows = plugin_rows(reg)
    if ns.repo:
        repo = loader.dot_repo()
        if not (repo / "bundles").is_dir():
            raise Missing("no dotfiles checkout at %s" % home_short(repo),
                          "set DOT_REPO in ~/.config/dot/local.env")
        for info in loader.repo_plugins(repo):
            if info.name in reg.plugins:
                continue
            bundle = os.path.basename(info.path)
            rows.append({"name": info.name, "groups": list(info.groups),
                         "requires": list(info.requires), "file": info.path,
                         "state": ("broken: " + info.broken) if info.broken
                         else "not applied (dot apply %s)" % bundle,
                         "help": info.help, "installed": False})
    sp = lambda v: " ".join(v) if v else "-"  # noqa: E731
    out.records(rows, [("name", "PLUGIN"), ("groups", "GROUPS", sp), ("requires", "REQUIRES", sp),
                       ("file", "FILE", home_short), ("state", "STATE")],
                empty="No plugins installed. dot apply <bundle> copies one into %s"
                % ", ".join(home_short(d) for d in reg.dirs))
    return 0


# -- config ----------------------------------------------------------------------------------

MACHINE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")


def _project_file(ctx: Context) -> Path:
    ctx.require("project")
    return ctx.project_dir / "tn.toml"


def _print_value(v: Any) -> None:
    if state.options.json:
        out.json(v)
    elif isinstance(v, dict):
        out.line(tomlw.dumps(v))
    elif isinstance(v, (bool, list, int, float)) and not isinstance(v, str):
        out.line(tomlw.value_text(v))
    else:
        out.line(v)


def _set_machine(value: str) -> None:
    if not MACHINE_RE.match(value):
        raise UsageError("machine names are letters, digits and dashes (e.g. U1, M2)")
    path = _config.dot_local_env()
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    idx = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("export "):
            s = s[len("export "):].lstrip()
        if s.startswith("MY_MACHINE="):
            idx = i
    new = "MY_MACHINE=%s" % value
    if idx is None:
        lines.append(new)
    else:
        lines[idx] = new
    fs.write_text(path, "\n".join(lines) + "\n")
    out.result({"file": str(path), "key": "machine", "value": value})
    out.hint("open a new shell (or re-source dot env) for MY_MACHINE to reach this one")


def _check_parses(path: Path) -> None:
    try:
        _config.read_toml(path)
    except ConfigError as e:
        raise Fail(e.message, hint="the edit is kept; fix it with: tn config edit")


def _check_valid(ctx: Context, target: Path, ns, parsed: dict) -> None:
    """Refuse a ``config set`` that would leave a config every other command rejects (only
    problems the edit adds: an already-broken config can still be fixed one key at a time)."""
    if ns.project:
        try:
            _config._project_config(ctx.project, target.parent, target, True, parsed)
        except ConfigError as e:
            raise Fail("setting %s would make %s invalid: %s; nothing was written"
                       % (ns.key, home_short(target), e.detail), fix="tn config edit --project")
        return
    before = {i.message for i in ctx.config.issues if i.file is None}
    new = [p for p in Config.problems_with(target, parsed) if p not in before]
    if new:
        raise Fail("setting %s would make the config invalid: %s; nothing was written"
                   % (ns.key, "; ".join(new)), fix="tn config edit")


def _editor_argv(editor: str, windows: bool) -> list:
    """``$VISUAL`` / ``$EDITOR`` as argv. Windows' non-POSIX split keeps the quotes inside a
    token (``"C:\\Program Files\\x.exe" -multiInst``); one surrounding pair is taken off."""
    if not windows:
        return shlex.split(editor)
    toks = shlex.split(editor, posix=False)
    return [t[1:-1] if len(t) >= 2 and t[0] == t[-1] == '"' else t for t in toks]


def cmd_config(args: list, cwd: Path, reg: loader.Registry) -> int:
    p = Parser(prog="tn config", description="read and edit tn's configuration")
    sub = p.add_subparsers(dest="verb")
    g = sub.add_parser("get", help="print a value (dotted key, or machine)")
    g.add_argument("key")
    g.add_argument("--project", action="store_true", help="the project's tn.toml alone")
    s = sub.add_parser("set", help="set one key (a line-level edit)")
    s.add_argument("key")
    s.add_argument("value")
    s.add_argument("--project", action="store_true", help="in the project's tn.toml")
    e = sub.add_parser("edit", help="open the file in $VISUAL / $EDITOR")
    e.add_argument("--project", action="store_true", help="the project's tn.toml")
    sub.add_parser("show", help="the effective merged config and its sources")
    ns = p.parse_args(args)
    if ns.verb is None:
        raise UsageError("which config command?", choices=["get", "set", "edit", "show"],
                         hint="tn config --help")

    if ns.verb == "set" and ns.key == "machine" and not ns.project:
        _set_machine(ns.value)
        return 0
    if ns.verb == "get" and ns.key == "machine" and not ns.project:
        m = machine_name()
        if not m:
            raise Fail("machine is not set", fix="tn config set machine <name>")
        _print_value(m)
        return 0

    ctx = load_context(cwd, state.options, lenient=ns.verb in ("edit", "set"))
    cfg = ctx.config

    if ns.verb == "get":
        if ns.project:
            _project_file(ctx)
            data = cfg.project.raw if cfg.project else {}
        else:
            data = cfg.data
        cur: Any = data
        for part in ns.key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                raise Fail("%s is not set" % ns.key)
            cur = cur[part]
        _print_value(cur)
        return 0

    if ns.verb == "show":
        sources = ["built-in defaults"] + [str(s) for s in cfg.sources]
        if state.options.json:
            out.json({"sources": sources, "config": cfg.data,
                      "project": cfg.project.raw if cfg.project else None})
            return 0
        lines = ["# sources, in merge order:", "#   built-in defaults"]
        lines += ["#   " + home_short(s) for s in cfg.sources]
        text = "\n".join(lines) + "\n\n" + tomlw.dumps(cfg.data)
        if cfg.project and cfg.project.raw:
            text += "\n\n# project settings: %s\n%s" % (home_short(cfg.project.file),
                                                        tomlw.dumps(cfg.project.raw))
        out.line(text)
        return 0

    target = _project_file(ctx) if ns.project else _config.config_dir() / "config.toml"

    if ns.verb == "set":
        try:
            tomlw.split_key(ns.key)
        except ValueError as ex:
            raise UsageError(str(ex))
        value = tomlw.parse_value(ns.value)
        if ns.project and ns.key.split(".")[0] not in _config.PROJECT_KEYS:
            out.warn("%s is not a project key (%s)"
                     % (ns.key, ", ".join(sorted(_config.PROJECT_KEYS))))
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        try:
            new = tomlw.set_key(old, ns.key, value)
            parsed = tomllib.loads(new)
        except (ValueError, tomllib.TOMLDecodeError) as ex:
            raise Fail("setting %s would leave %s unparsable (%s); nothing was written"
                       % (ns.key, home_short(target), ex))
        cur = parsed
        for part in ns.key.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur != value:
            raise Fail("could not set %s in %s with a line edit (is it defined as an inline "
                       "table or a dotted key?); nothing was written; use tn config edit"
                       % (ns.key, home_short(target)))
        _check_valid(ctx, target, ns, parsed)
        fs.write_text(target, new)
        out.result({"file": str(target), "key": ns.key, "value": value})
        out.info("%s = %s in %s" % (ns.key, tomlw.value_text(value), home_short(target)))
        return 0

    # edit
    if state.options.json:
        raise UsageError("--json is not supported here: tn config edit opens an editor")
    if not target.exists():
        fs.write_text(target, PROJECT_TEMPLATE if ns.project else USER_TEMPLATE)
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") \
        or ("notepad" if os.name == "nt" else "vi")
    argv = _editor_argv(editor, os.name == "nt") + [str(target)]
    rc = proc.run(argv, check=False)
    if state.options.dry_run:
        return 0
    if rc != 0:
        raise Fail("%s exited %d" % (argv[0], rc))
    _check_parses(target)
    return 0


# -- shell -----------------------------------------------------------------------------------


def cmd_shell(args: list, cwd: Path, reg: loader.Registry) -> int:
    p = Parser(prog="tn shell", description="shell integration")
    sub = p.add_subparsers(dest="verb")
    i = sub.add_parser("init", help="print the tn function and completion for a shell")
    i.add_argument("shell", nargs="?")
    ns = p.parse_args(args)
    if ns.verb is None:
        raise UsageError("which shell command?", choices=["init"])
    if ns.shell not in _shell.SHELLS:
        raise UsageError("which shell?" if not ns.shell else "unknown shell %r" % ns.shell,
                         choices=list(_shell.SHELLS))
    sys.stdout.write(_shell.script(ns.shell))
    sys.stdout.flush()
    return 0


# -- version ---------------------------------------------------------------------------------


def cmd_version() -> int:
    lib = str(Path(tn.__file__).resolve().parent.parent)
    py = platform.python_version()
    if state.options.json:
        reg = loader.discover()
        out.json({"tn": tn.__version__, "python": py, "lib": lib,
                  "plugins": {i.name: i.path for i in reg.sorted_plugins()}})
    else:
        out.line("tn %s (python %s, %s)" % (tn.__version__, py, lib))
    return 0
