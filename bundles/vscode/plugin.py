"""tn plugin for the vscode bundle: ``tn tunnel`` (docs/tn.md §7.4).

Port forwards through Microsoft dev tunnels, the service behind VS Code's PORTS panel (the
``code`` CLI cannot forward a port, ``devtunnel`` can). Replaces port-forward, port-list and
port-stop.

    tn tunnel open [port...] [--public] [--for DURATION]
    tn tunnel ls
    tn tunnel close [port... | --all]

The tunnels are TEMPORARY: ``devtunnel host`` creates one and deletes it when it exits
cleanly, so ``devtunnel list`` shows nothing and the state files are the truth. One
``<port>.json`` and one ``<port>.log`` per port under ``$TN_STATE_DIR/tunnels/``. A tunnel is
live while its pid is alive AND still names ``devtunnel host ... -p <port>`` (the state files
survive a reboot, and a reused pid must never be taken for, let alone signalled as, the host).
Stale entries are pruned whenever the state is read (the json goes, the log stays: it is the
record of why a tunnel ended); a pruned entry is never signalled.

``--for`` starts a detached watcher, ``python -P -m tn tunnel close <port> --when-expired``,
which sleeps until the expiry and closes the tunnel only if it is still the one it was started
for. ``tn tunnel ls`` and ``tn status`` close anything past its expiry too, in case the watcher
died. Both detached processes run in the state directory, never the caller's cwd (on Windows a
process's cwd cannot be removed, and ``-m`` would put the cwd on ``sys.path``; ``-P`` keeps it
off).

Stopping: SIGTERM lets devtunnel delete its temporary tunnel at the service, as Ctrl-C would;
SIGKILL after STOP_SECONDS. On Windows ``os.kill`` is TerminateProcess, a hard kill with no
shutdown, so there (and whenever SIGKILL was needed) tn also runs ``devtunnel delete <id>``,
the id read from the link, so no orphaned tunnel counts toward the account's limit.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import signal
import socket
import sys
import time
from pathlib import Path

import tn
from tn import (Fail, Missing, Plugin, Problem, UsageError, arg, capture, clock, fs, need, out,
                pick, pid_alive, spawn_detached)
from tn.config import state_dir
from tn.options import state
from tn.output import dumps, home_short

plugin = Plugin("vscode", help="port forwards through VS Code dev tunnels", groups=["tunnel"])

TIMEOUT_SECONDS = 45      # how long `open` waits for the relay to hand back a link
POLL_SECONDS = 1.0        # how often it re-reads the log meanwhile
STOP_SECONDS = 10         # SIGTERM grace before SIGKILL
WATCH_MAX_SLEEP = 60      # the expiry watcher re-checks at least this often
LOGIN_FIX = "devtunnel user login -g   (add -d on a machine without a browser)"
IS_WINDOWS = os.name == "nt"

_sleep = time.sleep       # tests patch these
_watch_sleep = time.sleep
_monotonic = time.monotonic

DURATION_RE = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")


# -- state -----------------------------------------------------------------------------------


def tunnels_dir() -> Path:
    return state_dir() / "tunnels"


def _json_path(port: int) -> Path:
    return tunnels_dir() / ("%d.json" % port)


def _log_path(port: int) -> Path:
    return tunnels_dir() / ("%d.log" % port)


def _read(port: int) -> dict | None:
    try:
        data = json.loads(_json_path(port).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write(st: dict) -> None:
    fs.write_text(_json_path(int(st["port"])), dumps(st) + "\n")


def _alive(pid) -> bool:
    """Like ``pid_alive``, but a child of this process that has exited (a zombie until reaped,
    which ``os.kill(pid, 0)`` still reports as alive) is reaped and counts as dead."""
    try:
        pid = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if not IS_WINDOWS:
        try:
            done, _ = os.waitpid(pid, os.WNOHANG)
            if done == pid:
                return False
        except (ChildProcessError, OSError):
            pass
    return pid_alive(pid)


def _dry_run() -> bool:
    return state.options.dry_run


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _ps() -> str:
    """``ps`` by absolute path when there is one (tn's PATH may be minimal)."""
    for cand in ("/bin/ps", "/usr/bin/ps"):
        if os.path.exists(cand):
            return cand
    return "ps"


def _cmdline(pid: int) -> str | None:
    """What ``pid`` is running, as text: the full command line on Unix (/proc on Linux, else
    ``ps -o args=``), the image name on Windows (``tasklist``). None when it cannot be told."""
    if IS_WINDOWS:
        r = capture(["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"], timeout=10)
        for row in csv.reader((r.stdout or "").splitlines()):
            if len(row) > 1 and row[1].strip() == str(pid):
                return row[0].strip()
        return None
    try:
        raw = Path("/proc/%d/cmdline" % pid).read_bytes()
    except OSError:
        raw = None
    if raw:
        return raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
    r = capture([_ps(), "-o", "args=", "-p", str(pid)], timeout=10)
    text = (r.stdout or "").strip()
    return text if r.returncode == 0 and text else None


def _is_host_cmd(cmd: str, port: int) -> bool:
    if IS_WINDOWS:
        return cmd.lower() in ("devtunnel.exe", "devtunnel")
    return re.search(r"(?:^|[\s/\\])devtunnel(?:\.exe)?\s+host\b.*\s-p\s+%d(?:\s|$)" % port,
                     cmd) is not None


def _is_watcher_cmd(cmd: str, port: int) -> bool:
    if IS_WINDOWS:
        name = cmd.lower()
        return name.startswith("python") or name == Path(sys.executable).name.lower()
    return re.search(r"\stn\s+tunnel\s+close\s+%d\s+--when-expired(?:\s|$)" % port,
                     cmd) is not None


def _ours(pid, kind: str, port: int) -> bool:
    """Whether ``pid`` is alive and still the process tn recorded: the ``devtunnel host`` for
    ``port`` (kind "host") or its ``--when-expired`` watcher (kind "watcher"). A pid that is
    dead, reused by something else, or whose command cannot be read is not ours."""
    try:
        pid = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0 or pid == os.getpid() or not _alive(pid):
        return False
    cmd = _cmdline(pid)
    if not cmd:
        return False
    return (_is_host_cmd if kind == "host" else _is_watcher_cmd)(cmd, port)


def live(port: int) -> dict | None:
    """The state of the live tunnel on ``port``, pruning a dead one; None when not open."""
    st = _read(port)
    if st is None:
        return None
    if not _ours(st.get("pid"), "host", port):
        if not _dry_run():
            _unlink(_json_path(port))       # the host is gone, so is its tunnel; keep the log
        return None
    return st


def live_tunnels(*, enforce_expiry: bool = False) -> list:
    """Every live tunnel, by port. With ``enforce_expiry``, a tunnel past its ``expires`` is
    closed on the way past (the watcher may have died)."""
    d = tunnels_dir()
    try:
        names = sorted(p.name for p in d.iterdir() if p.suffix == ".json")
    except OSError:
        return []
    rows = []
    for name in names:
        try:
            port = int(name[:-5])
        except ValueError:
            continue
        st = live(port)
        if st is None:
            continue
        if enforce_expiry and _expired(st):
            out.info("port %d: expired, closing" % port)
            close_tunnel(st)
            continue
        rows.append(st)
    rows.sort(key=lambda s: int(s["port"]))
    return rows


def _expired(st: dict) -> bool:
    exp = clock.parse_iso(st.get("expires"))
    return exp is not None and clock.now() >= exp


# -- parsing ---------------------------------------------------------------------------------


def parse_port(text) -> int:
    try:
        port = int(str(text), 10)
    except ValueError:
        port = 0
    if not 1 <= port <= 65535:
        raise UsageError("not a port number: %s (1 to 65535)" % text)
    return port


def parse_duration(text: str) -> int:
    """``90s``, ``30m``, ``2h``, ``1d`` and combinations (``1h30m``) -> seconds."""
    m = DURATION_RE.match((text or "").strip().lower())
    if not text or not m or not any(m.groups()):
        raise UsageError("not a duration: %s (use 90s, 30m, 2h, 1d or 1h30m)" % text)
    d, h, mi, s = (int(g or 0) for g in m.groups())
    total = d * 86400 + h * 3600 + mi * 60 + s
    if total <= 0:
        raise UsageError("not a duration: %s (it must be longer than 0s)" % text)
    return total


# -- devtunnel -------------------------------------------------------------------------------


def _login_text() -> str:
    r = capture(["devtunnel", "user", "show"], timeout=20)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def require_login() -> None:
    # `devtunnel user show` exits 0 either way: read the text. "Not logged in." contains
    # "logged in", so match the negative.
    if "not logged in" in _login_text().lower():
        raise Missing("not logged in to dev tunnels (a separate login from code tunnel)",
                      LOGIN_FIX)


def url_in_log(port: int) -> str | None:
    """The shareable link: ``https://<id>-<port>.<cluster>.devtunnels.ms``. Anchoring on
    ``-<port>.`` keeps out ``<id>.<cluster>:<port>`` and the ``-<port>-inspect.`` URL."""
    try:
        text = _log_path(port).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r"https://[a-z0-9]+-%d\.[a-z0-9-]+\.devtunnels\.ms" % port, text)
    return m.group(0) if m else None


def listening(port: int) -> bool:
    """Whether anything accepts a TCP connection on localhost:<port> (IPv4 or IPv6)."""
    for host in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            continue
    return False


def _terminate(pid, kind: str, port: int) -> bool:
    """SIGTERM (TerminateProcess on Windows), up to STOP_SECONDS, then SIGKILL, but only while
    ``pid`` is still ours (see ``_ours``): a reused pid is never signalled. True when the process
    ended on the TERM (on Unix that lets devtunnel delete its tunnel, as Ctrl-C would), or was
    not ours to stop; False when it had to be killed."""
    if not _ours(pid, kind, port):
        return True
    pid = int(pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return True
    deadline = _monotonic() + STOP_SECONDS
    while _alive(pid) and _monotonic() < deadline:
        _sleep(0.2)
    if not _alive(pid):
        return True
    if _ours(pid, kind, port):
        try:
            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        except OSError:
            pass
        _alive(pid)  # reap it when it is our child
    return False


def tunnel_id(link: str | None) -> str | None:
    """``https://<id>-<port>.<cluster>.devtunnels.ms`` -> ``<id>.<cluster>``."""
    m = re.match(r"^https://([a-z0-9]+)-\d+\.([a-z0-9-]+)\.devtunnels\.ms", link or "")
    return "%s.%s" % m.groups() if m else None


def _delete_at_service(st: dict) -> None:
    """``devtunnel delete <id>``: the host was killed without its shutdown (always on Windows,
    where os.kill is TerminateProcess), so the temporary tunnel is still registered."""
    tid = tunnel_id(st.get("url"))
    if not tid:
        return
    r = capture(["devtunnel", "delete", tid], input="y\n", timeout=30)
    if r.returncode != 0:
        err = ((r.stderr or "") + (r.stdout or "")).strip().splitlines()
        out.warn("port %d: devtunnel delete %s failed%s; the service expires it later"
                 % (int(st["port"]), tid, (": " + err[-1]) if err else ""))


def close_tunnel(st: dict) -> None:
    """Stop the host and its expiry watcher (not when that is us), drop the json."""
    port = int(st["port"])
    if _dry_run():
        out.would("stop devtunnel host for port %d (pid %s)" % (port, st.get("pid")))
        out.would("remove %s" % _json_path(port))
        return
    graceful = _terminate(st.get("pid"), "host", port)
    _terminate(st.get("watcher_pid"), "watcher", port)
    if IS_WINDOWS or not graceful:
        _delete_at_service(st)
    _unlink(_json_path(port))


def _lib_dir() -> str:
    return str(Path(tn.__file__).resolve().parent.parent)


def start_watcher(st: dict) -> int:
    """``python -P -m tn tunnel close <port> --when-expired``, detached, in the tunnels
    directory (-P: the cwd is never on sys.path); returns its pid."""
    port = int(st["port"])
    env = {"PYTHONPATH": os.pathsep.join(
        p for p in (_lib_dir(), os.environ.get("PYTHONPATH")) if p),
        "TN_STATE_DIR": str(state_dir())}
    fs.mkdir(tunnels_dir())
    return spawn_detached([sys.executable, "-P", "-m", "tn", "tunnel", "close", str(port),
                           "--when-expired"], cwd=tunnels_dir(), log=_log_path(port), env=env)


def _set_expiry(st: dict, seconds: int) -> None:
    old = st.get("watcher_pid")
    st["expires"] = clock.iso(clock.now() + seconds)
    st["watcher_pid"] = None
    _write(st)                      # the old watcher sees a new expiry and stands down
    if old and not _dry_run():
        _terminate(old, "watcher", int(st["port"]))
    pid = start_watcher(st)
    if pid:
        st["watcher_pid"] = pid
        _write(st)


def _access_line(st: dict) -> str:
    if st.get("access") == "public":
        return "public: anyone with this link reaches port %d on this machine" % int(st["port"])
    return "private: opening it asks for the account that started it"


def _record(st: dict, reused: bool, error: str | None = None) -> dict:
    return {"port": int(st["port"]), "url": st.get("url"), "access": st.get("access"),
            "pid": st.get("pid") or None, "started": st.get("started"),
            "expires": st.get("expires"), "label": st.get("label"),
            "context": st.get("context"), "reused": reused, "error": error}


# -- commands --------------------------------------------------------------------------------


@plugin.command(name="open", help="forward local ports to the internet and print the links")
@arg("port", nargs="*", complete="tunnel",
     help="ports to forward (default: [tunnel] ports in the project's tn.toml)")
@arg("--public", action="store_true",
     help="anyone with the link gets in (default: private, needs the same account)")
@arg("--for", dest="duration", metavar="DURATION",
     help="close it after 90s, 30m, 2h, 1d, 1h30m, ...")
def open_(ctx, args) -> int:
    need("devtunnel", fix="dot apply vscode")
    require_login()
    if args.port:
        ports = [parse_port(p) for p in args.port]
    else:
        proj = ctx.config.project if ctx.project else None
        ports = [parse_port(p) for p in (proj.tunnel_ports if proj else [])]
        if not ports:
            if ctx.project_dir is not None:
                raise UsageError("no port given and no [tunnel] ports in %s"
                                 % home_short(ctx.project_dir / "tn.toml"))
            raise UsageError("no port given (and not in a project whose tn.toml has "
                             "[tunnel] ports)")
    ports = list(dict.fromkeys(ports))
    seconds = parse_duration(args.duration) if args.duration is not None else None
    access = "public" if args.public else "private"

    records = []
    errors = []
    for port in ports:
        try:
            records.append(_open_one(ctx, port, access, seconds))
        except Fail as e:
            if len(ports) == 1:
                raise
            errors.append(port)
            out.error("tn: port %d: %s" % (port, e.message))
            records.append({"port": port, "url": None, "access": access, "pid": None,
                            "started": None, "expires": None,
                            "label": ctx.tunnel_label(port), "context": ctx.name,
                            "reused": False, "error": e.message})
    out.result(records, lambda rs: [r["url"] for r in rs if r["url"]] or None)
    return 1 if errors else 0


def _open_one(ctx, port: int, access: str, seconds: int | None) -> dict:
    st = live(port)
    if st is not None:
        out.info("port %d is already forwarded (%s)" % (port, st.get("access")))
        if access == "public" and st.get("access") != "public":
            out.warn("port %d stays private: tn tunnel close %d, then open it with --public"
                     % (port, port))
        if seconds is not None:
            _set_expiry(st, seconds)
            out.info("closes in %s" % clock.fmt_duration(seconds))
        if not st.get("url"):
            out.hint("no link recorded yet: see %s" % home_short(_log_path(port)))
        return _record(st, True)

    if not listening(port):
        out.warn("nothing is listening on %d yet - the link will 502 until something starts "
                 "there" % port)
    log = _log_path(port)
    fs.mkdir(tunnels_dir())
    fs.write_text(log, "")
    argv = ["devtunnel", "host", "-p", str(port)]
    if access == "public":
        argv.append("--allow-anonymous")
    pid = spawn_detached(argv, cwd=tunnels_dir(), log=log)   # never the caller's cwd
    st = {"port": port, "pid": pid or None, "url": None, "access": access,
          "started": clock.iso(clock.now()), "expires": None,
          "label": ctx.tunnel_label(port), "context": ctx.name, "dir": str(ctx.path),
          "log": str(log), "watcher_pid": None}
    if _dry_run():
        if seconds is not None:
            st["expires"] = clock.iso(clock.now() + seconds)
            out.would("start a watcher that closes port %d in %s"
                      % (port, clock.fmt_duration(seconds)))
        return _record(st, False)
    _write(st)

    deadline = _monotonic() + TIMEOUT_SECONDS
    while True:
        url = url_in_log(port)
        if url:
            break
        if not _alive(pid):
            try:
                text = log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            for line in text.splitlines():
                out.error("  " + line)
            _unlink(_json_path(port))
            raise Fail("devtunnel exited before it published a link for port %d" % port,
                       hint="the log is kept: %s" % home_short(log))
        if _monotonic() >= deadline:
            raise Fail("gave up after %ds; still running: see %s, or tn tunnel close %d"
                       % (TIMEOUT_SECONDS, home_short(log), port))
        _sleep(POLL_SECONDS)

    st["url"] = url
    _write(st)
    if seconds is not None:
        _set_expiry(st, seconds)
    out.info(_access_line(st))
    if seconds is not None:
        out.info("closes in %s" % clock.fmt_duration(seconds))
    return _record(st, False)


def _row(st: dict) -> dict:
    started = clock.parse_iso(st.get("started"))
    return {"port": int(st["port"]), "access": st.get("access"),
            "age_seconds": clock.age_seconds(started), "expires": st.get("expires"),
            "label": st.get("label"), "context": st.get("context"), "url": st.get("url"),
            "pid": st.get("pid"), "started": st.get("started"), "dir": st.get("dir"),
            "log": st.get("log")}


def _expires_text(iso: str | None) -> str:
    exp = clock.parse_iso(iso)
    if exp is None:
        return "-"
    return "in " + clock.fmt_duration(max(0, exp - clock.now()))


@plugin.command(name="ls", help="list the open port forwards")
def ls_(ctx, args) -> int:
    rows = [_row(s) for s in live_tunnels(enforce_expiry=True)]
    out.records(rows, [("port", "PORT"), ("access", "ACCESS"),
                       ("age_seconds", "AGE", clock.fmt_age),
                       ("expires", "EXPIRES", _expires_text), ("label", "LABEL"),
                       ("context", "CONTEXT"), ("url", "LINK")],
                empty="No tunnels. Open one with: tn tunnel open <port>")
    return 0


def _pick_label(st: dict) -> str:
    return "%s  %s  %s" % (st["port"], st.get("access") or "-", st.get("url") or "-")


@plugin.command(help="stop port forwards and delete their tunnels (the link is gone for good)")
@arg("port", nargs="*", complete="tunnel", help="ports to close (default: pick one)")
@arg("--all", action="store_true", help="close every open forward")
@arg("--when-expired", action="store_true", help=argparse.SUPPRESS)
def close(ctx, args) -> int:
    if args.when_expired:
        return _watch(args.port)
    if args.all and args.port:
        raise UsageError("give ports or --all, not both")
    missing: list = []
    if args.all:
        targets = live_tunnels()
        if not targets:
            out.info("No tunnels to close")
            out.result([])
            return 0
    elif args.port:
        targets = []
        for p in dict.fromkeys(parse_port(p) for p in args.port):
            st = live(p)
            if st is None:
                missing.append(p)
            else:
                targets.append(st)
        if missing and not targets:
            raise Fail("port %s is not forwarded" % ", ".join(str(p) for p in missing))
        for p in missing:
            out.error("tn: port %d is not forwarded" % p)
    else:
        candidates = live_tunnels()
        if not candidates:
            out.info("No tunnels to close")
            out.result([])
            return 0
        targets = [pick(candidates, label=_pick_label, prompt="close", what="which tunnel?")]
    records = []
    for st in targets:
        out.info("closing port %d (pid %s)" % (int(st["port"]), st.get("pid")))
        close_tunnel(st)
        records.append({"port": int(st["port"]), "url": st.get("url"), "closed": True})
    out.info("the link is gone for good: a new open gets a new URL")
    out.result(records)
    return 1 if missing else 0


def _watch(ports: list) -> int:
    """The --for watcher: sleep until the expiry recorded now, then close the tunnel, but only
    while its pid and expiry are still the ones this watcher was started for."""
    if len(ports) != 1:
        raise UsageError("--when-expired takes exactly one port")
    port = parse_port(ports[0])
    first = _read(port)
    if first is None or not first.get("expires"):
        return 0
    pid, expires = first.get("pid"), first.get("expires")
    while True:
        st = live(port)
        if st is None or st.get("pid") != pid or st.get("expires") != expires:
            return 0
        exp = clock.parse_iso(expires)
        if exp is None:
            return 0
        remaining = exp - clock.now()
        if remaining <= 0:
            out.info("tn: port %d expired at %s, closing" % (port, expires))
            st["watcher_pid"] = None      # that is this process: do not kill it
            close_tunnel(st)
            return 0
        _watch_sleep(min(remaining, WATCH_MAX_SLEEP))


# -- hooks -----------------------------------------------------------------------------------


@plugin.status
def tunnels_open(ctx):
    rows = live_tunnels(enforce_expiry=True)
    if not rows:
        return None
    parts = []
    for st in rows:
        age = clock.fmt_age(clock.age_seconds(clock.parse_iso(st.get("started"))))
        parts.append("%s %s (%s, %s)" % (st["port"], st.get("url") or "-", st.get("access"), age))
    return "%d open: %s" % (len(rows), "; ".join(parts))


@plugin.check
def devtunnel_installed(ctx):
    """devtunnel installed"""
    return home_short(need("devtunnel", fix="dot apply vscode"))


@plugin.check
def devtunnel_logged_in(ctx):
    """devtunnel logged in"""
    if not shutil.which("devtunnel"):
        raise Problem("devtunnel logged in: not checked, devtunnel is not installed",
                      fix="dot apply vscode", level="warn")
    text = _login_text()
    if "not logged in" in text.lower():
        raise Problem("devtunnel not logged in (separate from `code tunnel user login`)",
                      fix="devtunnel user login -g")
    if not text:
        raise Problem("devtunnel logged in: `devtunnel user show` printed nothing",
                      fix="devtunnel user login -g", level="warn")
    return "%s (separate from `code tunnel user login`)" % text.splitlines()[0]


@plugin.completer("tunnel")
def complete_tunnel(ctx, prefix):
    return [(str(s["port"]), s.get("url") or "-") for s in live_tunnels()
            if str(s["port"]).startswith(prefix)]
