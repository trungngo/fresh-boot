"""tn claude start."""

from __future__ import annotations

import json
import os

from _base import ClaudeCase, claude, mock_windows

UUID = "0f3c2a1e-7b8d-4c5e-9a1b-2c3d4e5f6a7b"
OTHER = "11111111-2222-4333-8444-555555555555"


class Start(ClaudeCase):
    def setUp(self):
        super().setUp()
        self.p = self.make_project("acme", repos=["shop-web", "shop-all"],
                                   workspaces=["src-02"])
        self.repo = self.p.repo("shop-web", "src-02")

    def start(self, *argv, code=0, **kw):
        r = self.tn("claude", "start", *argv, **kw)
        self.assertExit(r, code)
        return r

    def test_happy_path_json(self):
        r = self.start("--json", cwd=self.repo)
        j = r.json
        self.assertEqual(j["tmux"], "claude-acme-shop-web-02")
        self.assertEqual(j["name"], "Acme Shop Web #T1-02")
        self.assertEqual(j["dir"], str(self.repo))
        self.assertEqual(j["context"], "acme/shop-web@02")
        self.assertRegex(j["uuid"], claude.UUID_RE)
        self.assertEqual((j["resumed"], j["trusted"], j["trust_changed"],
                          j["workspace_created"]), (False, True, True, None))
        argv = self.new_session_argv()
        self.assertEqual(argv[:6], ["new-session", "-d", "-s", "claude-acme-shop-web-02",
                                    "-c", str(self.repo)])
        self.assertIn("PATH=" + os.environ["PATH"], argv)
        self.assertIn("MY_MACHINE=T1", argv)
        i = argv.index(str(self.bin / "claude"))
        self.assertEqual(argv[i + 1:i + 7], ["--session-id", j["uuid"], "--remote-control",
                                             j["name"], "-n", j["name"]])
        opts = self.tmux_state()["claude-acme-shop-web-02"]["options"]
        self.assertEqual(opts, {"@claude_name": j["name"], "@claude_dir": str(self.repo),
                                "@claude_uuid": j["uuid"], "@tn_context": "acme/shop-web@02",
                                "@tn_kind": "claude"})
        data = json.loads(self.claude_json().read_text())
        self.assertIs(data["projects"][claude.project_key(self.repo)]["hasTrustDialogAccepted"], True)

    def test_options_land_on_the_new_session_when_started_inside_tmux(self):
        # Without a target, the chained set-options retag the tmux session tn was run from.
        self.seed_session("claude-caller", title="Caller #T1", uuid=OTHER)
        before = self.tmux_state()["claude-caller"]["options"]
        j = self.start("--json", cwd=self.repo,
                       env={"FAKE_TMUX_CALLER": "claude-caller"}).json
        state = self.tmux_state()
        self.assertEqual(state["claude-caller"]["options"], before)
        self.assertEqual(state[j["tmux"]]["options"]["@claude_uuid"], j["uuid"])

    def test_tmux_does_not_inherit_the_shell_function_env(self):
        # The tmux server this starts (and every shell under it) would otherwise keep the
        # function's temp TN_CD_FILE and TN_SHELL=1 after the function deleted the file.
        self.start("--json", cwd=self.repo, env={"TN_SHELL": "1"})
        env = self.tmux_state()["claude-acme-shop-web-02"]["env"]
        self.assertEqual((env["TN_CD_FILE"], env["TN_SHELL"]), (None, None))

    def test_claude_does_not_inherit_a_parent_claudes_markers(self):
        # Started from inside a Claude session, the new claude would see
        # CLAUDE_CODE_CHILD_SESSION and turn its transcript off.
        self.start("--json", cwd=self.repo,
                   env={"CLAUDECODE": "1", "CLAUDE_CODE_CHILD_SESSION": "1"})
        env = self.tmux_state()["claude-acme-shop-web-02"]["env"]
        self.assertEqual((env["CLAUDECODE"], env["CLAUDE_CODE_CHILD_SESSION"]), (None, None))

    def test_text_output(self):
        r = self.start(cwd=self.repo)
        self.assertEqual(r.stdout, "claude-acme-shop-web-02\n")
        for s in ("trusted ", "Directory: ", "Name:      Acme Shop Web #T1-02",
                  "Tmux:      claude-acme-shop-web-02", "Session:   ",
                  "attach: tn claude attach claude-acme-shop-web-02"):
            self.assertIn(s, r.stderr)

    def test_subdirectory_starts_at_the_repo(self):
        sub = self.p.repo("shop-web") / "app" / "models"
        sub.mkdir(parents=True)
        r = self.start("--json", cwd=sub)
        self.assertEqual(r.json["dir"], str(self.p.repo("shop-web")))
        self.assertEqual(r.json["tmux"], "claude-acme-shop-web-00")
        self.assertEqual(r.json["name"], "Acme Shop Web #T1-00")

    def test_git_root_outside_the_roots(self):
        repo = self.make_repo(self.home / "code" / "tool")
        sub = repo / "src"
        sub.mkdir()
        r = self.start("--json", cwd=sub)
        self.assertEqual((r.json["dir"], r.json["tmux"], r.json["name"]),
                         (str(repo), "claude-tool", "Tool #T1"))
        self.assertIn("(git root of ~/code/tool/src)", r.stderr)

    def test_target_by_name(self):
        r = self.start("acme/shop-all", "--json")
        self.assertEqual(r.json["dir"], str(self.p.repo("shop-all")))
        self.assertEqual(r.json["tmux"], "claude-acme-shop-all-00")

    def test_target_with_ws(self):
        r = self.start("acme/shop-web", "--ws", "02", "--json")
        self.assertEqual(r.json["dir"], str(self.repo))

    def test_project_with_one_repo_resolves_to_it(self):
        one = self.make_project("hooli", repos=["hooli-even"])
        r = self.start("hooli", "--json")
        self.assertEqual(r.json["dir"], str(one.repo("hooli-even")))
        self.assertEqual(r.json["name"], "Hooli Even #T1-00")
        self.assertEqual(r.json["tmux"], "claude-hooli-even-00")

    def test_project_root_session(self):
        r = self.start("acme", "--json")
        self.assertEqual(r.json["dir"], str(self.p.dir))
        self.assertEqual((r.json["tmux"], r.json["name"]), ("claude-acme", "Acme #T1"))

    def test_outside_the_roots(self):
        d = self.home / "scratch"
        d.mkdir()
        r = self.start("--json", cwd=d)
        self.assertEqual((r.json["tmux"], r.json["name"], r.json["context"]),
                         ("claude-scratch", "Scratch #T1", None))
        self.assertEqual(self.tmux_state()["claude-scratch"]["options"]["@tn_context"], "")

    def test_explicit_name(self):
        r = self.start("--name", "My Big: Thing.", "--json", cwd=self.repo)
        self.assertEqual((r.json["tmux"], r.json["name"]), ("claude-my-big-thing", "My Big: Thing."))
        argv = self.new_session_argv()
        self.assertIn("My Big: Thing.", argv)

    def test_empty_name_is_usage(self):
        r = self.start("--name", "  ", code=2, cwd=self.repo)
        self.assertEqual(self.calls("tmux"), [])
        self.assertIn("--name", r.stderr)

    def test_unknown_target_is_usage(self):
        r = self.start("nope", "--json", code=2)
        self.assertIn("nope", r.error["message"])

    def test_ambiguous_target_without_tty_gives_choices(self):
        self.make_project("other", repos=["shop-all"])
        r = self.start("shop-all", "--json", code=2)
        self.assertEqual(len(r.error["choices"]), 2)

    def test_already_running(self):
        self.seed_session("claude-acme-shop-web-02", directory=str(self.repo))
        r = self.start(cwd=self.repo, code=1)
        self.assertIn("already running in tmux session claude-acme-shop-web-02", r.stderr)
        self.assertIn("run: tn claude attach claude-acme-shop-web-02", r.stderr)
        self.assertNotIn("new-session", self.tmux_verbs())

    def test_machine_unset_is_exit_3(self):
        self.no_machine()
        r = self.start(cwd=self.repo, code=3)
        self.assertIn("MY_MACHINE", r.stderr)
        self.assertIn("run: tn config set machine <name>", r.stderr)
        self.assertNotIn("new-session", self.tmux_verbs())

    def test_machine_unset_but_name_given(self):
        self.no_machine()
        r = self.start("--name", "Adhoc", "--json", cwd=self.repo)
        self.assertNotIn("MY_MACHINE=", " ".join(self.new_session_argv()))
        self.assertEqual(r.json["tmux"], "claude-adhoc")

    def test_tmux_missing_is_exit_3(self):
        self.unfake("tmux")
        r = self.start(cwd=self.repo, code=3)
        self.assertIn("run: dot apply tmux", r.stderr)

    def test_claude_missing_is_exit_3(self):
        self.unfake("claude")
        r = self.start("--json", cwd=self.repo, code=3)
        self.assertEqual(r.error["fix"], "dot apply claude")

    def test_windows_opens_a_terminal_tab(self):
        self.fake("wt")
        self.set_agents([])
        with mock_windows():
            r = self.start("--json", cwd=self.repo)
        j = r.json
        argv = self.calls("wt")[0]
        self.assertEqual(argv[:3], ["-w", "0", "new-tab"])
        self.assertEqual(argv[argv.index("--title") + 1], j["name"])
        self.assertEqual(argv[argv.index("-d") + 1], str(self.repo))
        i = argv.index("--")
        self.assertEqual(argv[i + 1:], [str(self.bin / "claude"), "--session-id", j["uuid"],
                                        "--remote-control", j["name"], "-n", j["name"]])
        self.assertEqual(self.tmux_verbs(), [])
        reg = json.loads(claude.registry_path().read_text())
        self.assertEqual([(e["name"], e["uuid"], e["dir"]) for e in reg],
                         [(j["tmux"], j["uuid"], str(self.repo))])

    def test_windows_without_wt_uses_cmd_start(self):
        self.fake("cmd")
        with mock_windows():
            self.start("--json", cwd=self.repo)
        self.assertEqual(self.calls("cmd")[0][:5], ["/c", "start", "", "/D", str(self.repo)])

    def test_claude_dies_at_once(self):
        (self.state_dir / "tmux-die").write_text("")
        r = self.start(cwd=self.repo, code=1)
        self.assertIn("claude exited straight away", r.stderr)
        self.assertRegex(r.stderr, r"run: cd .*shop-web && claude --session-id [0-9a-f-]+ "
                                   r"--remote-control 'Acme Shop Web #T1-02'")

    def test_first_run_setup_not_done_is_exit_3(self):
        # claude would sit at its theme / login screens in the detached session, still alive.
        for content in (None, {"numStartups": 1}, {"hasCompletedOnboarding": False}):
            with self.subTest(content=content):
                if content is None:
                    self.claude_json().unlink(missing_ok=True)
                else:
                    self.claude_json().write_text(json.dumps(content))
                r = self.start("--json", cwd=self.repo, code=3)
                self.assertIn("first-run", r.error["message"])
                self.assertEqual(r.error["fix"], "claude")
                self.assertNotIn("new-session", self.tmux_verbs())

    def test_dry_run_changes_nothing(self):
        r = self.start("-n", "--json", cwd=self.repo)
        self.assertTrue(r.json["dry_run"])
        self.assertNotIn("new-session", self.tmux_verbs())
        self.assertNotIn("projects", json.loads(self.claude_json().read_text()))
        self.assertIn("would: run ", r.stderr)
        self.assertIn("new-session", r.stderr)

    # -- trust -------------------------------------------------------------------------------
    def test_trust_keeps_other_keys_and_is_idempotent(self):
        self.claude_json().write_text(json.dumps({"numStartups": 3, "hasCompletedOnboarding": True, "projects": {
            "/else": {"hasTrustDialogAccepted": False, "x": 1}}}))
        os.chmod(self.claude_json(), 0o600)
        self.start(cwd=self.repo)
        data = json.loads(self.claude_json().read_text())
        self.assertEqual(data["numStartups"], 3)
        self.assertEqual(data["projects"]["/else"], {"hasTrustDialogAccepted": False, "x": 1})
        self.assertTrue(data["projects"][claude.project_key(self.repo)]["hasTrustDialogAccepted"])
        if os.name != "nt":
            self.assertEqual(os.stat(self.claude_json()).st_mode & 0o777, 0o600)
        self.tn("claude", "stop", "claude-acme-shop-web-02")
        r = self.start("--json", cwd=self.repo)
        self.assertEqual((r.json["trusted"], r.json["trust_changed"]), (True, False))
        self.assertNotIn("trusted ", r.stderr)

    def test_trust_key_on_windows_uses_forward_slashes(self):
        # Claude Code on Windows reads projects["C:/Users/alex/repo"]; a backslash key is ignored.
        with mock_windows():
            self.assertEqual(claude.project_key("C:\\Users\\alex\\repo"), "C:/Users/alex/repo")
            claude.trust("C:\\Users\\alex\\repo")
            self.assertTrue(claude.is_trusted("C:\\Users\\alex\\repo"))
        projects = json.loads(self.claude_json().read_text())["projects"]
        self.assertEqual(list(projects), ["C:/Users/alex/repo"])

    def test_no_trust(self):
        r = self.start("--no-trust", "--json", cwd=self.repo)
        self.assertNotIn("projects", json.loads(self.claude_json().read_text()))
        self.assertEqual((r.json["trusted"], r.json["trust_changed"]), (False, False))

    def test_config_trust_false(self):
        self.config("[claude]\ntrust = false\n")
        self.start(cwd=self.repo)
        self.assertNotIn("projects", json.loads(self.claude_json().read_text()))

    def test_invalid_claude_json_is_left_alone(self):
        self.claude_json().write_text("{not json")
        r = self.start(cwd=self.repo, code=1)
        self.assertIn("is not valid JSON", r.stderr)
        self.assertEqual(self.claude_json().read_text(), "{not json")
        self.assertNotIn("new-session", self.tmux_verbs())

    # -- resume ------------------------------------------------------------------------------
    def test_resume_latest(self):
        d = self.transcripts(self.repo)
        (d / (OTHER + ".jsonl")).write_text("{}\n")
        (d / (UUID + ".jsonl")).write_text("{}\n")
        os.utime(d / (OTHER + ".jsonl"), (1000, 1000))
        r = self.start("--resume", "--json", cwd=self.repo)
        self.assertEqual((r.json["uuid"], r.json["resumed"]), (UUID, True))
        argv = self.new_session_argv()
        i = argv.index("--resume")
        self.assertEqual(argv[i + 1], UUID)
        self.assertNotIn("--session-id", argv)

    def test_resume_takes_a_target_after_it(self):
        d = self.transcripts(self.p.repo("shop-all"))
        (d / (UUID + ".jsonl")).write_text("{}\n")
        r = self.start("--resume", "acme/shop-all", "--json")
        self.assertEqual((r.json["dir"], r.json["uuid"]), (str(self.p.repo("shop-all")), UUID))

    def test_resume_explicit_uuid(self):
        r = self.start(str(self.repo), "--resume", UUID.upper(), "--json")
        self.assertEqual(r.json["uuid"], UUID)

    def test_resume_nothing_to_resume(self):
        r = self.start("--resume", cwd=self.repo, code=1)
        self.assertIn("no conversation to resume in", r.stderr)

    def test_resume_short_id_is_usage(self):
        r = self.start("--resume", "0f3c2a1e", "--json", cwd=self.repo, code=2)
        self.assertIn("full uuid", r.error["message"])

    def test_resume_live_outside_tmux(self):
        self.set_agents([{"sessionId": UUID, "pid": os.getpid(), "status": "idle"}])
        r = self.start("--resume", UUID, cwd=self.repo, code=1)
        self.assertIn("running outside tmux (pid %d)" % os.getpid(), r.stderr)
        self.assertNotIn("new-session", self.tmux_verbs())

    def test_resume_dead_or_missing_pid_is_fine(self):
        self.set_agents([{"sessionId": UUID, "pid": 0}, {"sessionId": UUID},
                         {"sessionId": UUID, "pid": True}])
        self.start("--resume", UUID, cwd=self.repo)

    def test_uuid_already_running_in_tmux(self):
        self.seed_session("claude-elsewhere", uuid=UUID)
        r = self.start("--resume", UUID, cwd=self.repo, code=1)
        self.assertIn("conversation %s is already running" % UUID, r.stderr)
        self.assertIn("run: tn claude attach claude-elsewhere", r.stderr)

    # -- workspaces --------------------------------------------------------------------------
    def test_ws_new(self):
        r = self.start("acme/shop-web", "--ws", "new", "--json")
        self.assertEqual(r.json["workspace_created"], "src-01")
        self.assertEqual(r.json["dir"], str(self.p.repo("shop-web", "src-01")))
        self.assertEqual(r.json["tmux"], "claude-acme-shop-web-01")
        self.assertTrue((self.p.repo("shop-web", "src-01") / ".git").is_dir())

    def test_missing_ws_is_usage(self):
        r = self.start("acme/shop-web", "--ws", "07", "--json", code=2)
        self.assertIn("tn ws new 07", r.error["message"])

