"""tn claude ls | attach | stop | restart, and the sessions / status hooks."""

from __future__ import annotations

import json
import os
from unittest import mock

from _base import CREATED, ClaudeCase, claude, mock_windows

U1 = "aaaaaaaa-1111-4111-8111-111111111111"
U2 = "bbbbbbbb-2222-4222-8222-222222222222"


class Sessions(ClaudeCase):
    def setUp(self):
        super().setUp()
        self.p = self.make_project("acme", repos=["shop-web"], workspaces=["src-02"])
        self.r00 = str(self.p.repo("shop-web"))
        self.r02 = str(self.p.repo("shop-web", "src-02"))
        self.seed_session("claude-acme-shop-web-00", title="Acme Shop Web #T1-00",
                          directory=self.r00, uuid=U1, context="acme/shop-web",
                          created=CREATED - 7200)
        # Started by the old claude-start: no @tn_context, so the context is derived.
        self.seed_session("claude-acme-shop-web-t1-02", title="Acme Shop Web #T1-02",
                          directory=self.r02, uuid=U2, attached=1)
        self.seed_session("work", title=None)          # a plain tmux session: never listed
        self.set_agents([{"sessionId": U1, "status": "busy", "pid": 1},
                         {"sessionId": "zzz", "status": "idle"}])

    # -- ls ----------------------------------------------------------------------------------
    def test_ls_json(self):
        r = self.tn("claude", "ls", "--json")
        self.assertExit(r, 0)
        a, b = r.json
        self.assertEqual(a, {"tmux": "claude-acme-shop-web-00", "name": "Acme Shop Web #T1-00",
                             "context": "acme/shop-web", "status": "busy", "age_seconds": 10800,
                             "attached": False, "dir": self.r00, "uuid": U1,
                             "started": "2023-11-14T20:13:20Z"})
        self.assertEqual((b["tmux"], b["context"], b["status"], b["attached"], b["age_seconds"]),
                         ("claude-acme-shop-web-t1-02", "acme/shop-web@02", None, True, 3600))

    def test_ls_text(self):
        r = self.tn("claude", "ls")
        self.assertExit(r, 0)
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0].split(), ["TMUX", "NAME", "CONTEXT", "STATUS", "AGE",
                                            "ATTACHED", "DIRECTORY"])
        self.assertIn("busy", lines[1])
        self.assertIn("3h", lines[1])
        self.assertIn("~/myprojects/acme/src/shop-web", lines[1])
        self.assertNotIn("work", r.stdout.replace("~", ""))

    def test_ls_empty(self):
        (self.state_dir / "tmux.json").unlink()
        r = self.tn("claude", "ls")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "")
        self.assertIn("No Claude sessions in tmux. Start one with: tn claude start", r.stderr)
        self.assertEqual(self.tn("claude", "ls", "--json").json, [])

    def test_ls_without_claude_has_no_status(self):
        self.unfake("claude")
        r = self.tn("claude", "ls", "--json")
        self.assertExit(r, 0)
        self.assertEqual([x["status"] for x in r.json], [None, None])

    def test_ls_tmux_missing(self):
        self.unfake("tmux")
        r = self.tn("claude", "ls", "--json")
        self.assertExit(r, 3)
        self.assertEqual(r.error["fix"], "dot apply tmux")

    def seed_tab(self, live: bool):
        claude.registry_path().parent.mkdir(parents=True, exist_ok=True)
        claude.registry_path().write_text(json.dumps([{
            "name": "claude-acme-shop-01", "title": "Acme Shop #T1-01", "uuid": U1,
            "dir": str(self.home), "context": "acme/shop@01", "created": CREATED}]))
        self.set_agents([{"sessionId": U1, "pid": os.getpid(), "status": "idle"}] if live else [])

    def test_ls_windows_lists_the_registry(self):
        self.seed_tab(live=False)
        with mock_windows():
            r = self.tn("claude", "ls", "--json")
        self.assertExit(r, 0)
        self.assertEqual([(x["tmux"], x["attached"]) for x in r.json],
                         [("claude-acme-shop-01", False)])

    def test_attach_windows_reopens_a_closed_tab(self):
        self.fake("wt")
        self.seed_tab(live=False)
        with mock_windows():
            r = self.tn("claude", "attach", "shop-01")
        self.assertExit(r, 0)
        argv = self.calls("wt")[0]
        self.assertEqual(argv[argv.index("--") + 2:], ["--resume", U1, "--remote-control",
                                                       "Acme Shop #T1-01", "-n", "Acme Shop #T1-01"])

    def test_attach_windows_refuses_a_tab_that_is_open(self):
        self.fake("wt")
        self.seed_tab(live=True)
        with mock_windows():
            r = self.tn("claude", "attach", "shop-01")
        self.assertExit(r, 1)
        self.assertEqual(self.calls("wt"), [])

    def test_stop_windows_kills_and_forgets(self):
        self.fake("taskkill")
        self.seed_tab(live=True)
        with mock_windows():
            r = self.tn("claude", "stop", "shop-01")
        self.assertExit(r, 0)
        self.assertEqual(self.calls("taskkill")[0], ["/PID", str(os.getpid()), "/T", "/F"])
        self.assertEqual(json.loads(claude.registry_path().read_text()), [])

    # -- attach ------------------------------------------------------------------------------
    def test_attach_by_name(self):
        r = self.tn("claude", "attach", "web@02")
        self.assertExit(r, 0)
        self.assertEqual(r.handoff, [str(self.bin / "tmux"), "attach-session", "-t",
                                     "=claude-acme-shop-web-t1-02"])

    def test_attach_drops_the_shell_function_env(self):
        seen = {}
        with mock.patch.object(claude, "handoff",
                               side_effect=lambda argv, **kw: seen.update(kw) or 0):
            r = self.tn("claude", "attach", "web@02", env={"TN_SHELL": "1"})
        self.assertExit(r, 0)
        self.assertEqual(seen["env"], {"TN_CD_FILE": None, "TN_SHELL": None})

    def test_attach_by_uuid_prefix_inside_tmux(self):
        r = self.tn("claude", "attach", "aaaa", env={"TMUX": "/tmp/tmux-1/default,1,0"})
        self.assertExit(r, 0)
        self.assertEqual(r.handoff[1:], ["switch-client", "-t", "=claude-acme-shop-web-00"])

    def test_attach_picks_without_name(self):
        r = self.tn("claude", "attach", tty=True, stdin="2\n")
        self.assertExit(r, 0)
        self.assertEqual(r.handoff[-1], "=claude-acme-shop-web-t1-02")

    def test_attach_no_tty_gives_choices(self):
        r = self.tn("claude", "attach")
        self.assertExit(r, 2)
        self.assertIn("choices: claude-acme-shop-web-00", r.stderr)
        self.assertIsNone(r.handoff)

    def test_attach_no_match(self):
        r = self.tn("claude", "attach", "nothing-like-it")
        self.assertExit(r, 2)
        self.assertIn('no Claude session matches "nothing-like-it"', r.stderr)

    def test_attach_rejects_json(self):
        r = self.tn("claude", "attach", "claude-acme-shop-web-00", "--json")
        self.assertExit(r, 2)
        self.assertIsNone(r.handoff)

    def test_attach_nothing_running(self):
        (self.state_dir / "tmux.json").unlink()
        r = self.tn("claude", "attach")
        self.assertExit(r, 1)
        self.assertIn("no Claude sessions in tmux", r.stderr)

    # -- stop --------------------------------------------------------------------------------
    def test_stop_by_name(self):
        r = self.tn("claude", "stop", "claude-acme-shop-web-00", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, [{"tmux": "claude-acme-shop-web-00",
                                   "name": "Acme Shop Web #T1-00", "uuid": U1, "dir": self.r00,
                                   "resume": "tn claude start %s --resume %s" % (self.r00, U1)}])
        self.assertEqual(sorted(self.tmux_state()), ["claude-acme-shop-web-t1-02", "work"])

    def test_stop_text_prints_the_resume_line(self):
        r = self.tn("claude", "stop", "@02")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "resume: tn claude start %s --resume %s\n" % (self.r02, U2))
        self.assertIn("stopped Acme Shop Web #T1-02", r.stderr)

    def test_stop_without_name_or_tty(self):
        r = self.tn("claude", "stop", "--json")
        self.assertExit(r, 2)
        self.assertEqual(len(r.error["choices"]), 2)
        self.assertNotIn("kill-session", self.tmux_verbs())

    def test_stop_all_confirms(self):
        r = self.tn("claude", "stop", "--all")
        self.assertExit(r, 2)
        self.assertIn("pass --yes to confirm", r.stderr)
        self.assertNotIn("kill-session", self.tmux_verbs())
        r = self.tn("claude", "stop", "--all", "--yes", "--json")
        self.assertExit(r, 0)
        self.assertEqual(len(r.json), 2)
        self.assertEqual(list(self.tmux_state()), ["work"])

    def test_stop_all_declined_on_tty(self):
        r = self.tn("claude", "stop", "--all", tty=True, stdin="n\n")
        self.assertExit(r, 1)
        self.assertEqual(len(self.tmux_state()), 3)

    def test_stop_name_and_all_is_usage(self):
        self.assertExit(self.tn("claude", "stop", "x", "--all"), 2)

    def test_stop_dry_run(self):
        r = self.tn("claude", "stop", "claude-acme-shop-web-00", "-n", "--json")
        self.assertExit(r, 0)
        self.assertNotIn("kill-session", self.tmux_verbs())
        self.assertIn("would: run ", r.stderr)
        self.assertEqual(len(self.tmux_state()), 3)

    def test_stop_nothing_running(self):
        (self.state_dir / "tmux.json").unlink()
        r = self.tn("claude", "stop", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, [])

    # -- restart -----------------------------------------------------------------------------
    def test_restart_resumes_the_conversation_under_the_same_names(self):
        self.set_agents([])
        r = self.tn("claude", "restart", "claude-acme-shop-web-00", "--json")
        self.assertExit(r, 0)
        self.assertEqual((r.json["tmux"], r.json["name"], r.json["uuid"], r.json["resumed"]),
                         ("claude-acme-shop-web-00", "Acme Shop Web #T1-00", U1, True))
        self.assertEqual(self.tmux_verbs().count("kill-session"), 1)
        argv = self.new_session_argv()
        i = argv.index(str(self.bin / "claude"))
        self.assertEqual(argv[i + 1:i + 3], ["--resume", U1])
        self.assertEqual(argv[argv.index("-s") + 1], "claude-acme-shop-web-00")
        self.assertEqual(argv[argv.index("-c") + 1], self.r00)
        self.assertEqual(self.tmux_state()["claude-acme-shop-web-00"]["options"]["@claude_name"],
                         "Acme Shop Web #T1-00")

    def test_restart_keeps_a_custom_name(self):
        self.set_agents([])
        self.seed_session("claude-acme-iphone-build", title="Acme iPhone Build",
                          directory=self.r02, uuid="cccccccc-3333-4333-8333-333333333333")
        r = self.tn("claude", "restart", "iphone", "--json")
        self.assertExit(r, 0)
        self.assertEqual((r.json["tmux"], r.json["name"]),
                         ("claude-acme-iphone-build", "Acme iPhone Build"))

    def test_restart_without_name_or_tty(self):
        r = self.tn("claude", "restart", "--json")
        self.assertExit(r, 2)
        self.assertEqual(len(r.error["choices"]), 2)
        self.assertNotIn("kill-session", self.tmux_verbs())

    def test_restart_unknown_name_is_usage(self):
        self.assertExit(self.tn("claude", "restart", "nope", "--json"), 2)

    def test_restart_nothing_running(self):
        (self.state_dir / "tmux.json").unlink()
        r = self.tn("claude", "restart", "--json")
        self.assertExit(r, 1)
        self.assertIn("no Claude sessions in tmux", r.stderr)

    def test_restart_missing_claude(self):
        (self.bin / "claude").unlink()
        r = self.tn("claude", "restart", "claude-acme-shop-web-00", "--json")
        self.assertExit(r, 3)
        self.assertNotIn("kill-session", self.tmux_verbs())

    def test_restart_dry_run_changes_nothing(self):
        self.set_agents([])
        r = self.tn("claude", "restart", "claude-acme-shop-web-00", "-n", "--json")
        self.assertExit(r, 0)
        self.assertNotIn("kill-session", self.tmux_verbs())
        self.assertNotIn("new-session", self.tmux_verbs())
        self.assertEqual(len(self.tmux_state()), 3)

    def test_restart_failure_after_stop_prints_the_resume_line(self):
        self.set_agents([])
        (self.state_dir / "tmux-die").write_text("")
        r = self.tn("claude", "restart", "claude-acme-shop-web-00", "--json")
        self.assertExit(r, 1)
        self.assertIn("is stopped; bring it back with: tn claude start", r.stderr)

    # -- hooks -------------------------------------------------------------------------------
    def test_sessions_hook(self):
        r = self.tn("sessions", "--json")
        self.assertExit(r, 0)
        mine = [s for s in r.json if s["kind"] == "claude"]
        self.assertEqual([s["id"] for s in mine],
                         ["claude-acme-shop-web-00", "claude-acme-shop-web-t1-02"])
        s = mine[0]
        self.assertEqual((s["name"], s["context"], s["dir"], s["status"], s["attached"]),
                         ("Acme Shop Web #T1-00", "acme/shop-web", self.r00, "busy", False))
        self.assertEqual(s["started"], CREATED - 7200)
        self.assertEqual(s["attach"], ["tmux", "attach-session", "-t",
                                       "=claude-acme-shop-web-00"])
        self.assertEqual(s["extra"], {"uuid": U1})

    def test_sessions_attach_goes_through_the_hook(self):
        r = self.tn("sessions", "attach", U2[:6])
        self.assertExit(r, 0)
        self.assertEqual(r.handoff, ["tmux", "attach-session", "-t",
                                     "=claude-acme-shop-web-t1-02"])

    def test_status_hook(self):
        r = self.tn("status", "--json", cwd=self.r00)
        self.assertExit(r, 0)
        self.assertEqual(r.json["plugins"]["claude"],
                         ["2 sessions (1 attached); here: claude-acme-shop-web-00 busy"])
        r = self.tn("status", "--json")
        self.assertEqual(r.json["plugins"]["claude"], ["2 sessions (1 attached)"])

    def test_status_hook_is_quiet_without_sessions(self):
        (self.state_dir / "tmux.json").unlink()
        r = self.tn("status", "--json")
        self.assertNotIn("claude", r.json["plugins"])
        self.assertNotIn("claude", r.json["errors"])

    def test_hooks_without_tmux(self):
        self.unfake("tmux")
        r = self.tn("sessions", "--json")
        self.assertExit(r, 0)
        self.assertEqual([s for s in r.json if s["kind"] == "claude"], [])
        self.assertNotIn("claude", self.tn("status", "--json").json["errors"])
