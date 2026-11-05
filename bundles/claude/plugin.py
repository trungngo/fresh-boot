"""tn plugin for the claude bundle: Claude Code sessions in tmux, for Remote Control
(docs/tn.md §7.2). It replaces claude-start, -stop, -list, -attach, -login and their helpers
_claude_sessions.py, _claude_trust.py and _session_name.py.

A session is an ordinary interactive ``claude`` inside a detached tmux session, not ``--bg``:
a ``--bg`` session goes offline in the desktop app after a long idle stretch, while one in tmux
has a live terminal behind it and stays up until it is stopped. tn marks the tmux sessions it
creates with options, which is how ``ls``, ``attach``, ``stop`` and ``tn sessions`` find them
(other tmux sessions, and a claude you are sitting in, are never listed)::

    @claude_name   the title ("Acme Shop Web #U1-02"), shown in the desktop app
    @claude_dir    the directory it runs in (the git root)
    @claude_uuid   the conversation, pinned with --session-id, so --resume can find it later
    @tn_context    the display name ("acme/shop-web@02"), "" outside the roots
    @tn_kind       "claude"

Windows has no tmux. There ``start`` opens the session in a new Windows Terminal tab (a
``cmd`` window without ``wt``) and the tab IS the session: close it and the session is gone.
tn keeps a small registry (``~/.claude/tn-sessions.json``) so ``ls`` still lists a closed one,
``attach`` reopens it with ``--resume``, and ``stop`` ends the claude process and forgets it.

With tmux the same registry is what ``resume`` reads once a tmux session is gone (a reboot takes
the options with it): ``start`` records each session and the account it runs on, ``stop`` marks
it stopped, and ``ls`` adopts live sessions started before the registry existed. ``resume``
then tells a session that died (crash, reboot, account switch) from one that was ended on
purpose (``tn claude stop``, ``/exit``, archived in the app) and wakes only the first kind.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import time
import uuid as uuidlib
from pathlib import Path
from types import SimpleNamespace

from tn import (Cancelled, Context, Fail, Missing, Plugin, Problem, Session, TnError, UsageError,
                arg, capture, clock, confirm, fs, handoff, match, need, out, pick, pid_alive, run,
                slugify)
from tn.output import home_short
from tn.plugins import projects

plugin = Plugin("claude", help="Claude Code sessions in tmux, for Remote Control",
                requires=["projects"])

IS_WINDOWS = os.name == "nt"

# Seconds `start` waits before checking Claude did not die on startup (tests set it to 0).
START_WAIT = 2.0
# Seconds `restart` waits for the stopped claude to exit before resuming its conversation.
STOP_WAIT = 5.0

# The `tn` shell function sets these for tn alone. A tmux server tn starts (and every shell and
# Claude under it) must not inherit them: TN_CD_FILE names a temp file the function deletes, so
# a later `tn cd` there would write into it and change nothing, and TN_SHELL=1 would make
# `tn doctor` report shell integration that is not loaded.
SCRUB_ENV = {"TN_CD_FILE": None, "TN_SHELL": None}


def _scrub_env() -> dict:
    """SCRUB_ENV plus the markers a Claude Code session sets for its own children (CLAUDECODE,
    CLAUDE_CODE_CHILD_SESSION, CLAUDE_CODE_SESSION_ID, ...). A claude started by tn from inside
    another claude must not inherit them: CLAUDE_CODE_CHILD_SESSION turns its transcript off, so
    the session could never be resumed."""
    env = dict(SCRUB_ENV)
    for k in os.environ:
        if k.upper() in ("CLAUDECODE", "CLAUDE_PID") or k.upper().startswith("CLAUDE_CODE_"):
            env[k] = None
    return env

# tmux list-sessions fields, tab-separated. Sessions without @claude_name are not ours.
FIELDS = ("#{session_name}", "#{@claude_name}", "#{@claude_uuid}", "#{@claude_dir}",
          "#{session_created}", "#{session_attached}", "#{@tn_context}")

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
HEXISH_RE = re.compile(r"^[0-9a-f][0-9a-f-]*$", re.I)

EMPTY = "No Claude sessions in tmux. Start one with: tn claude start [target]"


# == small helpers ==========================================================================


def _need_tmux() -> str:
    """The tmux binary; "" on Windows, where sessions are terminal tabs and need none."""
    if IS_WINDOWS:
        return ""
    return need("tmux", fix="dot apply tmux")


def _need_claude() -> str:
    return need("claude", fix="dot apply claude")


def _tmux_has(tmux: str, name: str) -> bool:
    return capture([tmux, "has-session", "-t", "=" + name], timeout=10).returncode == 0


def transcript_dir(directory) -> Path:
    """``~/.claude/projects/<dir with every character outside [A-Za-z0-9] as '-'>``."""
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(directory))


def latest_uuid(directory) -> str | None:
    """The uuid of the newest ``*.jsonl`` transcript for ``directory``, or None."""
    d = transcript_dir(directory)
    try:
        files = [p for p in d.iterdir() if p.suffix == ".jsonl" and p.is_file()]
    except OSError:
        return None
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime).stem


def agents() -> list:
    """``claude agents --json`` as a list of dicts; [] when claude is absent or says nothing
    useful. The registry keeps entries for dead processes: check ``pid`` before trusting it."""
    if not shutil.which("claude"):
        return []
    r = capture(["claude", "agents", "--json"], timeout=15)
    if r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout or "null")
    except ValueError:
        return []
    return [a for a in data if isinstance(a, dict)] if isinstance(data, list) else []


def live_pid(uuid: str, agent_rows: list | None = None) -> int | None:
    """The pid of a live claude process on conversation ``uuid`` (from ``claude agents``).

    A missing or non-positive pid is skipped: kill(-1, 0) always succeeds."""
    for a in agent_rows if agent_rows is not None else agents():
        pid = a.get("pid")
        if a.get("sessionId") != uuid or isinstance(pid, bool) or not isinstance(pid, int):
            continue
        if pid > 0 and pid_alive(pid):
            return pid
    return None


# == Windows: terminal tabs and a registry ==================================================


def registry_path() -> Path:
    return Path.home() / ".claude" / "tn-sessions.json"


def _registry() -> list:
    try:
        data = json.loads(registry_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("name") and e.get("uuid")] \
        if isinstance(data, list) else []


def _registry_save(entries: list) -> None:
    fs.write_text(registry_path(), json.dumps(entries, indent=2) + "\n")


def _record(entry: dict) -> None:
    """Remember a session tn started, replacing any entry with the same name or uuid."""
    entries = [e for e in _registry() if e["name"] != entry["name"] and e["uuid"] != entry["uuid"]]
    entries.append(entry)
    _registry_save(entries)


def _registry_rows() -> list:
    """The registry as ``_tmux_rows`` rows. ``attached`` means the claude process is alive."""
    entries = _registry()
    if not entries:
        return []
    live = agents()
    return [[e["name"], e.get("title") or e["name"], e["uuid"], e.get("dir") or "",
             str(int(e.get("created") or 0)), "1" if live_pid(e["uuid"], live) else "0",
             e.get("context") or ""] for e in entries]


def _open_tab(title: str, directory, claude_bin: str, cargs: list, machine: str | None) -> None:
    """Start claude in a new Windows Terminal tab, or a cmd window when ``wt`` is missing."""
    env = _scrub_env()
    if machine:
        env["MY_MACHINE"] = machine
    wt = shutil.which("wt")
    if wt:
        argv = [wt, "-w", "0", "new-tab", "--suppressApplicationTitle", "--title", title,
                "-d", str(directory), "--", claude_bin, *cargs]
    else:
        argv = ["cmd", "/c", "start", "", "/D", str(directory), claude_bin, *cargs]
    run(argv, quiet=True, env=env)


def _wait_live(uuid: str) -> int | None:
    """Poll ``claude agents`` for the new claude; it registers a moment after the tab opens."""
    deadline = time.monotonic() + START_WAIT * 5
    while True:
        pid = live_pid(uuid)
        if pid or time.monotonic() >= deadline:
            return pid
        time.sleep(1)


def _tmux_rows() -> list:
    """Raw rows of the tmux sessions carrying @claude_name; [] without tmux or a server."""
    if IS_WINDOWS:
        return _registry_rows()
    if not shutil.which("tmux"):
        return []
    r = capture(["tmux", "list-sessions", "-F", "\t".join(FIELDS)], timeout=10)
    if r.returncode != 0:          # "no server running" is an empty list, not an error
        return []
    rows = []
    for line in (r.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) == len(FIELDS) and parts[1]:
            rows.append(parts)
    return rows


def _context_of(ctx: Context, directory: str | None, recorded: str | None) -> str | None:
    """The display name tn recorded at start; for older sessions, derived from the dir."""
    if recorded:
        return recorded
    if not directory:
        return None
    try:
        return ctx.for_path(directory).name
    except Exception:  # noqa: BLE001 - a bad tn.toml there must not break a listing
        return None


def list_sessions(ctx: Context, *, status: bool = True) -> list:
    """The ``tn claude ls`` rows, oldest first. ``status=False`` skips ``claude agents``."""
    raw = _tmux_rows()
    if not raw:
        return []
    by_uuid = {}
    if status:
        by_uuid = {a.get("sessionId"): a.get("status") for a in agents()}
    rows = []
    for tmux_name, name, uuid, directory, created, attached, context in raw:
        try:
            started = float(int(created))
        except ValueError:
            started = None
        try:
            is_attached = int(attached or "0") > 0
        except ValueError:
            is_attached = None
        rows.append({
            "tmux": tmux_name,
            "name": name,
            "context": _context_of(ctx, directory, context),
            "status": (by_uuid.get(uuid) or None) if uuid else None,
            "age_seconds": clock.age_seconds(started),
            "attached": is_attached,
            "dir": directory or None,
            "uuid": uuid or None,
            "started": clock.iso(started),
            "_started": started,
        })
    rows.sort(key=lambda r: (r["_started"] or 0, r["tmux"]))
    return rows


def _public(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _attach_argv(tmux_name: str) -> list:
    if IS_WINDOWS:
        return ["tn", "claude", "attach", tmux_name]
    verb = "switch-client" if os.environ.get("TMUX") else "attach-session"
    return ["tmux", verb, "-t", "=" + tmux_name]


def resume_command(row: dict) -> str:
    """``tn claude start <dir> --resume <uuid>``: what brings a stopped session back."""
    cmd = "tn claude start %s --resume" % shlex.quote(row.get("dir") or ".")
    if row.get("uuid"):
        cmd += " " + row["uuid"]
    return cmd


def _session_keys(row: dict) -> list:
    return [row.get("tmux"), row.get("name"), row.get("context"), row.get("uuid")]


def _choose(rows: list, name: str | None, *, prompt: str) -> dict:
    """One session: matched by tmux name, title, context or uuid prefix, else picked."""
    cands = match(name, rows, _session_keys)
    if not cands:
        raise UsageError('no Claude session matches "%s"' % name,
                         choices=[r["tmux"] for r in rows])
    return pick(cands, label=lambda r: "%s  %s" % (r["tmux"], r["name"]), prompt=prompt,
                what="which session?")


# == trust ==================================================================================


def claude_json() -> Path:
    return Path.home() / ".claude.json"


def project_key(directory) -> str:
    """The ``projects`` key Claude Code uses for ``directory`` in ~/.claude.json: the absolute
    path, with forward slashes on Windows (``C:/Users/alex/repo``). A backslash key is never
    read, so the trust prompt would still come up."""
    key = str(directory)
    return key.replace("\\", "/") if IS_WINDOWS else key


def is_trusted(directory) -> bool:
    try:
        data = json.loads(claude_json().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    entry = (data.get("projects") or {}).get(project_key(directory))
    return isinstance(entry, dict) and entry.get("hasTrustDialogAccepted") is True


def _need_onboarded() -> None:
    """Exit 3 unless Claude Code finished its first-run setup here (theme, login method).

    Until ``hasCompletedOnboarding`` is set in ~/.claude.json, claude opens those screens
    before anything else, Remote Control included, and a detached session sits on them with
    nobody to answer: it stays up, so the startup check cannot tell. An unreadable file is
    left to ``trust`` to report."""
    try:
        data = json.loads(claude_json().read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except (OSError, ValueError):
        return
    if isinstance(data, dict) and data.get("hasCompletedOnboarding") is not True:
        raise Missing("Claude Code has not been set up on this machine: a detached session "
                      "would wait at its first-run screens; finish them once in a terminal, "
                      "then exit", "claude")


def trust(directory) -> bool:
    """Mark ``directory`` trusted in ~/.claude.json, as the startup prompt does. Returns
    whether anything changed.

    Claude Code gates a workspace's own configuration (its skills, and plugin bundles vendored
    under .claude/skills/) on ``projects.<abs path>.hasTrustDialogAccepted``, silently. The
    prompt that sets it is interactive, which a detached session can never answer. Trust is
    read at process start. Every running Claude holds this file in memory and writes it back
    whole, so a concurrent write can lose this one: the rewrite is atomic, not clobber-proof.
    """
    path = claude_json()
    key = project_key(directory)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = None                  # never ran Claude Code here: Claude fills in the rest
    except OSError as e:
        raise Fail("cannot read %s: %s" % (home_short(path), e))
    if text is None or not text.strip():
        data: dict = {}
    else:
        try:
            data = json.loads(text)
        except ValueError as e:
            raise Fail("%s is not valid JSON (%s); not touching it" % (home_short(path), e))
        if not isinstance(data, dict):
            raise Fail("%s is not a JSON object; not touching it" % home_short(path))
    projects_map = data.setdefault("projects", {})
    if not isinstance(projects_map, dict):
        raise Fail("%s: \"projects\" is not an object; not touching it" % home_short(path))
    entry = projects_map.setdefault(key, {})
    if not isinstance(entry, dict):
        raise Fail("%s: projects[%s] is not an object; not touching it"
                   % (home_short(path), key))
    if entry.get("hasTrustDialogAccepted") is True:
        return False
    entry["hasTrustDialogAccepted"] = True
    fs.write_text(path, json.dumps(data, indent=2) + "\n")
    return True


# == login status ===========================================================================


def auth_status() -> dict:
    """``claude auth status --json``: {"logged_in", "email", "auth_method", "subscription"}.

    Its exit code is 0 either way, so ``loggedIn`` is the only signal. ``known`` is False
    when the output could not be read."""
    r = capture(["claude", "auth", "status", "--json"], timeout=20)
    try:
        d = json.loads(r.stdout or "")
    except ValueError:
        d = None
    if not isinstance(d, dict):
        return {"logged_in": False, "email": None, "auth_method": None, "subscription": None,
                "known": False}
    return {"logged_in": bool(d.get("loggedIn")), "email": d.get("email") or None,
            "auth_method": d.get("authMethod") or None,
            "subscription": d.get("subscriptionType") or None, "known": True}


def _auth_text(st: dict) -> str:
    if not st.get("known"):
        return "unknown (could not read `claude auth status --json`)"
    if not st["logged_in"]:
        return "not signed in"
    text = st["email"] or "signed in"
    if st["auth_method"]:
        text += " via %s" % st["auth_method"]
    if st["subscription"]:
        text += " (%s)" % st["subscription"]
    return text


# == commands ===============================================================================


def _complete_sessions(ctx, prefix):
    return [(r["tmux"], r["name"]) for r in list_sessions(ctx, status=False)]


def _resume_arg(args) -> str | None:
    """--resume: None, "latest" or a full uuid. ``--resume <target>`` (no uuid, target not
    given yet) is read as ``--resume <target>``: argparse would otherwise eat the target."""
    value = args.resume
    if value is None or value == "latest":
        return value
    value = value.strip()
    if UUID_RE.match(value):
        return value.lower()
    if args.target is None and not HEXISH_RE.match(value):
        args.target = value
        return "latest"
    raise UsageError("--resume takes the full uuid (the transcript file name), not %r" % value,
                     hint="ls -t %s" % home_short(Path.home() / ".claude" / "projects"))


@plugin.command(help="start a Claude session in tmux, here or in a target")
@arg("target", nargs="?", complete="target",
     help="project, project/repo[@ws], repo, client/engagement or a directory (default: here)")
@arg("--ws", metavar="NN|new", complete="ws",
     help="run in that parallel workspace; new creates the next src-NN first")
@arg("--resume", nargs="?", const="latest", metavar="ID",
     help="resume a conversation: its full uuid, or the newest one there with no ID")
@arg("--name", metavar="NAME", help="the session title (default: derived from the layout)")
@arg("--no-trust", action="store_true",
     help="do not mark the directory trusted in ~/.claude.json")
def start(ctx, args):
    """start a Claude session in tmux, here or in a target"""
    return _start(ctx, args)


def _start(ctx, args, force=None):
    out.result(_launch(ctx, args, force), text=lambda r: r["tmux"])


def _launch(ctx, args, force=None) -> dict:
    """``start`` without printing its result; ``force=(title, tmux name)`` is ``restart`` or
    ``resume`` bringing a session back under its old names (in a dry run the old tmux session
    may still be there)."""
    dry_restart = force is not None and ctx.options.dry_run
    tmux = _need_tmux()
    claude_bin = _need_claude()
    _need_onboarded()
    resume = _resume_arg(args)
    if args.name is not None and not args.name.strip():
        raise UsageError("--name is empty")

    where = projects.resolve(ctx, args.target, ws=args.ws, prefer_repo=True)
    path = Path(where.path)
    directory = where.git_root or path
    if directory != path:
        out.info("(git root of %s)" % home_short(path))
    rctx = where.ctx if directory == path else ctx.for_path(directory)

    if force:
        title, tmux_name = force
    elif args.name:
        title = " ".join(args.name.split())
        tmux_name = "claude-" + (slugify(title) or "session")
    else:
        title = rctx.label()              # exit 3 without MY_MACHINE (§3.4)
        tmux_name = rctx.session("claude")

    if IS_WINDOWS:
        taken = any(r[0] == tmux_name for r in _tmux_rows())
    else:
        taken = _tmux_has(tmux, tmux_name)
    if taken and not dry_restart:
        raise Fail("already running in tmux session %s" % tmux_name,
                   fix="tn claude attach %s" % tmux_name)

    if resume == "latest":
        uuid = latest_uuid(directory)
        if uuid is None:
            raise Fail("no conversation to resume in %s" % home_short(transcript_dir(directory)))
    elif resume is not None:
        uuid = resume
    else:
        uuid = str(uuidlib.uuid4())

    for row in _tmux_rows():
        if row[2] == uuid and not dry_restart:
            raise Fail("conversation %s is already running" % uuid,
                       fix="tn claude attach %s" % row[0])
    if resume is not None and not dry_restart:
        # The newest transcript is often a claude someone is sitting in right now, outside
        # tmux. Two processes on one transcript corrupt it.
        pid = live_pid(uuid)
        if pid:
            raise Fail("conversation %s is running outside tmux (pid %d); exit it first"
                       % (uuid, pid))

    trust_on = not args.no_trust and ctx.config.get("claude.trust") is not False
    changed = False
    if trust_on:
        changed = trust(directory)       # before Claude starts: trust is read at startup
        if changed and not ctx.options.dry_run:
            out.info("trusted %s" % home_short(directory))
    trusted = trust_on or is_trusted(directory)

    cargs = ["--resume", uuid] if resume is not None else ["--session-id", uuid]
    cargs += ["--remote-control", title, "-n", title]
    if IS_WINDOWS:
        return _start_tab(ctx, rctx, title, tmux_name, uuid, directory, claude_bin, cargs,
                          resumed=resume is not None, trusted=trusted, changed=changed,
                          created=where.workspace_created)
    # A running tmux server gives new sessions ITS environment, so PATH and MY_MACHINE go in
    # with -e. The options are chained into the same call so they land even if Claude dies.
    argv = [tmux, "new-session", "-d", "-s", tmux_name, "-c", str(directory),
            "-e", "PATH=" + os.environ.get("PATH", "")]
    machine = rctx.machine
    if machine:
        argv += ["-e", "MY_MACHINE=" + machine]
    # Each option names the new session: with no -t, tmux sets it on the session tn runs in. The
    # colon matters too: set-option's target is a pane, and a bare "=name" finds nothing.
    target = "=%s:" % tmux_name
    argv += [claude_bin, *cargs,
             ";", "set-option", "-t", target, "@claude_name", title,
             ";", "set-option", "-t", target, "@claude_dir", str(directory),
             ";", "set-option", "-t", target, "@claude_uuid", uuid,
             ";", "set-option", "-t", target, "@tn_context", rctx.name or "",
             ";", "set-option", "-t", target, "@tn_kind", "claude"]
    run(argv, quiet=True, env=_scrub_env())

    if not ctx.options.dry_run:
        # Claude exiting takes the tmux session with it: a bad flag or a failed resume shows
        # up as the session being gone a moment later.
        if START_WAIT:
            time.sleep(START_WAIT)
        if not _tmux_has(tmux, tmux_name):
            raise Fail("claude exited straight away; run it by hand to see why:",
                       fix="cd %s && claude %s" % (shlex.quote(str(directory)),
                                                   shlex.join(cargs)))
        _record({"name": tmux_name, "title": title, "uuid": uuid, "dir": str(directory),
                 "context": rctx.name or "", "created": int(clock.now()),
                 "account": _account()})
        out.info("Directory: %s" % home_short(directory))
        out.info("Name:      %s" % title)
        out.info("Tmux:      %s" % tmux_name)
        out.info("Session:   %s" % uuid)
        out.info("attach: tn claude attach %s" % tmux_name)

    return {"tmux": tmux_name, "name": title, "uuid": uuid, "dir": str(directory),
            "context": rctx.name, "resumed": resume is not None, "trusted": trusted,
            "trust_changed": changed, "workspace_created": where.workspace_created}


def _start_tab(ctx, rctx, title, name, uuid, directory, claude_bin, cargs, *, resumed,
               trusted, changed, created) -> dict:
    """The Windows half of ``start``: open the tab, then record it in the registry."""
    _open_tab(title, directory, claude_bin, cargs, rctx.machine)
    if not ctx.options.dry_run:
        _record({"name": name, "title": title, "uuid": uuid, "dir": str(directory),
                 "context": rctx.name or "", "created": int(time.time())})
        if _wait_live(uuid) is None:
            out.info("(could not confirm claude is running; look at the new terminal tab)")
        out.info("Directory: %s" % home_short(directory))
        out.info("Name:      %s" % title)
        out.info("Tab:       %s" % name)
        out.info("Session:   %s" % uuid)
        out.info("closing the tab ends the session; reopen it with: tn claude attach %s" % name)
    return {"tmux": name, "name": title, "uuid": uuid, "dir": str(directory),
            "context": rctx.name, "resumed": resumed, "trusted": trusted,
            "trust_changed": changed, "workspace_created": created}


@plugin.command(name="ls", help="Claude sessions running in tmux")
def ls_(ctx, args):
    """Claude sessions running in tmux"""
    _need_tmux()
    rows = list_sessions(ctx)
    _adopt(ctx, rows)
    rows = [_public(r) for r in rows]
    out.records(rows, [("tmux", "TMUX"), ("name", "NAME"), ("context", "CONTEXT"),
                       ("status", "STATUS"), ("age_seconds", "AGE", clock.fmt_age),
                       ("attached", "ATTACHED"), ("dir", "DIRECTORY", home_short)],
                empty=EMPTY)


@plugin.command(help="attach this terminal to a session (detach with C-a d)")
@arg("name", nargs="?", complete=_complete_sessions,
     help="tmux name, title, context or uuid prefix (default: pick)")
def attach(ctx, args):
    """attach this terminal to a session (detach with C-a d)"""
    tmux = _need_tmux()
    rows = list_sessions(ctx, status=False)
    if not rows:
        raise Fail("no Claude sessions in tmux", hint="start one with: tn claude start [target]")
    row = _choose(rows, args.name, prompt="attach")
    if IS_WINDOWS:
        return _reopen_tab(ctx, row)
    out.info("attaching to %s (%s)" % (row["name"], row["tmux"]))
    argv = _attach_argv(row["tmux"])
    handoff([tmux] + argv[1:], env=_scrub_env())


def _reopen_tab(ctx, row: dict):
    """Windows ``attach``: a session still running has its tab open (tn cannot raise it); one
    whose tab was closed is resumed in a fresh tab."""
    if row["attached"]:
        raise Fail("%s is already open in a terminal tab" % row["tmux"],
                   hint="tn cannot bring a tab forward; find it by its title: %s" % row["name"],
                   fix="tn claude stop %s, then attach, to move it to a new tab" % row["tmux"])
    directory = row.get("dir")
    if not directory or not row.get("uuid"):
        raise Fail("%s has no directory or conversation recorded" % row["tmux"])
    out.info("reopening %s (%s)" % (row["name"], row["tmux"]))
    _open_tab(row["name"], directory, _need_claude(),
              ["--resume", row["uuid"], "--remote-control", row["name"], "-n", row["name"]],
              ctx.machine)
    return 0


@plugin.command(help="stop a session (the conversation is kept; --all stops every one)")
@arg("name", nargs="?", complete=_complete_sessions,
     help="tmux name, title, context or uuid prefix (default: pick)")
@arg("--all", action="store_true", help="stop every Claude session in tmux (confirms)")
def stop(ctx, args):
    """stop a session (the conversation is kept; --all stops every one)"""
    tmux = _need_tmux()
    if args.all and args.name:
        raise UsageError("give a session name or --all, not both")
    rows = list_sessions(ctx, status=False)
    if not rows:
        out.info("No Claude sessions in tmux to stop.")
        out.result([])
        return 0
    if args.all:
        if not confirm("stop all %d Claude session%s? (their conversations are kept)"
                       % (len(rows), "" if len(rows) == 1 else "s")):
            raise Cancelled()
        chosen = rows
    else:
        chosen = [_choose(rows, args.name, prompt="stop")]
    stopped = []
    for row in chosen:
        _kill(tmux, row)
        if not ctx.options.dry_run:
            out.info("stopped %s (%s)" % (row["name"], row["tmux"]))
        stopped.append({"tmux": row["tmux"], "name": row["name"], "uuid": row["uuid"],
                        "dir": row["dir"], "resume": resume_command(row)})
    if not IS_WINDOWS and not ctx.options.dry_run:
        _mark_stopped(ctx, chosen)
    out.result(stopped, text=lambda rs: ["resume: " + r["resume"] for r in rs])


def _mark_stopped(ctx, rows: list) -> None:
    """Note in the registry that tn stopped these on purpose: ``resume --all`` leaves them."""
    _adopt(ctx, rows)
    names = {r["tmux"] for r in rows}
    now = int(clock.now())
    entries = _registry()
    for e in entries:
        if e["name"] in names:
            e["stopped"] = now
    _registry_save(entries)


def _kill(tmux: str, row: dict) -> None:
    if IS_WINDOWS:
        _stop_tab(row)
    else:
        run([tmux, "kill-session", "-t", "=" + row["tmux"]], quiet=True)


@plugin.command(help="stop a session and start it again on the same conversation")
@arg("name", nargs="?", complete=_complete_sessions,
     help="tmux name, title, context or uuid prefix (default: pick)")
def restart(ctx, args):
    """stop a session and start it again on the same conversation"""
    tmux = _need_tmux()
    rows = list_sessions(ctx, status=False)
    if not rows:
        raise Fail("no Claude sessions in tmux", hint="start one with: tn claude start [target]")
    row = _choose(rows, args.name, prompt="restart")
    if not row.get("uuid") or not row.get("dir"):
        raise Fail("%s has no conversation or directory recorded" % row["tmux"],
                   hint="stop it and start a new one: tn claude stop %s" % row["tmux"])
    _need_claude()
    out.result(_relaunch(ctx, tmux, row), text=lambda r: r["tmux"])


def _relaunch(ctx, tmux: str, row: dict) -> dict:
    """Kill the tmux session of ``row`` and resume its conversation under the same names."""
    _kill(tmux, row)
    if not ctx.options.dry_run:
        out.info("stopped %s (%s)" % (row["name"], row["tmux"]))
        # Two processes on one transcript corrupt it: wait for the old claude to be gone.
        for _ in range(int(STOP_WAIT * 5)):
            if not live_pid(row["uuid"]):
                break
            time.sleep(0.2)
    try:
        return _launch(ctx, _resume_ns(row), force=(row["name"], row["tmux"]))
    except Fail:
        out.info("%s is stopped; bring it back with: %s" % (row["tmux"], resume_command(row)))
        raise


def _resume_ns(row: dict) -> SimpleNamespace:
    """``start`` arguments that resume ``row``'s conversation in its directory."""
    return SimpleNamespace(target=row["dir"], ws=None, resume=row["uuid"], name=None,
                           no_trust=False)


# == resume: sessions that died =============================================================

# States `resume --all` wakes. The others were ended on purpose, are running, or cannot be
# resumed: stopped (tn claude stop), exited (/exit, archived in the app), running, outside (a
# claude on that conversation runs outside tmux), missing (directory or transcript gone).
WAKE = ("crashed", "rebooted", "account")

# A session whose transcript was last written this many seconds before the boot, or later,
# died in the shutdown: it may have exited cleanly on the SIGTERM.
SHUTDOWN_WINDOW = 600


def _account() -> str | None:
    """The e-mail of the account claude is signed in as now; None when unknown."""
    st = auth_status()
    return st["email"] if st["logged_in"] else None


def _boot_time() -> float | None:
    """When this machine booted (epoch seconds); None when it cannot be read."""
    try:
        for line in Path("/proc/stat").read_text().splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    r = capture(["sysctl", "-n", "kern.boottime"], timeout=10)
    m = re.search(r"\bsec = (\d+)", r.stdout or "") if r.returncode == 0 else None
    return float(m.group(1)) if m else None


def _transcript_end(directory: str, uuid: str):
    """``(clean, mtime)`` for the conversation's transcript, or None when there is none.

    Claude writes a ``cost-state`` row as it exits: on /exit, an archive from the app, the
    SIGHUP of ``tn claude stop`` and the SIGTERM of a shutdown alike. One after the last message
    means it exited on its own; a crash or a kill -9 leaves none."""
    path = transcript_dir(directory) / (uuid + ".jsonl")
    clean = False
    try:
        mtime = path.stat().st_mtime
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    kind = json.loads(line).get("type")
                except (ValueError, AttributeError):
                    continue
                if kind == "cost-state":
                    clean = True
                elif kind in ("user", "assistant"):
                    clean = False
    except OSError:
        return None
    return clean, mtime


def _adopt(ctx, rows: list) -> None:
    """Add live tmux sessions the registry does not know (started before it existed, or by
    the old claude-start) and drop entries whose directory is gone. Not in a dry run."""
    if IS_WINDOWS or ctx.options.dry_run:
        return
    entries = _registry()
    known = {e["uuid"] for e in entries}
    keep = [e for e in entries if e.get("dir") and Path(e["dir"]).is_dir()]
    changed = len(keep) != len(entries)
    for r in rows:
        if r.get("uuid") and r.get("dir") and r["uuid"] not in known:
            keep = [e for e in keep if e["name"] != r["tmux"]]
            keep.append({"name": r["tmux"], "title": r["name"], "uuid": r["uuid"],
                         "dir": r["dir"], "context": r.get("context") or "",
                         "created": int(r.get("_started") or clock.now()), "account": None})
            changed = True
    if changed:
        _registry_save(keep)


def _classify(entry: dict, live: dict, agent_rows: list, account: str | None,
              boot: float | None) -> str:
    """The state of a registry entry (see WAKE)."""
    row = live.get(entry["name"])
    moved = bool(entry.get("account") and account and entry["account"] != account)
    if row is not None and row.get("uuid") == entry["uuid"]:
        return "account" if moved else "running"
    end = _transcript_end(entry.get("dir") or "", entry["uuid"])
    if end is None or not Path(entry.get("dir") or "").is_dir():
        return "missing"
    if live_pid(entry["uuid"], agent_rows):
        return "outside"
    if entry.get("stopped"):
        return "stopped"
    if moved:
        return "account"
    clean, mtime = end
    booted_since = bool(boot and boot > (entry.get("created") or 0))
    if booted_since and (not clean or mtime >= boot - SHUTDOWN_WINDOW):
        return "rebooted"
    return "exited" if clean else "crashed"


def resume_rows(ctx, live: list, account: str | None) -> list:
    """Every session in the registry with its ``state``, oldest first."""
    by_name = {r["tmux"]: r for r in live}
    agent_rows = agents()
    boot = _boot_time()
    rows = []
    for e in sorted(_registry(), key=lambda e: (e.get("created") or 0, e["name"])):
        row = by_name.get(e["name"])
        rows.append({"tmux": e["name"], "name": e.get("title") or e["name"], "uuid": e["uuid"],
                     "dir": e.get("dir") or None, "context": e.get("context") or None,
                     "state": _classify(e, by_name, agent_rows, account, boot),
                     "_live": row is not None and row.get("uuid") == e["uuid"]})
    return rows


def _complete_registry(ctx, prefix):
    return [(e["name"], e.get("title") or "") for e in _registry()]


@plugin.command(help="bring back sessions that died: crashed, killed by a reboot, or left on "
                     "the previous account (--all: every one)")
@arg("name", nargs="?", complete=_complete_registry,
     help="tmux name, title, context or uuid prefix (default: pick among the dead ones)")
@arg("--all", action="store_true",
     help="every session that crashed, died in a reboot or runs on the previous account")
def resume(ctx, args):
    """bring back sessions that died: crashed, killed by a reboot, or left on the previous
    account (--all: every one)"""
    if IS_WINDOWS:
        raise Fail("there is no resume on Windows: a session is its terminal tab",
                   fix="tn claude attach <name>")
    tmux = _need_tmux()
    _need_claude()
    if args.all and args.name:
        raise UsageError("give a session name or --all, not both")
    live = list_sessions(ctx, status=False)
    _adopt(ctx, live)
    st = auth_status()
    rows = resume_rows(ctx, live, st["email"] if st["logged_in"] else None)

    if args.name:
        if not rows:
            raise Fail("tn has no Claude session recorded",
                       hint="start one with: tn claude start [target]")
        row = _choose(rows, args.name, prompt="resume")
        if row["state"] == "running":
            raise Fail("%s is running" % row["tmux"], fix="tn claude attach %s" % row["tmux"])
        if row["state"] == "outside":
            raise Fail("conversation %s is running outside tmux; exit it first" % row["uuid"])
        if row["state"] == "missing":
            raise Fail("%s cannot be resumed: its directory or transcript is gone" % row["tmux"])
        chosen = [row]
    else:
        dead = [r for r in rows if r["state"] in WAKE]
        ended = [r for r in rows if r["state"] in ("stopped", "exited")]
        if ended:
            n = len(ended)
            out.info("left alone: %d session%s stopped or exited on purpose (resume one by "
                     "name: tn claude resume <name>)" % (n, "" if n == 1 else "s"))
        if not dead:
            out.info("No Claude session to resume.")
            out.result([])
            return 0
        chosen = dead if args.all else [
            pick(dead, label=lambda r: "%s  %s  (%s)" % (r["tmux"], r["name"], r["state"]),
                 prompt="resume", what="which session?")]

    if st["known"] and not st["logged_in"]:
        raise Missing("not signed in: a resumed session would wait at the login screen",
                      "tn claude login")
    results, failed = [], 0
    for row in chosen:
        base = {k: row[k] for k in ("tmux", "name", "uuid", "dir", "context", "state")}
        try:
            if row["_live"]:
                _relaunch(ctx, tmux, row)
            else:
                _launch(ctx, _resume_ns(row), force=(row["name"], row["tmux"]))
        except TnError as e:
            if len(chosen) == 1:
                raise
            failed += 1
            out.error("%s: %s" % (row["tmux"], e.message))
            results.append(dict(base, resumed=False, error=e.message))
            continue
        results.append(dict(base, resumed=True, error=None))
    out.result(results, text=lambda rs: ["%s %s (%s)" % ("resumed" if r["resumed"] else "failed",
                                                         r["tmux"], r["state"]) for r in rs])
    return 1 if failed else 0


def _stop_tab(row: dict) -> None:
    """Windows ``stop``: end the claude process tree, then forget the session."""
    pid = live_pid(row["uuid"]) if row.get("uuid") else None
    if pid:
        run(["taskkill", "/PID", str(pid), "/T", "/F"], quiet=True, check=False)
    _registry_save([e for e in _registry() if e["name"] != row["tmux"]])     # dry-run aware


@plugin.command(passthrough=True, help="sign in to Claude Code (--json: only the status)")
@arg("--console", action="store_true",
     help="Anthropic Console (API billing) instead of a Claude subscription")
@arg("--sso", action="store_true", help="force the SSO flow")
@arg("--email", metavar="ADDR", help="pre-fill the login page")
def login(ctx, args):
    """sign in to Claude Code (--json: only the status)"""
    claude_bin = _need_claude()
    st = auth_status()
    if ctx.options.json:
        out.json({k: v for k, v in st.items() if k != "known"})
        return 0
    out.info("currently: " + _auth_text(st))
    flags = []
    if args.console:
        flags.append("--console")
    if args.sso:
        flags.append("--sso")
    if args.email:
        flags += ["--email", args.email]
    flags += list(getattr(args, "rest", []) or [])
    if st["logged_in"] and not ctx.options.dry_run:
        # A needless re-login is a browser round trip and a new token.
        if not confirm("sign in again, replacing this?"):
            out.info("keeping the current login")
            return 0
    code = run([claude_bin, "auth", "login", *flags], check=False, env=_scrub_env())
    if ctx.options.dry_run:
        return 0
    out.info("now: " + _auth_text(auth_status()))
    return code


# == hooks ==================================================================================


@plugin.sessions
def _sessions(ctx):
    rows = list_sessions(ctx)
    return [Session(kind="claude", id=r["tmux"], name=r["name"], context=r["context"],
                    dir=r["dir"], started=r["_started"], attached=r["attached"],
                    status=r["status"], attach=_attach_argv(r["tmux"]),
                    extra={"uuid": r["uuid"]})
            for r in rows]


@plugin.status
def _status(ctx):
    rows = list_sessions(ctx, status=False)
    if not rows:
        return None
    n = len(rows)
    attached = len([r for r in rows if r["attached"]])
    text = "%d session%s (%d attached)" % (n, "" if n == 1 else "s", attached)
    here_dirs = {os.path.normpath(str(p)) for p in (ctx.path, ctx.git_root) if p}
    here = [r for r in rows if r["dir"] and os.path.normpath(r["dir"]) in here_dirs]
    if here:
        # Only now ask claude for idle/busy: the status line must stay fast.
        by_uuid = {a.get("sessionId"): a.get("status") for a in agents()}
        text += "; here: " + ", ".join("%s %s" % (r["tmux"], by_uuid.get(r["uuid"]) or "-")
                                       for r in here)
    return text


@plugin.check
def _claude_installed(ctx):
    """claude installed"""
    return home_short(_need_claude())


@plugin.check
def _tmux_installed(ctx):
    """tmux installed"""
    if IS_WINDOWS:
        return "not used on Windows (sessions are terminal tabs)"
    return home_short(need("tmux", fix="dot apply tmux"))


@plugin.check
def _logged_in(ctx):
    """logged in"""
    if not shutil.which("claude"):
        raise Missing("claude is not installed", "dot apply claude")
    st = auth_status()
    if not st["known"]:
        raise Problem("logged in: could not read `claude auth status --json`",
                      fix="tn claude login", level="warn")
    if not st["logged_in"]:
        raise Missing("not signed in", "tn claude login")
    return _auth_text(st)


@plugin.check
def _onboarded(ctx):
    """first-run setup done"""
    if not shutil.which("claude"):
        raise Missing("claude is not installed", "dot apply claude")
    _need_onboarded()
    return "yes"


@plugin.check
def _machine_set(ctx):
    """MY_MACHINE set"""
    if not ctx.machine:
        raise Missing("MY_MACHINE is not set: it names this machine in session titles",
                      "tn config set machine <name>")
    return ctx.machine
