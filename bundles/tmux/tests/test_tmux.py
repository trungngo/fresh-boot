"""tn tmux new|attach|ls|kill (docs/tn.md §7.6)."""

from __future__ import annotations

from unittest import mock

from _tmuxfake import NOW, TmuxCase

CLAUDE = {"name": "claude-acme-shop-app-00", "attached": 1,
          "opts": {"tn_kind": "claude", "claude_name": "Acme Shop App #T1-00"}}
LEGACY_CLAUDE = {"name": "claude-old", "opts": {"claude_name": "Old #T1"}}     # no @tn_kind
CODEX = {"name": "codex-x", "opts": {"tn_kind": "codex"}}
PLAIN = {"name": "work", "windows": 3}
PLAIN2 = {"name": "workshop"}


class New(TmuxCase):
    def setUp(self):
        super().setUp()
        self.p = self.make_project("acme", repos=["shop-app"], workspaces=["src-02"])
        self.repo = self.p.repo("shop-app", ws="src-02")

    def test_detached_json_names_session_after_context(self):
        r = self.tn("tmux", "new", "-d", "--json", cwd=self.repo)
        self.assertExit(r, 0)
        self.assertEqual(r.json, {"name": "acme-shop-app-02", "dir": str(self.repo),
                                  "created": True})
        self.assertIn(["new-session", "-d", "-s", "acme-shop-app-02", "-c", str(self.repo)],
                      self.calls("tmux"))
        self.assertEqual(self.names(), ["acme-shop-app-02"])

    def test_detached_text_prints_name(self):
        r = self.tn("tmux", "new", "scratch", "-d", cwd=self.repo)
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "scratch\n")

    def test_default_dir_is_context_path_from_subdirectory(self):
        sub = self.repo / "app"
        sub.mkdir()
        r = self.tn("tmux", "new", "-d", "--json", cwd=sub)
        self.assertExit(r, 0)
        self.assertEqual(r.json["dir"], str(self.repo))

    def test_outside_roots_uses_directory_name(self):
        d = self.tmp / "My Stuff"
        d.mkdir()
        r = self.tn("tmux", "new", "-d", "--json", cwd=d)
        self.assertExit(r, 0)
        self.assertEqual(r.json["name"], "my-stuff")
        self.assertEqual(r.json["dir"], str(d))

    def test_attaches_by_handoff(self):
        r = self.tn("tmux", "new", cwd=self.repo)
        self.assertExit(r, 0)
        self.assertEqual(r.handoff[1:], ["new-session", "-s", "acme-shop-app-02",
                                         "-c", str(self.repo)])
        self.assertTrue(r.handoff[0].endswith("tmux"))

    def test_existing_session_attaches_instead(self):
        self.seed({"name": "acme-shop-app-02"})
        r = self.tn("tmux", "new", cwd=self.repo)
        self.assertExit(r, 0)
        self.assertEqual(r.handoff[1:], ["attach-session", "-t", "=acme-shop-app-02"])
        self.assertIn("already exists", r.stderr)

    def test_existing_session_detached_reports_not_created(self):
        self.seed({"name": "acme-shop-app-02", "dir": "/elsewhere"})
        r = self.tn("tmux", "new", "-d", "--json", cwd=self.repo)
        self.assertExit(r, 0)
        self.assertEqual(r.json, {"name": "acme-shop-app-02", "dir": "/elsewhere",
                                  "created": False})
        self.assertEqual(self.mutating(), [])

    def test_inside_tmux_creates_detached_then_switches(self):
        r = self.tn("tmux", "new", "side", cwd=self.repo, env={"TMUX": "/tmp/tmux-1/default,1,0"})
        self.assertExit(r, 0)
        self.assertIsNone(r.handoff)
        self.assertEqual(self.mutating(), [
            ["new-session", "-d", "-s", "side", "-c", str(self.repo)],
            ["switch-client", "-t", "=side"]])

    def test_dir_option_relative_to_cwd(self):
        (self.repo / "docs").mkdir()
        r = self.tn("tmux", "new", "x", "-c", "docs", "-d", "--json", cwd=self.repo)
        self.assertExit(r, 0)
        self.assertEqual(r.json["dir"], str(self.repo / "docs"))

    def test_missing_dir_is_usage_error(self):
        r = self.tn("tmux", "new", "x", "-c", "nope", "-d", cwd=self.repo)
        self.assertExit(r, 2)
        self.assertIn("no such directory", r.stderr)

    def test_bad_name_is_usage_error(self):
        r = self.tn("tmux", "new", "a.b", "-d", cwd=self.repo)
        self.assertExit(r, 2)
        self.assertIn("try a-b", r.stderr)
        self.assertEqual(self.mutating(), [])

    def test_json_without_detach_is_rejected(self):
        r = self.tn("tmux", "new", "--json", cwd=self.repo)
        self.assertExit(r, 2)
        self.assertEqual(self.mutating(), [])

    def test_dry_run_changes_nothing(self):
        r = self.tn("-n", "tmux", "new", "-d", "--json", cwd=self.repo)
        self.assertExit(r, 0)
        self.assertTrue(r.json["dry_run"])
        self.assertIn("would: run tmux new-session", r.stderr)
        self.assertEqual(self.mutating(), [])
        self.assertEqual(self.names(), [])

    def test_dry_run_attach_does_not_hand_off(self):
        r = self.tn("-n", "tmux", "new", cwd=self.repo)
        self.assertExit(r, 0)
        self.assertIsNone(r.handoff)
        self.assertIn("would: run tmux new-session -s acme-shop-app-02", r.stderr)

    def test_missing_tmux_exits_3(self):
        self.unfake("tmux")
        r = self.tn("tmux", "new", "-d", cwd=self.repo)
        self.assertExit(r, 3)
        self.assertIn("run: dot apply tmux", r.stderr)


class Ls(TmuxCase):
    def test_json_rows(self):
        self.seed(PLAIN, CLAUDE, LEGACY_CLAUDE, CODEX)
        r = self.tn("tmux", "ls", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json[0], {"name": "work", "windows": 3, "attached": False,
                                     "started": "2026-09-21T14:13:20Z",
                                     "age_seconds": 3 * 3600, "kind": None})
        self.assertEqual([x["kind"] for x in r.json], [None, "claude", "claude", "codex"])
        self.assertTrue(r.json[1]["attached"])

    def test_text_table(self):
        self.seed(PLAIN, CLAUDE)
        r = self.tn("tmux", "ls")
        self.assertExit(r, 0)
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0].split(), ["NAME", "KIND", "WINDOWS", "ATTACHED", "AGE"])
        self.assertEqual(lines[1].split(), ["work", "-", "3", "no", "3h"])
        self.assertEqual(lines[2].split(), ["claude-acme-shop-app-00", "claude", "1", "yes",
                                            "3h"])

    def test_no_server_is_empty(self):
        r = self.tn("tmux", "ls")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "")
        self.assertIn("No tmux sessions", r.stderr)
        r = self.tn("tmux", "ls", "--json")
        self.assertEqual(r.json, [])

    def test_missing_tmux_exits_3(self):
        self.unfake("tmux")
        r = self.tn("tmux", "ls", "--json")
        self.assertExit(r, 3)
        self.assertEqual(r.error["fix"], "dot apply tmux")


class Attach(TmuxCase):
    def test_by_exact_name(self):
        self.seed(PLAIN, PLAIN2)
        r = self.tn("tmux", "attach", "work")
        self.assertExit(r, 0)
        self.assertEqual(r.handoff[1:], ["attach-session", "-t", "=work"])

    def test_by_unique_prefix(self):
        self.seed(PLAIN, CLAUDE)
        r = self.tn("tmux", "attach", "clau")
        self.assertExit(r, 0)
        self.assertEqual(r.handoff[1:], ["attach-session", "-t", "=claude-acme-shop-app-00"])

    def test_by_claude_title(self):
        self.seed(PLAIN, CLAUDE)
        r = self.tn("tmux", "attach", "acme shop")
        self.assertExit(r, 0)
        self.assertEqual(r.handoff[-1], "=claude-acme-shop-app-00")

    def test_inside_tmux_switches(self):
        self.seed(PLAIN)
        r = self.tn("tmux", "attach", "work", env={"TMUX": "x"})
        self.assertExit(r, 0)
        self.assertIsNone(r.handoff)
        self.assertEqual(self.mutating(), [["switch-client", "-t", "=work"]])

    def test_single_session_needs_no_name(self):
        self.seed(PLAIN)
        r = self.tn("tmux", "attach")
        self.assertExit(r, 0)
        self.assertEqual(r.handoff[-1], "=work")
        self.assertIn("using work", r.stderr)

    def test_picks_on_a_terminal(self):
        self.seed(PLAIN, PLAIN2)
        r = self.tn("tmux", "attach", stdin="2\n", tty=True)
        self.assertExit(r, 0)
        self.assertEqual(r.handoff[-1], "=workshop")

    def test_ambiguous_without_terminal_lists_choices(self):
        self.seed(PLAIN, PLAIN2)
        r = self.tn("tmux", "attach", "wor")
        self.assertExit(r, 2)
        self.assertIn("which tmux session?", r.stderr)
        self.assertIsNone(r.handoff)

    def test_no_match_is_usage_error(self):
        self.seed(PLAIN)
        r = self.tn("tmux", "attach", "zzz")
        self.assertExit(r, 2)
        self.assertIn("choices: work", r.stderr)

    def test_no_sessions_fails(self):
        r = self.tn("tmux", "attach")
        self.assertExit(r, 1)
        self.assertIn("No tmux sessions", r.stderr)

    def test_json_rejected(self):
        self.seed(PLAIN)
        r = self.tn("tmux", "attach", "work", "--json")
        self.assertExit(r, 2)
        self.assertEqual(self.mutating(), [])

    def test_dry_run(self):
        self.seed(PLAIN)
        r = self.tn("tmux", "attach", "work", "-n")
        self.assertExit(r, 0)
        self.assertIsNone(r.handoff)
        self.assertIn("would: run tmux attach-session -t =work", r.stderr)


class Kill(TmuxCase):
    def test_by_name_json(self):
        self.seed(PLAIN, PLAIN2)
        r = self.tn("tmux", "kill", "work", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, [{"name": "work", "killed": True}])
        self.assertEqual(self.names(), ["workshop"])
        self.assertIn(["kill-session", "-t", "=work"], self.calls("tmux"))

    def test_claude_session_hints(self):
        self.seed(CLAUDE)
        r = self.tn("tmux", "kill", "claude-acme-shop-app-00")
        self.assertExit(r, 0)
        self.assertIn("tn claude stop", r.stderr)

    def test_no_name_without_terminal_is_usage_error(self):
        self.seed(PLAIN, PLAIN2)
        r = self.tn("tmux", "kill", "--json")
        self.assertExit(r, 2)
        self.assertEqual(r.error["choices"][0].split()[0], "work")
        self.assertEqual(self.mutating(), [])

    def test_no_name_picks(self):
        self.seed(PLAIN, PLAIN2)
        r = self.tn("tmux", "kill", stdin="1\n", tty=True)
        self.assertExit(r, 0)
        self.assertEqual(self.names(), ["workshop"])

    def test_all_confirms_and_counts_agents(self):
        self.seed(PLAIN, CLAUDE, LEGACY_CLAUDE, CODEX)
        r = self.tn("tmux", "kill", "--all")
        self.assertExit(r, 2)
        self.assertIn("kill all 4 tmux sessions (2 are Claude sessions, 1 is a Codex session)?",
                      r.stderr)
        self.assertIn("pass --yes", r.stderr)
        self.assertEqual(len(self.names()), 4)

    def test_all_with_yes(self):
        self.seed(PLAIN, CLAUDE)
        r = self.tn("tmux", "kill", "--all", "--yes", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, [{"name": "work", "killed": True},
                                  {"name": "claude-acme-shop-app-00", "killed": True}])
        self.assertEqual(self.names(), [])

    def test_all_answer_no_cancels(self):
        self.seed(PLAIN)
        r = self.tn("tmux", "kill", "--all", stdin="n\n", tty=True)
        self.assertExit(r, 1)
        self.assertIn("cancelled", r.stderr)
        self.assertEqual(self.names(), ["work"])

    def test_all_kills_own_session_last(self):
        self.seed(PLAIN, PLAIN2, {"name": "aaa"})
        r = self.tn("tmux", "kill", "--all", "-y", env={"TMUX": "x", "FAKE_TMUX_CURRENT": "work"})
        self.assertExit(r, 0)
        kills = [c[2] for c in self.mutating()]
        self.assertEqual(kills, ["=workshop", "=aaa", "=work"])

    def test_all_with_no_sessions_is_ok(self):
        r = self.tn("tmux", "kill", "--all", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, [])

    def test_name_and_all_is_usage_error(self):
        self.seed(PLAIN)
        r = self.tn("tmux", "kill", "work", "--all", "-y")
        self.assertExit(r, 2)
        self.assertEqual(self.names(), ["work"])

    def test_no_match(self):
        self.seed(PLAIN)
        r = self.tn("tmux", "kill", "zzz")
        self.assertExit(r, 2)

    def test_prefix_kills_nothing(self):
        # A typo or an ended session must not take out the session it happens to prefix.
        self.seed({"name": "foobar"}, CLAUDE)
        r = self.tn("tmux", "kill", "foo", "--json")
        self.assertExit(r, 2)
        self.assertEqual(r.error["choices"], ["foobar"])
        self.assertEqual(self.mutating(), [])
        self.assertEqual(len(self.names()), 2)

    def test_prefix_on_a_terminal_still_kills_nothing(self):
        self.seed({"name": "foobar"})
        r = self.tn("tmux", "kill", "foo", "-y", stdin="1\ny\n", tty=True)
        self.assertExit(r, 2)
        self.assertEqual(self.names(), ["foobar"])

    def test_substring_does_not_kill_claude_session(self):
        self.seed(CLAUDE, PLAIN)
        r = self.tn("tmux", "kill", "acme")
        self.assertExit(r, 2)
        self.assertEqual(self.mutating(), [])
        self.assertEqual(len(self.names()), 2)

    def test_lone_session_without_name_confirms(self):
        self.seed(PLAIN)
        r = self.tn("tmux", "kill")
        self.assertExit(r, 2)
        self.assertIn("kill tmux session work", r.stderr)
        self.assertIn("pass --yes", r.stderr)
        self.assertEqual(self.names(), ["work"])

    def test_lone_session_answer_no_cancels(self):
        self.seed(PLAIN)
        r = self.tn("tmux", "kill", stdin="n\n", tty=True)
        self.assertExit(r, 1)
        self.assertEqual(self.names(), ["work"])

    def test_lone_session_with_yes(self):
        self.seed(PLAIN)
        r = self.tn("tmux", "kill", "-y", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, [{"name": "work", "killed": True}])
        self.assertEqual(self.names(), [])

    def test_no_sessions(self):
        r = self.tn("tmux", "kill", "work")
        self.assertExit(r, 1)

    def test_dry_run_changes_nothing(self):
        self.seed(PLAIN, PLAIN2)
        r = self.tn("-n", "tmux", "kill", "--all", "-y")
        self.assertExit(r, 0)
        self.assertIn("would: run tmux kill-session -t =work", r.stderr)
        self.assertEqual(self.mutating(), [])
        self.assertEqual(len(self.names()), 2)

    def test_missing_tmux_exits_3(self):
        self.unfake("tmux")
        r = self.tn("tmux", "kill", "--all", "-y")
        self.assertExit(r, 3)
        self.assertIn("run: dot apply tmux", r.stderr)


class Windows(TmuxCase):
    def test_every_command_exits_3(self):
        mod = self.module()
        with mock.patch.object(mod, "IS_WINDOWS", True):
            for argv in (("new", "-d"), ("ls",), ("attach",), ("kill", "--all")):
                r = self.tn("tmux", *argv)
                self.assertExit(r, 3)
                self.assertIn("run: wsl", r.stderr)


class Hooks(TmuxCase):
    def test_status_counts_and_here(self):
        p = self.make_project("acme", repos=["shop-app"])
        self.seed(PLAIN, {"name": "acme-shop-app-00"})
        r = self.tn("status", "--json", cwd=p.repo("shop-app"))
        self.assertExit(r, 0)
        self.assertEqual(r.json["plugins"]["tmux"], ["2 sessions; here: acme-shop-app-00"])

    def test_status_without_tmux_says_nothing(self):
        self.unfake("tmux")
        r = self.tn("status", "--json")
        self.assertExit(r, 0)
        self.assertNotIn("tmux", r.json["plugins"])
        self.assertNotIn("tmux", r.json.get("errors") or {})

    def test_doctor_check(self):
        r = self.tn("doctor", "--json")
        rows = [x for x in r.json if x["plugin"] == "tmux"]
        self.assertEqual(rows[0]["check"], "tmux installed")
        self.assertEqual(rows[0]["status"], "ok")
        self.assertEqual(rows[0]["detail"], "tmux 3.4")

    def test_doctor_check_missing(self):
        self.unfake("tmux")
        r = self.tn("doctor", "--json")
        rows = [x for x in r.json if x["plugin"] == "tmux"]
        self.assertEqual(rows[0]["status"], "fail")
        self.assertEqual(rows[0]["fix"], "dot apply tmux")

    def test_completion_offers_session_names(self):
        self.seed(PLAIN, PLAIN2, CLAUDE)
        r = self.tn("__complete", "3", "--", "tn", "tmux", "attach", "wo")
        self.assertExit(r, 0)
        values = [line.split("\t")[0] for line in r.stdout.splitlines()]
        self.assertEqual(values, ["work", "workshop"])


class Parse(TmuxCase):
    def test_parse_tolerates_short_rows(self):
        mod = self.module()
        rows = mod.parse_sessions("a\t2\t0\t100\n\nb\n")
        self.assertEqual([r.name for r in rows], ["a", "b"])
        self.assertEqual(rows[1].windows, None)
        self.assertEqual(rows[0].to_json()["age_seconds"], NOW - 100)
