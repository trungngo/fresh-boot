"""tn plugin for the tmux bundle: plain tmux sessions (docs/tn.md §7.6).

    tn tmux new [name] [-c DIR] [-d]     create (or join) a session; name defaults to the
                                         Context's slug, the directory to the Context's path
    tn tmux attach [name]                join one (switch-client inside tmux)
    tn tmux ls                           every session, agent sessions included
    tn tmux kill [name | --all]          kill-session; the name must be exact; --all (and a
                                         lone session picked without a name) confirms

It replaces the ``mux-new`` / ``mux-kill`` zsh functions and ``tm-kill-all.sh``. Sessions are
always addressed as ``=<name>``, tmux's exact-match form, and ``kill`` takes only an exact name
(no prefix or substring matching), so ``tn tmux kill foo`` never kills ``foobar``. tmux does not exist on Windows: every command exits 3 there.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

from tn import (Cancelled, Context, Fail, Missing, Plugin, UsageError, arg, capture, clock,
                confirm, handoff, match, need, out, pick, run, slugify)

plugin = Plugin("tmux", help="plain tmux sessions")

IS_WINDOWS = os.name == "nt"
FIELDS = ("#{session_name}", "#{session_windows}", "#{session_attached}", "#{session_created}",
          "#{@tn_kind}", "#{@claude_name}")
EMPTY = "No tmux sessions. Start one with: tn tmux new [name]"
BAD_NAME_CHARS = ".:"        # tmux rejects both in a session name (docs/tn.md §3.3)


# == tmux queries ===========================================================================


@dataclass
class TmuxSession:
    name: str
    windows: int | None
    attached: bool
    started: float | None
    kind: str | None          # "claude" | "codex" | None (a plain session)
    title: str | None         # @claude_name, when an agent session carries one

    def to_json(self) -> dict:
        return {"name": self.name, "windows": self.windows, "attached": self.attached,
                "started": clock.iso(self.started),
                "age_seconds": clock.age_seconds(self.started), "kind": self.kind}

    def label(self) -> str:
        bits = ["%s window%s" % (self.windows, "" if self.windows == 1 else "s")
                if self.windows is not None else None,
                "attached" if self.attached else None, self.kind, self.title]
        extra = ", ".join(b for b in bits if b)
        return "%s  (%s)" % (self.name, extra) if extra else self.name


def _int(text: str) -> int | None:
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def parse_sessions(text: str) -> list[TmuxSession]:
    """Rows of ``tmux list-sessions -F <FIELDS joined by tab>``."""
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        f = line.split("\t")
        f += [""] * (len(FIELDS) - len(f))
        created = _int(f[3])
        kind = f[4].strip() or ("claude" if f[5].strip() else None)
        rows.append(TmuxSession(name=f[0], windows=_int(f[1]), attached=(_int(f[2]) or 0) > 0,
                                started=float(created) if created is not None else None,
                                kind=kind, title=f[5].strip() or None))
    return rows


def list_sessions(timeout: float | None = 10) -> list[TmuxSession]:
    """Every tmux session; [] when no server runs (or tmux is absent)."""
    r = capture(["tmux", "list-sessions", "-F", "\t".join(FIELDS)], timeout=timeout)
    if r.returncode != 0:
        return []
    return parse_sessions(r.stdout)


def has_session(name: str) -> bool:
    return capture(["tmux", "has-session", "-t", "=" + name], timeout=10).returncode == 0


def session_path(name: str) -> str | None:
    r = capture(["tmux", "display-message", "-p", "-t", "=" + name, "#{session_path}"],
                timeout=10)
    p = r.stdout.strip() if r.returncode == 0 else ""
    return p or None


def current_session() -> str | None:
    """The session this terminal is in, when inside tmux."""
    if not os.environ.get("TMUX"):
        return None
    r = capture(["tmux", "display-message", "-p", "#{session_name}"], timeout=10)
    name = r.stdout.strip() if r.returncode == 0 else ""
    return name or None


def inside_tmux() -> bool:
    return bool(os.environ.get("TMUX"))


# == shared checks ==========================================================================


def _need_tmux() -> str:
    if IS_WINDOWS:
        raise Missing("tmux sessions need tmux, which Windows lacks", "wsl, then tn tmux there")
    return need("tmux", fix="dot apply tmux")


def _check_name(name: str) -> str:
    if not name or not name.strip():
        raise UsageError("a session name cannot be empty")
    bad = sorted({c for c in name if c in BAD_NAME_CHARS})
    if bad:
        raise UsageError("tmux session names cannot contain %s: %r"
                         % (" or ".join(repr(c) for c in bad), name),
                         hint="try %s" % (slugify(name) or "a plain word"))
    return name


def _no_json(ctx: Context, what: str) -> None:
    if ctx.options.json:
        raise UsageError("--json is not supported here: %s hands the terminal to tmux" % what)


def _join(name: str) -> int | None:
    """Put this terminal on session ``name``: switch-client inside tmux, else hand off."""
    if inside_tmux():
        run(["tmux", "switch-client", "-t", "=" + name])
        return 0
    handoff(["tmux", "attach-session", "-t", "=" + name])


def _select(query: str | None, sessions: list[TmuxSession], *, prompt: str,
            what: str) -> TmuxSession:
    """The session ``query`` names (exact, prefix, substring), or a pick among the candidates."""
    if query is not None:
        found = match(query, sessions, lambda s: (s.name, s.title))
        exact = [s for s in found if s.name == query]
        if exact:
            return exact[0]
        if not found:
            raise UsageError("no tmux session matches %r" % query,
                             choices=[s.name for s in sessions])
        sessions = found
    return pick(sessions, label=lambda s: s.label(), prompt=prompt, what=what)


def _exact(name: str, sessions: list[TmuxSession]) -> TmuxSession:
    """The session named exactly ``name``. Destructive commands take no prefix or substring:
    near misses are only offered back as choices (exit 2)."""
    for s in sessions:
        if s.name == name:
            return s
    near = match(name, sessions, lambda s: (s.name, s.title))
    raise UsageError("no tmux session is named exactly %r" % name,
                     choices=[s.name for s in (near or sessions)],
                     hint="give the full name (tn tmux ls)")


# == commands ===============================================================================


@plugin.command(help="create a session named after this context (or join it if it exists)")
@arg("name", nargs="?", complete="tmux-session",
     help="session name (default: the context's slug, e.g. acme-shop-app-00)")
@arg("-c", dest="dir", metavar="DIR", complete="dir",
     help="start directory (default: the context's path)")
@arg("-d", "--detach", action="store_true",
     help="create it detached and print its name instead of attaching")
def new(ctx: Context, args) -> int | None:
    _need_tmux()
    if not args.detach:
        _no_json(ctx, "tn tmux new (without -d)")
    name = _check_name(args.name if args.name is not None else ctx.slug)
    if args.dir is not None:
        d = os.path.expanduser(args.dir)
        if not os.path.isabs(d):
            d = os.path.join(str(ctx.cwd), d)
        d = os.path.normpath(d)
        if not os.path.isdir(d):
            raise UsageError("no such directory: %s" % args.dir)
    else:
        d = str(ctx.path)

    if has_session(name):
        if args.detach:
            obj = {"name": name, "dir": session_path(name) or d, "created": False}
            out.info("session %s already exists" % name)
            out.result(obj, text=lambda o: o["name"])
            return 0
        out.info("session %s already exists; attaching" % name)
        return _join(name)

    if args.detach:
        run(["tmux", "new-session", "-d", "-s", name, "-c", d])
        out.result({"name": name, "dir": d, "created": True}, text=lambda o: o["name"])
        return 0
    if inside_tmux():
        # Nesting a client inside tmux is refused; create it detached, then move this client.
        run(["tmux", "new-session", "-d", "-s", name, "-c", d])
        run(["tmux", "switch-client", "-t", "=" + name])
        return 0
    handoff(["tmux", "new-session", "-s", name, "-c", d])


@plugin.command(help="join a session in this terminal (pick when no name)")
@arg("name", nargs="?", complete="tmux-session", help="session name (exact, prefix or part)")
def attach(ctx: Context, args) -> int | None:
    _need_tmux()
    _no_json(ctx, "tn tmux attach")
    sessions = list_sessions()
    if not sessions:
        raise Fail(EMPTY)
    s = _select(args.name, sessions, prompt="attach", what="which tmux session?")
    return _join(s.name)


@plugin.command(name="ls", help="list every tmux session, agent sessions included")
def ls_(ctx: Context, args) -> int | None:
    _need_tmux()
    rows = [s.to_json() for s in list_sessions()]
    out.records(rows, [("name", "NAME"), ("kind", "KIND"), ("windows", "WINDOWS"),
                       ("attached", "ATTACHED"), ("age_seconds", "AGE", clock.fmt_age)],
                empty=EMPTY)


@plugin.command(help="kill a session (pick when no name), or every session with --all")
@arg("name", nargs="?", complete="tmux-session", help="exact session name")
@arg("--all", action="store_true", help="kill every tmux session, agent sessions included")
def kill(ctx: Context, args) -> int | None:
    _need_tmux()
    if args.all and args.name is not None:
        raise UsageError("give a session name or --all, not both")
    sessions = list_sessions()
    if not sessions:
        if args.all:
            out.info("No tmux sessions.")
            out.result([])
            return 0
        raise Fail(EMPTY)

    if args.all:
        victims = list(sessions)
        agents = [s for s in victims if s.kind]
        n = len(victims)
        question = "kill all %d tmux session%s" % (n, "" if n == 1 else "s")
        if agents:
            kinds = {}
            for s in agents:
                kinds[s.kind] = kinds.get(s.kind, 0) + 1
            question += " (%s)" % ", ".join(
                "%d %s %s" % (c, "is a" if c == 1 else "are", k.capitalize() + " session"
                              + ("" if c == 1 else "s"))
                for k, c in sorted(kinds.items()))
        if not confirm(question + "?"):
            raise Cancelled()
        # This terminal's own session goes last, so tn is not killed halfway.
        here = current_session()
        victims.sort(key=lambda s: s.name == here)
    elif args.name is not None:
        victims = [_exact(args.name, sessions)]
    elif len(sessions) == 1:
        # pick() would take a lone session without asking; killing needs a yes.
        if not confirm("kill tmux session %s?" % sessions[0].label()):
            raise Cancelled()
        victims = [sessions[0]]
    else:
        victims = [pick(sessions, label=lambda s: s.label(), prompt="kill",
                        what="which tmux session?")]

    killed = []
    for s in victims:
        run(["tmux", "kill-session", "-t", "=" + s.name])
        out.info("killed %s" % s.name)
        if s.kind == "claude" and not args.all:
            out.hint("that was a Claude session; `tn claude stop` also prints how to resume it")
        killed.append({"name": s.name, "killed": True})
    out.result(killed)


# == hooks ==================================================================================


@plugin.status
def sessions_status(ctx: Context):
    if IS_WINDOWS or not shutil.which("tmux"):
        return None
    sessions = list_sessions(timeout=2)
    text = "%d session%s" % (len(sessions), "" if len(sessions) == 1 else "s")
    if any(s.name == ctx.slug for s in sessions):
        text += "; here: %s" % ctx.slug
    return text


@plugin.check
def tmux_installed(ctx: Context):
    """tmux installed"""
    if IS_WINDOWS:
        return "not used on Windows"
    path = need("tmux", fix="dot apply tmux")
    r = capture(["tmux", "-V"], timeout=10)
    return r.stdout.strip() or path


@plugin.completer("tmux-session")
def complete_session(ctx: Context, prefix: str):
    if IS_WINDOWS or not shutil.which("tmux"):
        return []
    return [(s.name, s.kind or "tmux") for s in list_sessions(timeout=2)
            if s.name.startswith(prefix)]
