"""tn plugin for the codex bundle: ``tn codex start|ls|attach|stop|login`` (docs/tn.md §7.3).

The verbs match the claude plugin, but their meaning follows how Codex works. Codex runs ONE
shared app-server daemon that hosts every session; Remote Control belongs to that daemon, and
Codex has no machine-readable session list (``codex agents`` is a full-screen browser). So:

* ``start`` brings the daemon up with Remote Control and pairs it; sessions are opened from the
  app or with ``codex -C <dir>``;
* ``ls`` reports the daemon (``codex app-server daemon version`` prints JSON), never the browser;
* ``attach`` hands off to ``codex resume <name>``, or to Codex's own picker (``--all``);
* ``stop`` is daemon-wide, so it always confirms;
* ``login`` picks the browser or the device-code flow for the machine you are on.

``codex login status`` prints "Not logged in" and still exits 0, and has no --json: the text is
the only signal, and it is captured (never piped into ``grep -q``, which SIGPIPEs codex).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from tn import (Cancelled, Context, Fail, Missing, Plugin, Problem, Session, UsageError, arg,
                can_prompt, capture, confirm, handoff, need, out, run, term)
from tn.plugins import projects

plugin = Plugin("codex", help="the shared Codex daemon and its sessions", requires=["projects"])

FIX_INSTALL = "dot apply codex"
FIX_LOGIN = "tn codex login"
STOP_QUESTION = ("this stops the shared daemon, ending remote control for every Codex session "
                 "on this machine; conversations are kept. Stop it?")


# == queries ================================================================================


def _codex() -> str:
    return need("codex", FIX_INSTALL)


def _login_text() -> str:
    """``codex login status`` output (stdout and stderr: codex prints it on either)."""
    r = capture(["codex", "login", "status"], timeout=20)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def _logged_in(text: str) -> bool:
    """Only "Not logged in" (matched as ``ot logged in``) means signed out, as in the old
    scripts: any other text, even none, counts as signed in."""
    return "ot logged in" not in text


def _first_line(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[0] if lines else "unknown (codex login status printed nothing)"


def _daemon() -> dict:
    """``{"running", "status", "cli_version", "app_server_version"}``.

    ``codex app-server daemon version`` prints status and versions as JSON, and fails outright
    when nothing is listening: that failure is the liveness check.
    """
    r = capture(["codex", "app-server", "daemon", "version"], timeout=10)
    d = {"running": r.returncode == 0, "status": None, "cli_version": None,
         "app_server_version": None}
    if r.returncode != 0:
        return d
    try:
        j = json.loads(r.stdout or "")
    except ValueError:
        j = None
    if isinstance(j, dict):
        d["status"] = j.get("status") or None
        d["cli_version"] = j.get("cliVersion") or None
        d["app_server_version"] = j.get("appServerVersion") or None
    return d


def _platform() -> str:
    """``sys.platform`` (a function so the tests can pretend to be another OS)."""
    return sys.platform


def _has_local_browser() -> bool:
    """Whether a browser on this machine could take the login's localhost callback.

    It can only tell whether the machine HAS a browser, not whether you are sitting at it: a
    desktop reached remotely looks the same, hence the hint printed with the browser flow.
    """
    if os.environ.get("SSH_CONNECTION"):
        return False
    plat = _platform()
    if plat == "darwin" or plat.startswith("win"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


# == start ==================================================================================


@plugin.command(help="start the shared daemon with Remote Control and pair it")
@arg("target", nargs="?", complete="target", help="project, project/repo, repo or a path")
@arg("--ws", metavar="NN|new", complete="ws", help="in a workspace (new: create one first)")
def start(ctx: Context, args) -> int:
    """start the shared daemon with Remote Control and pair it"""
    _codex()
    # Remote Control registers the machine against the account: without a login it fails
    # obscurely ("Remote control is enabled on <host> but the connection is errored").
    if not _logged_in(_login_text()):
        raise Missing("not signed in to Codex", FIX_LOGIN)

    where = projects.resolve(ctx, args.target, ws=args.ws, prefer_repo=True)
    root = where.git_root
    sdir = Path(root) if root is not None else Path(where.path)
    sctx = ctx.for_path(sdir)
    out.info("Directory: %s" % sdir)
    if os.path.normcase(str(sdir)) != os.path.normcase(str(where.path)):
        out.info("           (git root of %s)" % where.path)

    # Starting a running daemon is a no-op, so this is safe to repeat.
    out.info("Daemon:    starting with remote control")
    run(["codex", "remote-control", "start"], quiet=True)

    pairing = None
    if ctx.options.json:
        if ctx.options.dry_run:
            out.would("run codex remote-control pair")
        else:
            r = capture(["codex", "remote-control", "pair"], timeout=120)
            if r.returncode != 0:
                raise Fail("codex remote-control pair exited %d" % r.returncode,
                           hint=_first_line(r.stderr or r.stdout))
            pairing = (r.stdout or "").strip() or None
    else:
        out.info("")
        out.info("pairing code (only needed to link a new device):")
        # Streamed rather than captured: the code must show while pair may still be waiting.
        code = run(["codex", "remote-control", "pair"], check=False)
        if code != 0:
            raise Fail("codex remote-control pair exited %d" % code,
                       hint="the daemon is running; pair later with: codex remote-control pair")

    out.hint("open a session there: codex -C %s" % sdir)
    out.hint("browse sessions: codex agents   resume one: tn codex attach [name]")
    out.result({"dir": str(sdir), "context": sctx.name, "daemon": "running",
                "pairing": pairing, "workspace_created": where.workspace_created})
    return 0


# == ls =====================================================================================


def _row() -> dict:
    d = _daemon()
    return {"id": "daemon", "running": d["running"], "status": d["status"],
            "cli_version": d["cli_version"], "app_server_version": d["app_server_version"],
            "logged_in": _logged_in(_login_text())}


def _version_text(row: dict) -> str:
    if not row["running"]:
        return "-"
    return "codex %s / app-server %s" % (row["cli_version"] or "?",
                                         row["app_server_version"] or "?")


@plugin.command(name="ls", help="the shared daemon: running, status, versions, login")
def ls_(ctx: Context, args) -> int:
    """the shared daemon: running, status, versions, login"""
    _codex()
    row = _row()
    out.records([row], [("running", "DAEMON", lambda v: "running" if v else "stopped"),
                        ("status", "STATUS"),
                        ("cli_version", "VERSION", lambda _v: _version_text(row)),
                        ("logged_in", "LOGIN")],
                empty="")
    if not ctx.options.json:
        if not row["running"]:
            out.hint("start it: tn codex start [target]")
        if not row["logged_in"]:
            out.hint("not signed in: %s" % FIX_LOGIN)
        out.hint("browse sessions: codex agents   resume one: tn codex attach [name]")
    return 0


# == attach =================================================================================


@plugin.command(help="resume a Codex session in this terminal (no name: Codex's own picker)")
@arg("name", nargs="?", help="session name or uuid")
def attach(ctx: Context, args) -> int:
    """resume a Codex session in this terminal (no name: Codex's own picker)"""
    _codex()
    if args.name:
        out.info("resuming %s" % args.name)
        handoff(["codex", "resume", args.name])
    if ctx.options.json:
        handoff(["codex", "resume", "--all"])   # rejects --json (exit 2)
    # Codex's picker is still a prompt (§2.5): only on a terminal.
    if not can_prompt():
        raise UsageError("which session? pass a name or uuid (codex resume --all needs a terminal)",
                         hint="browse them on a terminal with: codex agents")
    out.info("choose a session to resume (Esc to cancel)")
    handoff(["codex", "resume", "--all"])
    return 0  # not reached


# == stop ===================================================================================


@plugin.command(help="stop the shared daemon (every session loses remote control)")
def stop(ctx: Context, args) -> int:
    """stop the shared daemon (every session loses remote control)"""
    _codex()
    if not _daemon()["running"]:
        out.info("not running")
        out.result({"stopped": False})
        return 0
    if not confirm(STOP_QUESTION):
        raise Cancelled()
    run(["codex", "remote-control", "stop"], quiet=True)
    out.result({"stopped": True})
    out.hint("conversations are kept: tn codex start, then tn codex attach [name]")
    return 0


# == login ==================================================================================


@plugin.command(help="sign in to Codex (browser, or device code when there is no browser here)")
@arg("--device-auth", action="store_true", help="print a URL and code to enter on another device")
@arg("--with-api-key", action="store_true", help="read an API key from stdin")
@arg("--with-access-token", action="store_true", help="read an access token from stdin")
def login(ctx: Context, args) -> int:
    """sign in to Codex (browser, or device code when there is no browser here)"""
    _codex()
    flags = [f for f, on in (("--device-auth", args.device_auth),
                             ("--with-api-key", args.with_api_key),
                             ("--with-access-token", args.with_access_token)) if on]
    if len(flags) > 1:
        raise UsageError("pass only one of --device-auth, --with-api-key, --with-access-token")

    text = _login_text()
    signed_in = _logged_in(text)
    if ctx.options.json:
        out.json({"logged_in": signed_in, "status": _first_line(text)})
        return 0

    out.info("currently: %s" % _first_line(text))
    if signed_in and not confirm("sign in again, replacing this?"):
        out.info("keeping the current login")
        return 0

    stdin_text = None
    if not flags:
        if _has_local_browser():
            out.info("not at this machine? Ctrl-C and run: tn codex login --device-auth")
        else:
            out.info("no browser on this machine: using the device code flow")
            flags = ["--device-auth"]
    elif flags[0] in ("--with-api-key", "--with-access-token") and not term.is_tty("stdin"):
        # Piped in (printenv OPENAI_API_KEY | tn codex login --with-api-key): hand it on.
        try:
            stdin_text = sys.stdin.read()
        except (OSError, ValueError):
            stdin_text = None
        if not (stdin_text or "").strip():
            raise UsageError("%s reads the secret from stdin, which is empty" % flags[0],
                             hint="printenv OPENAI_API_KEY | tn codex login --with-api-key")

    code = run(["codex", "login", *flags], input=stdin_text, check=False)
    if ctx.options.dry_run:
        return 0
    out.info("now: %s" % _first_line(_login_text()))
    return code


# == hooks ==================================================================================


def _installed() -> bool:
    return shutil.which("codex") is not None


@plugin.sessions
def _sessions(ctx: Context) -> list:
    if not _installed():
        return []
    d = _daemon()
    if not d["running"]:
        return []
    return [Session(kind="codex", id="daemon", name="codex daemon", context=None, dir=None,
                    started=None, attached=None, status=d["status"] or "running",
                    attach=["codex", "resume", "--all"],
                    extra={"cli_version": d["cli_version"],
                           "app_server_version": d["app_server_version"]})]


@plugin.status
def _status(ctx: Context):
    if not _installed():
        return None
    return "daemon running" if _daemon()["running"] else "daemon stopped"


@plugin.check
def _codex_installed(ctx: Context):
    """codex installed"""
    return need("codex", FIX_INSTALL)


@plugin.check
def _codex_logged_in(ctx: Context):
    """logged in"""
    if not _installed():
        raise Missing("codex is not installed", FIX_INSTALL)
    text = _login_text()
    if not _logged_in(text):
        raise Problem("codex: not signed in", fix=FIX_LOGIN)
    return _first_line(text)
