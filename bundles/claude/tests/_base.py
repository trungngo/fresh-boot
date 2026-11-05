"""Shared fixtures for the claude plugin tests: stateful fake tmux and claude executables."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

from tn.plugins import claude  # noqa: E402 - tn/plugins/__init__.py maps TN_PLUGIN_PATH
from tn.testing import TnTestCase

# Epoch seconds the fake tmux stamps as session_created; tests freeze "now" an hour later.
CREATED = 1_700_000_000
NOW = CREATED + 3600

# A fake tmux keeping its sessions in <state>/tmux.json. It understands the subset tn uses:
# has-session, list-sessions -F, new-session (with ";"-chained set-option), kill-session.
# <state>/tmux-die makes the next new-session "exit straight away" (the session vanishes).
FAKE_TMUX = r'''
import re
db = state_dir / "tmux.json"
sessions = json.loads(db.read_text()) if db.exists() else {}

def target(rest):
    return rest[rest.index("-t") + 1].lstrip("=")

cmds, cur = [], []
for a in argv:
    if a == ";":
        cmds.append(cur)
        cur = []
    else:
        cur.append(a)
cmds.append(cur)
current = None
code = 0
for c in cmds:
    if not c:
        continue
    verb, rest = c[0], c[1:]
    if verb == "has-session":
        code = 0 if target(rest) in sessions else 1
        if code:
            sys.stderr.write("can't find session: %s\n" % target(rest))
    elif verb == "list-sessions":
        if not sessions:
            sys.stderr.write("no server running on /tmp/tmux-0/default\n")
            code = 1
            continue
        fmt = rest[rest.index("-F") + 1]
        for name, s in sessions.items():
            vals = {"session_name": name, "session_created": str(s["created"]),
                    "session_attached": str(s.get("attached", 0))}
            vals.update(s.get("options", {}))
            print(re.sub(r"#\{([^}]*)\}", lambda m: vals.get(m.group(1), ""), fmt))
    elif verb == "new-session":
        name = rest[rest.index("-s") + 1]
        if name in sessions:
            sys.stderr.write("duplicate session: %s\n" % name)
            sys.exit(1)
        sessions[name] = {"created": CREATED_TS, "attached": 0,
                          "dir": rest[rest.index("-c") + 1], "argv": rest, "options": {},
                          "env": {k: os.environ.get(k) for k in ("TN_CD_FILE", "TN_SHELL",
                                                                 "CLAUDECODE",
                                                                 "CLAUDE_CODE_CHILD_SESSION")}}
        current = name
    elif verb == "set-option":
        # As real tmux: no -t means the session of the client running the command, not the one
        # the chain just created; a session target needs the trailing colon.
        if "-t" in rest:
            t = rest[rest.index("-t") + 1]
            if not (t.startswith("=") and t.endswith(":")):
                sys.stderr.write("can't find pane: %s\n" % t)
                sys.exit(1)
            t = t[1:-1]
        else:
            t = os.environ.get("FAKE_TMUX_CALLER", "")
        if t not in sessions:
            sys.stderr.write("no current session: %r\n" % t)
            sys.exit(1)
        sessions[t]["options"][rest[-2]] = rest[-1]
    elif verb == "kill-session":
        t = target(rest)
        if t not in sessions:
            sys.stderr.write("can't find session: %s\n" % t)
            sys.exit(1)
        del sessions[t]
    else:
        sys.stderr.write("fake tmux: unknown command %s\n" % verb)
        sys.exit(1)
die = state_dir / "tmux-die"
if current is not None and die.exists():
    die.unlink()
    del sessions[current]
db.write_text(json.dumps(sessions))
sys.exit(code)
'''.replace("CREATED_TS", str(CREATED))

# A fake claude: `agents --json` prints <state>/agents.json (default []); `auth status --json`
# prints <state>/auth.json (default logged out); `auth login` logs in.
FAKE_CLAUDE = r'''
def read(name, default):
    p = state_dir / name
    return p.read_text() if p.exists() else default

if argv[:2] == ["agents", "--json"]:
    sys.stdout.write(read("agents.json", "[]"))
elif argv[:3] == ["auth", "status", "--json"]:
    sys.stdout.write(read("auth.json", '{"loggedIn": false}'))
elif argv[:2] == ["auth", "login"]:
    (state_dir / "login-env.json").write_text(json.dumps(
        {k: os.environ.get(k) for k in ("TN_CD_FILE", "TN_SHELL")}))
    (state_dir / "auth.json").write_text(json.dumps({
        "loggedIn": True, "email": "new@example.com", "authMethod": "claude.ai",
        "subscriptionType": "max"}))
    print("Login successful.")
else:
    sys.stderr.write("fake claude: unexpected %r\n" % (argv,))
    sys.exit(1)
'''

LOGGED_IN = {"loggedIn": True, "email": "me@example.com", "authMethod": "claude.ai",
             "subscriptionType": "max"}


class ClaudeCase(TnTestCase):
    """TnTestCase with fake tmux and claude on PATH and no startup wait."""

    def setUp(self) -> None:
        super().setUp()
        self.fake("tmux", script=FAKE_TMUX)
        self.fake("claude", script=FAKE_CLAUDE)
        # Claude Code's first-run setup done, as on any machine that can start a session.
        self.claude_json().write_text(json.dumps({"hasCompletedOnboarding": True}))
        for knob in ("START_WAIT", "STOP_WAIT"):
            patcher = mock.patch.object(claude, knob, 0)
            patcher.start()
            self.addCleanup(patcher.stop)
        # The machine booted a day before any session, unless a test says otherwise.
        self.boot_time = CREATED - 86400
        patcher = mock.patch.object(claude, "_boot_time", lambda: self.boot_time)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.freeze_time(NOW)

    # -- fake state --------------------------------------------------------------------------
    def tmux_state(self) -> dict:
        db = self.state_dir / "tmux.json"
        return json.loads(db.read_text()) if db.exists() else {}

    def seed_session(self, name: str, *, title: str | None = "Some Session #T1",
                     directory: str | None = None, uuid: str = "", attached: int = 0,
                     context: str | None = None, created: int = CREATED) -> None:
        """A tmux session as tn claude start leaves it (title=None: a plain tmux session)."""
        s = self.tmux_state()
        opts = {}
        if title is not None:
            opts = {"@claude_name": title, "@claude_dir": directory or str(self.home),
                    "@claude_uuid": uuid, "@tn_kind": "claude"}
            if context is not None:
                opts["@tn_context"] = context
        s[name] = {"created": created, "attached": attached, "dir": directory or "",
                   "argv": [], "options": opts}
        (self.state_dir / "tmux.json").write_text(json.dumps(s))

    def set_agents(self, rows: list) -> None:
        (self.state_dir / "agents.json").write_text(json.dumps(rows))

    def set_auth(self, obj) -> None:
        text = obj if isinstance(obj, str) else json.dumps(obj)
        (self.state_dir / "auth.json").write_text(text)

    def tmux_verbs(self) -> list:
        return [c[0] for c in self.calls("tmux")]

    def new_session_argv(self) -> list:
        calls = [c for c in self.calls("tmux") if c[0] == "new-session"]
        self.assertEqual(len(calls), 1, self.calls("tmux"))
        return calls[0]

    def claude_json(self) -> Path:
        return self.home / ".claude.json"

    def transcripts(self, directory) -> Path:
        d = claude.transcript_dir(directory)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def no_machine(self) -> None:
        os.environ.pop("MY_MACHINE", None)


class mock_windows:
    """Pretend to be on Windows (``claude.IS_WINDOWS``) inside a with block."""

    def __enter__(self):
        self._p = mock.patch.object(claude, "IS_WINDOWS", True)
        self._p.start()
        return self

    def __exit__(self, *exc):
        self._p.stop()
        return False
