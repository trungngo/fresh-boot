"""tn claude resume, and the registry start / stop / ls keep for it."""

from __future__ import annotations

import json
import os

from _base import CREATED, LOGGED_IN, NOW, ClaudeCase, claude, mock_windows

U1 = "aaaaaaaa-1111-4111-8111-111111111111"
U2 = "bbbbbbbb-2222-4222-8222-222222222222"
U3 = "cccccccc-3333-4333-8333-333333333333"
U4 = "dddddddd-4444-4444-8444-444444444444"

# Transcript tails: a claude that exited writes cost-state after its last message.
CLEAN = ["user", "assistant", "cost-state"]
ABRUPT = ["user", "assistant", "user"]


class Resume(ClaudeCase):
    def setUp(self):
        super().setUp()
        self.p = self.make_project("acme", repos=["shop-web"], workspaces=["src-01", "src-02",
                                                                           "src-03"])
        self.dirs = {ws: str(self.p.repo("shop-web", ws))
                     for ws in ("src", "src-01", "src-02", "src-03")}
        self.set_auth(LOGGED_IN)

    # -- fixtures ----------------------------------------------------------------------------
    def entry(self, ws, uuid, *, account="me@example.com", **extra):
        n = "00" if ws == "src" else ws[-2:]
        e = {"name": "claude-acme-shop-web-" + n, "title": "Acme Shop Web #T1-" + n,
             "uuid": uuid, "dir": self.dirs[ws], "context": "acme/shop-web@" + n,
             "created": CREATED, "account": account}
        e.update(extra)
        return e

    def seed_registry(self, *entries):
        claude.registry_path().parent.mkdir(parents=True, exist_ok=True)
        claude.registry_path().write_text(json.dumps(list(entries)))

    def registry(self):
        return json.loads(claude.registry_path().read_text())

    def transcript(self, ws, uuid, kinds, mtime=None):
        p = self.transcripts(self.dirs[ws]) / (uuid + ".jsonl")
        p.write_text("".join(json.dumps({"type": k, "sessionId": uuid}) + "\n" for k in kinds))
        if mtime is not None:
            os.utime(p, (mtime, mtime))

    def resume(self, *argv, code=0, **kw):
        r = self.tn("claude", "resume", *argv, **kw)
        self.assertExit(r, code)
        return r

    def started(self):
        """(tmux name, resumed uuid) of every new-session call."""
        res = []
        for c in self.calls("tmux"):
            if c[0] == "new-session":
                res.append((c[c.index("-s") + 1], c[c.index("--resume") + 1]))
        return res

    # -- the states --------------------------------------------------------------------------
    def test_all_wakes_crashed_and_account_but_not_ended_or_running(self):
        self.seed_registry(
            self.entry("src", U1),                                   # crashed
            self.entry("src-01", U2),                                # exited (archived)
            self.entry("src-02", U3, stopped=NOW - 60),              # tn claude stop
            self.entry("src-03", U4, account="old@example.com"))     # previous account, live
        self.transcript("src", U1, ABRUPT)
        self.transcript("src-01", U2, CLEAN)
        self.transcript("src-02", U3, CLEAN)
        self.transcript("src-03", U4, ABRUPT)
        self.seed_session("claude-acme-shop-web-03", title="Acme Shop Web #T1-03",
                          directory=self.dirs["src-03"], uuid=U4)
        r = self.resume("--all", "--json")
        self.assertEqual([(x["tmux"], x["state"], x["resumed"]) for x in r.json],
                         [("claude-acme-shop-web-00", "crashed", True),
                          ("claude-acme-shop-web-03", "account", True)])
        self.assertEqual(self.started(), [("claude-acme-shop-web-00", U1),
                                          ("claude-acme-shop-web-03", U4)])
        self.assertEqual(self.tmux_verbs().count("kill-session"), 1)    # the live one restarted
        self.assertIn("left alone: 2 sessions stopped or exited on purpose", r.stderr)
        # Resuming records them again, on the account they now run on.
        reg = {e["name"]: e for e in self.registry()}
        self.assertEqual(reg["claude-acme-shop-web-03"]["account"], "me@example.com")
        self.assertNotIn("stopped", reg["claude-acme-shop-web-00"])

    def test_running_session_is_left_alone(self):
        self.seed_registry(self.entry("src", U1))
        self.transcript("src", U1, ABRUPT)
        self.seed_session("claude-acme-shop-web-00", title="Acme Shop Web #T1-00",
                          directory=self.dirs["src"], uuid=U1)
        r = self.resume("--all", "--json")
        self.assertEqual(r.json, [])
        self.assertNotIn("new-session", self.tmux_verbs())

    def test_reboot_after_creation(self):
        self.boot_time = CREATED + 1000
        self.seed_registry(self.entry("src", U1), self.entry("src-01", U2),
                           self.entry("src-02", U3))
        self.transcript("src", U1, CLEAN, mtime=self.boot_time - 30)     # SIGTERM at shutdown
        self.transcript("src-01", U2, ABRUPT, mtime=CREATED + 10)        # killed outright
        self.transcript("src-02", U3, CLEAN, mtime=CREATED + 10)         # exited, then reboot
        r = self.resume("--all", "--json")
        self.assertEqual([(x["tmux"], x["state"]) for x in r.json],
                         [("claude-acme-shop-web-00", "rebooted"),
                          ("claude-acme-shop-web-01", "rebooted")])

    def test_outside_and_missing_are_not_woken(self):
        self.seed_registry(self.entry("src", U1), self.entry("src-01", U2))
        self.transcript("src", U1, ABRUPT)                     # src-01 has no transcript
        self.set_agents([{"sessionId": U1, "pid": os.getpid(), "status": "idle"}])
        r = self.resume("--all", "--json")
        self.assertEqual(r.json, [])
        self.assertIn("No Claude session to resume.", r.stderr)
        r = self.resume("claude-acme-shop-web-00", code=1)
        self.assertIn("running outside tmux", r.stderr)
        r = self.resume("claude-acme-shop-web-01", code=1)
        self.assertIn("directory or transcript is gone", r.stderr)

    # -- by name -----------------------------------------------------------------------------
    def test_name_resumes_a_stopped_session(self):
        self.seed_registry(self.entry("src-02", U3, stopped=NOW - 60))
        self.transcript("src-02", U3, CLEAN)
        r = self.resume("web@02", "--json")
        self.assertEqual([(x["tmux"], x["state"], x["resumed"]) for x in r.json],
                         [("claude-acme-shop-web-02", "stopped", True)])
        argv = self.new_session_argv()
        self.assertEqual(argv[argv.index("-c") + 1], self.dirs["src-02"])
        self.assertEqual(self.tmux_state()["claude-acme-shop-web-02"]["options"]["@claude_name"],
                         "Acme Shop Web #T1-02")

    def test_name_running_fails_with_attach(self):
        self.seed_registry(self.entry("src", U1))
        self.transcript("src", U1, ABRUPT)
        self.seed_session("claude-acme-shop-web-00", title="Acme Shop Web #T1-00",
                          directory=self.dirs["src"], uuid=U1)
        r = self.resume("claude-acme-shop-web-00", "--json", code=1)
        self.assertEqual(r.error["fix"], "tn claude attach claude-acme-shop-web-00")

    def test_unknown_name_is_usage(self):
        self.seed_registry(self.entry("src", U1))
        self.transcript("src", U1, ABRUPT)
        r = self.resume("nope", "--json", code=2)
        self.assertEqual(r.error["choices"], ["claude-acme-shop-web-00"])

    def test_without_name_or_tty_gives_choices(self):
        self.seed_registry(self.entry("src", U1), self.entry("src-01", U2))
        self.transcript("src", U1, ABRUPT)
        self.transcript("src-01", U2, ABRUPT)
        r = self.resume("--json", code=2)
        self.assertEqual(len(r.error["choices"]), 2)
        self.assertNotIn("new-session", self.tmux_verbs())

    def test_picks_on_a_tty(self):
        self.seed_registry(self.entry("src", U1), self.entry("src-01", U2))
        self.transcript("src", U1, ABRUPT)
        self.transcript("src-01", U2, ABRUPT)
        self.resume(tty=True, stdin="2\n")
        self.assertEqual(self.started(), [("claude-acme-shop-web-01", U2)])

    def test_name_and_all_is_usage(self):
        self.resume("x", "--all", code=2)

    # -- dry run, failures, prerequisites ----------------------------------------------------
    def test_dry_run_changes_nothing(self):
        self.seed_registry(self.entry("src", U1),
                           self.entry("src-03", U4, account="old@example.com"))
        self.transcript("src", U1, ABRUPT)
        self.transcript("src-03", U4, ABRUPT)
        self.seed_session("claude-acme-shop-web-03", title="Acme Shop Web #T1-03",
                          directory=self.dirs["src-03"], uuid=U4)
        before = claude.registry_path().read_text()
        r = self.resume("--all", "-n", "--json")
        self.assertEqual([x["state"] for x in r.json], ["crashed", "account"])
        self.assertNotIn("kill-session", self.tmux_verbs())
        self.assertNotIn("new-session", self.tmux_verbs())
        self.assertEqual(claude.registry_path().read_text(), before)

    def test_all_goes_on_after_a_failure(self):
        self.seed_registry(self.entry("src", U1), self.entry("src-01", U2))
        self.transcript("src", U1, ABRUPT)
        self.transcript("src-01", U2, ABRUPT)
        (self.state_dir / "tmux-die").write_text("")          # the first start dies
        r = self.resume("--all", "--json", code=1)
        self.assertEqual([(x["tmux"], x["resumed"]) for x in r.json],
                         [("claude-acme-shop-web-00", False), ("claude-acme-shop-web-01", True)])
        self.assertIn("claude exited straight away", r.json[0]["error"])

    def test_not_signed_in(self):
        self.set_auth({"loggedIn": False})
        self.seed_registry(self.entry("src", U1))
        self.transcript("src", U1, ABRUPT)
        r = self.resume("--all", "--json", code=3)
        self.assertEqual(r.error["fix"], "tn claude login")
        self.assertNotIn("new-session", self.tmux_verbs())

    def test_tmux_missing(self):
        self.unfake("tmux")
        r = self.resume("--all", "--json", code=3)
        self.assertEqual(r.error["fix"], "dot apply tmux")

    def test_nothing_recorded(self):
        r = self.resume("--all", "--json")
        self.assertEqual(r.json, [])
        self.resume("anything", code=1)

    def test_windows_points_at_attach(self):
        with mock_windows():
            r = self.resume("--all", "--json", code=1)
        self.assertEqual(r.error["fix"], "tn claude attach <name>")

    # -- the registry ------------------------------------------------------------------------
    def test_start_records_and_stop_marks(self):
        r = self.tn("claude", "start", "--json", cwd=self.dirs["src-01"])
        self.assertExit(r, 0)
        e = self.registry()[0]
        self.assertEqual((e["name"], e["uuid"], e["dir"], e["account"], e["created"]),
                         (r.json["tmux"], r.json["uuid"], self.dirs["src-01"], "me@example.com",
                          NOW))
        self.assertExit(self.tn("claude", "stop", r.json["tmux"]), 0)
        self.assertEqual(self.registry()[0]["stopped"], NOW)

    def test_ls_adopts_live_sessions_and_drops_gone_dirs(self):
        self.seed_registry(dict(self.entry("src", U1), dir=str(self.home / "gone")))
        self.seed_session("claude-acme-shop-web-02", title="Acme Shop Web #T1-02",
                          directory=self.dirs["src-02"], uuid=U3, created=CREATED - 50)
        self.assertExit(self.tn("claude", "ls", "--json"), 0)
        self.assertEqual([(e["name"], e["uuid"], e["created"], e["account"])
                          for e in self.registry()],
                         [("claude-acme-shop-web-02", U3, CREATED - 50, None)])

    def test_ls_dry_run_writes_nothing(self):
        self.seed_session("claude-acme-shop-web-02", title="Acme Shop Web #T1-02",
                          directory=self.dirs["src-02"], uuid=U3)
        self.assertExit(self.tn("claude", "ls", "-n", "--json"), 0)
        self.assertFalse(claude.registry_path().exists())
