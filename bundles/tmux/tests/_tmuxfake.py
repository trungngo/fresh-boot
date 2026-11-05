"""A stateful fake tmux for the tmux plugin tests (never a real tmux server).

Sessions live in <state>/tmux.json as a list of {name, dir, windows, attached, created, opts}.
It understands the subcommands the plugin uses: list-sessions -F, has-session, new-session,
kill-session, switch-client, attach-session, display-message -p and -V.
"""

from __future__ import annotations

import json
import sys

from tn.testing import TnTestCase

TMUX_FAKE = r'''
import re
db = state_dir / "tmux.json"
sessions = json.loads(db.read_text()) if db.exists() else []

def save():
    db.write_text(json.dumps(sessions))

def target(args):
    t = args[args.index("-t") + 1] if "-t" in args else None
    if t is None:
        return None
    t = t[1:] if t.startswith("=") else t
    for s in sessions:
        if s["name"] == t:
            return s
    return False

def fmt(f, s):
    vals = {"session_name": s["name"], "session_windows": str(s.get("windows", 1)),
            "session_attached": str(s.get("attached", 0)), "session_created": str(s.get("created", 0)),
            "session_path": s.get("dir", "")}
    vals.update({"@" + k: v for k, v in s.get("opts", {}).items()})
    return re.sub(r"#\{([^}]*)\}", lambda m: vals.get(m.group(1), ""), f)

cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
if cmd == "-V":
    print("tmux 3.4")
elif cmd == "list-sessions":
    if not sessions:
        sys.stderr.write("no server running on /tmp/tmux-501/default\n"); sys.exit(1)
    f = rest[rest.index("-F") + 1]
    for s in sessions:
        print(fmt(f, s))
elif cmd == "has-session":
    sys.exit(0 if target(rest) else 1)
elif cmd == "new-session":
    name = rest[rest.index("-s") + 1]
    if any(s["name"] == name for s in sessions):
        sys.stderr.write("duplicate session: %s\n" % name); sys.exit(1)
    d = rest[rest.index("-c") + 1] if "-c" in rest else os.getcwd()
    sessions.append({"name": name, "dir": d, "windows": 1, "attached": 0 if "-d" in rest else 1,
                     "created": 1790000000, "opts": {}})
    save()
elif cmd == "kill-session":
    s = target(rest)
    if not s:
        sys.stderr.write("can't find session\n"); sys.exit(1)
    sessions.remove(s); save()
elif cmd in ("switch-client", "attach-session"):
    if not target(rest):
        sys.stderr.write("can't find session\n"); sys.exit(1)
elif cmd == "display-message":
    s = target(rest)
    if s is False:
        sys.exit(1)
    if s is None:
        cur = os.environ.get("FAKE_TMUX_CURRENT")
        s = next((x for x in sessions if x["name"] == cur), None)
        if s is None:
            sys.exit(1)
    print(fmt(rest[-1], s))
else:
    sys.stderr.write("fake tmux: unknown command %r\n" % cmd); sys.exit(1)
'''

NOW = 1790000000 + 3 * 3600      # three hours after every fake session was created


class TmuxCase(TnTestCase):
    """TnTestCase with the fake tmux on PATH and helpers to seed its sessions."""

    def setUp(self) -> None:
        super().setUp()
        self.fake("tmux", script=TMUX_FAKE)
        self.freeze_time(NOW)

    def seed(self, *sessions: dict) -> None:
        rows = []
        for s in sessions:
            row = {"windows": 1, "attached": 0, "created": 1790000000, "dir": str(self.home),
                   "opts": {}}
            row.update(s)
            rows.append(row)
        (self.state_dir / "tmux.json").write_text(json.dumps(rows))

    def module(self):
        """The imported tmux plugin module (for patching and its helpers)."""
        self.load_plugin("tmux")
        return sys.modules["tn.plugins.tmux"]

    def sessions(self) -> list:
        db = self.state_dir / "tmux.json"
        return json.loads(db.read_text()) if db.exists() else []

    def names(self) -> list:
        return [s["name"] for s in self.sessions()]

    def mutating(self) -> list:
        """The tmux calls that change something (read-only queries excluded)."""
        return [c for c in self.calls("tmux")
                if c and c[0] in ("new-session", "kill-session", "switch-client",
                                  "attach-session")]
