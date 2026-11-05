"""Tests for the codex plugin (docs/tn.md §7.3), against a fake `codex` on PATH."""

from __future__ import annotations

from unittest import mock

from tn.testing import TnTestCase
from tn.plugins import codex  # noqa: F401 - tn/plugins/__init__.py maps TN_PLUGIN_PATH

# A stand-in for the codex CLI. State lives in state_dir: "codex-logged-in" (signed in),
# "codex-daemon" (the app-server daemon runs). "codex-pair-fail" makes pair fail.
CODEX = r'''
li = state_dir / "codex-logged-in"
dm = state_dir / "codex-daemon"
a = argv
if a[:2] == ["login", "status"]:
    if li.exists():
        sys.stderr.write("Logged in using ChatGPT\n")
    else:
        sys.stderr.write("Not logged in\n")
    sys.exit(0)
if a[:1] == ["login"]:
    li.write_text(stdin or "browser")
    print("Successfully logged in")
    sys.exit(0)
if a[:4] == ["app-server", "daemon", "version"]:
    if not dm.exists():
        sys.stderr.write("error: could not connect to the app-server daemon\n")
        sys.exit(1)
    print(json.dumps({"status": "running", "cliVersion": "0.99.0", "appServerVersion": "0.99.1"}))
    sys.exit(0)
if a[:2] == ["remote-control", "start"]:
    if not li.exists():
        sys.stderr.write("Remote control is enabled on host but the connection is errored\n")
        sys.exit(1)
    dm.write_text("1")
    print("remote control started")
    sys.exit(0)
if a[:2] == ["remote-control", "pair"]:
    if (state_dir / "codex-pair-fail").exists():
        sys.exit(4)
    print("Pairing code: ABCD-1234")
    sys.exit(0)
if a[:2] == ["remote-control", "stop"]:
    if dm.exists():
        dm.unlink()
    sys.exit(0)
sys.stderr.write("fake codex: unexpected %r\n" % (a,))
sys.exit(2)
'''


class CodexCase(TnTestCase):
    def setUp(self):
        super().setUp()
        self.require_git()
        self.fake("codex", script=CODEX)

    def login_state(self, on: bool = True):
        p = self.state_dir / "codex-logged-in"
        if on:
            p.write_text("x")
        elif p.exists():
            p.unlink()

    def daemon(self, on: bool = True):
        p = self.state_dir / "codex-daemon"
        if on:
            p.write_text("1")
        elif p.exists():
            p.unlink()

    def codex_calls(self):
        return self.calls("codex")

    def changing_calls(self):
        """Calls other than the read-only queries."""
        return [c for c in self.codex_calls()
                if c[:2] != ["login", "status"] and c[:3] != ["app-server", "daemon", "version"]]


class Start(CodexCase):
    def test_not_installed(self):
        self.unfake("codex")
        r = self.tn("codex", "start")
        self.assertExit(r, 3)
        self.assertIn("run: dot apply codex", r.stderr)

    def test_not_logged_in_exits_3_before_anything_runs(self):
        r = self.tn("codex", "start")
        self.assertExit(r, 3)
        self.assertIn("run: tn codex login", r.stderr)
        self.assertEqual(self.changing_calls(), [])

    def test_starts_and_pairs_at_the_git_root(self):
        self.login_state()
        p = self.make_project("acme", repos=["shop-app"])
        sub = p.repo("shop-app") / "app"
        sub.mkdir()
        r = self.tn("codex", "start", cwd=sub)
        self.assertExit(r, 0)
        self.assertEqual(self.changing_calls(),
                         [["remote-control", "start"], ["remote-control", "pair"]])
        self.assertIn("Pairing code: ABCD-1234", r.stdout)
        self.assertIn("pairing code (only needed to link a new device):", r.stderr)
        self.assertIn("Directory: %s" % p.repo("shop-app"), r.stderr)
        self.assertIn("codex -C %s" % p.repo("shop-app"), r.stderr)
        self.assertTrue((self.state_dir / "codex-daemon").exists())

    def test_git_root_of_a_path_outside_the_roots(self):
        self.login_state()
        repo = self.make_repo(self.home / "work" / "tool")
        sub = repo / "lib"
        sub.mkdir()
        r = self.tn("codex", "start", "./lib", "--json", cwd=repo)
        self.assertExit(r, 0)
        self.assertEqual(r.json["dir"], str(repo))
        self.assertIn("(git root of %s)" % sub, r.stderr)

    def test_json(self):
        self.login_state()
        p = self.make_project("acme", repos=["shop-app"])
        r = self.tn("codex", "start", "acme", "--json")
        self.assertExit(r, 0)
        j = r.json
        self.assertEqual(j["dir"], str(p.repo("shop-app")))   # prefer_repo: the only repo
        self.assertEqual(j["context"], "acme/shop-app")
        self.assertEqual(j["daemon"], "running")
        self.assertEqual(j["pairing"], "Pairing code: ABCD-1234")
        self.assertIsNone(j["workspace_created"])

    def test_target_in_workspace(self):
        self.login_state()
        p = self.make_project("acme", repos=["shop-app", "shop-all"], workspaces=["src-02"])
        r = self.tn("codex", "start", "acme/shop-app", "--ws", "02", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json["dir"], str(p.repo("shop-app", "src-02")))
        self.assertEqual(r.json["context"], "acme/shop-app@02")

    def test_outside_roots_plain_dir(self):
        self.login_state()
        d = self.home / "scratch"
        d.mkdir()
        r = self.tn("codex", "start", "--json", cwd=d)
        self.assertExit(r, 0)
        self.assertEqual((r.json["dir"], r.json["context"]), (str(d), None))

    def test_unknown_target(self):
        self.login_state()
        r = self.tn("codex", "start", "nope")
        self.assertExit(r, 2)
        self.assertEqual(self.changing_calls(), [])

    def test_dry_run_changes_nothing(self):
        self.login_state()
        r = self.tn("-n", "codex", "start", "--json")
        self.assertExit(r, 0)
        self.assertEqual(self.changing_calls(), [])
        self.assertIn("would: run codex remote-control start", r.stderr)
        self.assertIn("would: run codex remote-control pair", r.stderr)
        self.assertTrue(r.json["dry_run"])
        self.assertIsNone(r.json["pairing"])

    def test_dry_run_text(self):
        self.login_state()
        r = self.tn("codex", "start", "-n")
        self.assertExit(r, 0)
        self.assertEqual(self.changing_calls(), [])
        self.assertIn("would: run codex remote-control pair", r.stderr)

    def test_pair_failure_exits_1(self):
        self.login_state()
        (self.state_dir / "codex-pair-fail").write_text("")
        r = self.tn("codex", "start")
        self.assertExit(r, 1)
        self.assertIn("pair", r.stderr)


class Ls(CodexCase):
    def test_stopped(self):
        r = self.tn("codex", "ls", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, [{"id": "daemon", "running": False, "status": None,
                                   "cli_version": None, "app_server_version": None,
                                   "logged_in": False}])

    def test_running(self):
        self.login_state()
        self.daemon()
        r = self.tn("codex", "ls", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, [{"id": "daemon", "running": True, "status": "running",
                                   "cli_version": "0.99.0", "app_server_version": "0.99.1",
                                   "logged_in": True}])

    def test_text_never_opens_the_browser(self):
        self.login_state()
        self.daemon()
        r = self.tn("codex", "ls")
        self.assertExit(r, 0)
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0].split(), ["DAEMON", "STATUS", "VERSION", "LOGIN"])
        self.assertIn("codex 0.99.0 / app-server 0.99.1", lines[1])
        self.assertTrue(lines[1].startswith("running"))
        self.assertIn("browse sessions: codex agents", r.stderr)
        self.assertNotIn(["agents"], self.codex_calls())

    def test_text_stopped_hints_start(self):
        r = self.tn("codex", "ls")
        self.assertExit(r, 0)
        self.assertTrue(r.stdout.splitlines()[1].startswith("stopped"))
        self.assertIn("tn codex start", r.stderr)
        self.assertIn("tn codex login", r.stderr)

    def test_unparsable_version_still_running(self):
        self.fake("codex", stdout="not json\n")
        r = self.tn("codex", "ls", "--json")
        self.assertExit(r, 0)
        self.assertTrue(r.json[0]["running"])
        self.assertIsNone(r.json[0]["status"])


class Attach(CodexCase):
    def test_by_name(self):
        r = self.tn("codex", "attach", "my-session")
        self.assertExit(r, 0)
        self.assertEqual(r.handoff[1:], ["resume", "my-session"])

    def test_exit_status_of_child(self):
        r = self.tn("codex", "attach", "x", handoff_exit=5)
        self.assertExit(r, 5)

    def test_picker_on_a_tty(self):
        r = self.tn("codex", "attach", tty=True)
        self.assertExit(r, 0)
        self.assertEqual(r.handoff[1:], ["resume", "--all"])

    def test_picker_needs_a_tty(self):
        r = self.tn("codex", "attach")
        self.assertExit(r, 2)
        self.assertIsNone(r.handoff)

    def test_json_rejected(self):
        r = self.tn("codex", "attach", "x", "--json")
        self.assertExit(r, 2)
        self.assertIsNone(r.handoff)
        r = self.tn("codex", "attach", "--json", tty=True)
        self.assertExit(r, 2)

    def test_dry_run(self):
        r = self.tn("-n", "codex", "attach", "x")
        self.assertExit(r, 0)
        self.assertIn("would: run", r.stderr)
        self.assertIsNone(r.handoff)


class Stop(CodexCase):
    def test_not_running(self):
        r = self.tn("codex", "stop", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, {"stopped": False})
        self.assertEqual(self.changing_calls(), [])

    def test_needs_confirmation_without_tty(self):
        self.daemon()
        r = self.tn("codex", "stop")
        self.assertExit(r, 2)
        self.assertIn("pass --yes to confirm", r.stderr)
        self.assertEqual(self.changing_calls(), [])

    def test_yes(self):
        self.daemon()
        r = self.tn("codex", "stop", "--yes", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, {"stopped": True})
        self.assertEqual(self.changing_calls(), [["remote-control", "stop"]])

    def test_tty_confirm_no_cancels(self):
        self.daemon()
        r = self.tn("codex", "stop", tty=True, stdin="n\n")
        self.assertExit(r, 1)
        self.assertIn("cancelled", r.stderr)
        self.assertEqual(self.changing_calls(), [])

    def test_tty_confirm_yes(self):
        self.daemon()
        r = self.tn("codex", "stop", tty=True, stdin="y\n")
        self.assertExit(r, 0)
        self.assertIn("Stop it?", r.stderr)
        self.assertEqual(self.changing_calls(), [["remote-control", "stop"]])

    def test_dry_run(self):
        self.daemon()
        r = self.tn("codex", "stop", "-ny")
        self.assertExit(r, 0)
        self.assertEqual(self.changing_calls(), [])
        self.assertIn("would: run codex remote-control stop", r.stderr)


class Login(CodexCase):
    def test_json_is_status_only(self):
        r = self.tn("codex", "login", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, {"logged_in": False, "status": "Not logged in"})
        self.assertEqual(self.changing_calls(), [])
        self.login_state()
        r = self.tn("codex", "login", "--json")
        self.assertEqual(r.json, {"logged_in": True, "status": "Logged in using ChatGPT"})

    def test_device_auth_without_a_browser(self):
        with mock.patch.object(codex, "_platform", return_value="linux"):
            r = self.tn("codex", "login")
        self.assertExit(r, 0)
        self.assertEqual(self.changing_calls(), [["login", "--device-auth"]])
        self.assertIn("currently: Not logged in", r.stderr)
        self.assertIn("now: Logged in using ChatGPT", r.stderr)

    def test_device_auth_over_ssh_even_with_display(self):
        with mock.patch.object(codex, "_platform", return_value="darwin"):
            r = self.tn("codex", "login", env={"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"})
        self.assertExit(r, 0)
        self.assertEqual(self.changing_calls(), [["login", "--device-auth"]])

    def test_browser_on_linux_with_display(self):
        with mock.patch.object(codex, "_platform", return_value="linux"):
            r = self.tn("codex", "login", env={"DISPLAY": ":0"})
        self.assertExit(r, 0)
        self.assertEqual(self.changing_calls(), [["login"]])
        self.assertIn("tn codex login --device-auth", r.stderr)

    def test_browser_on_macos(self):
        with mock.patch.object(codex, "_platform", return_value="darwin"):
            r = self.tn("codex", "login")
        self.assertEqual(self.changing_calls(), [["login"]])

    def test_signed_in_confirms(self):
        self.login_state()
        r = self.tn("codex", "login")
        self.assertExit(r, 2)
        self.assertIn("pass --yes", r.stderr)
        r = self.tn("codex", "login", tty=True, stdin="n\n")
        self.assertExit(r, 0)
        self.assertIn("keeping the current login", r.stderr)
        self.assertEqual(self.changing_calls(), [])
        r = self.tn("codex", "login", "--device-auth", "--yes")
        self.assertExit(r, 0)
        self.assertEqual(self.changing_calls(), [["login", "--device-auth"]])

    def test_api_key_from_stdin(self):
        r = self.tn("codex", "login", "--with-api-key", stdin="sk-test-not-a-key\n")
        self.assertExit(r, 0)
        recs = [c for c in self.call_records("codex") if c["argv"][:1] == ["login"]
                and c["argv"][1:2] != ["status"]]
        self.assertEqual(recs[0]["argv"], ["login", "--with-api-key"])
        self.assertEqual(recs[0]["stdin"], "sk-test-not-a-key\n")

    def test_api_key_empty_stdin(self):
        r = self.tn("codex", "login", "--with-access-token")
        self.assertExit(r, 2)
        self.assertEqual(self.changing_calls(), [])

    def test_one_flag_only(self):
        r = self.tn("codex", "login", "--device-auth", "--with-api-key")
        self.assertExit(r, 2)

    def test_dry_run(self):
        with mock.patch.object(codex, "_platform", return_value="linux"):
            r = self.tn("-n", "codex", "login")
        self.assertExit(r, 0)
        self.assertEqual(self.changing_calls(), [])
        self.assertIn("would: run codex login --device-auth", r.stderr)


class Hooks(CodexCase):
    def test_sessions_when_running(self):
        self.daemon()
        r = self.tn("sessions", "--json")
        self.assertExit(r, 0)
        rows = [s for s in r.json if s["kind"] == "codex"]
        self.assertEqual(len(rows), 1)
        s = rows[0]
        self.assertEqual((s["id"], s["name"], s["status"], s["attach"]),
                         ("daemon", "codex daemon", "running", ["codex", "resume", "--all"]))
        self.assertIsNone(s["context"])

    def test_no_sessions_when_stopped_or_missing(self):
        r = self.tn("sessions", "--json")
        self.assertEqual([s for s in (r.json or []) if s["kind"] == "codex"], [])
        self.unfake("codex")
        r = self.tn("sessions", "--json")
        self.assertEqual([s for s in (r.json or []) if s["kind"] == "codex"], [])

    def test_sessions_attach_hands_off_to_codex_picker(self):
        self.daemon()
        r = self.tn("sessions", "attach", "daemon")
        self.assertExit(r, 0)
        self.assertEqual(r.handoff, ["codex", "resume", "--all"])

    def test_status(self):
        r = self.tn("status", "--json")
        self.assertEqual(r.json["plugins"].get("codex"), ["daemon stopped"])
        self.daemon()
        r = self.tn("status", "--json")
        self.assertEqual(r.json["plugins"].get("codex"), ["daemon running"])

    def rows(self):
        r = self.tn("doctor", "--json")
        return {c["check"]: c for c in r.json if c["plugin"] == "codex"}

    def test_doctor(self):
        rows = self.rows()
        self.assertEqual(rows["codex installed"]["status"], "ok")
        bad = rows["codex: not signed in"]
        self.assertEqual((bad["status"], bad["fix"]), ("fail", "tn codex login"))
        self.login_state()
        rows = self.rows()
        self.assertEqual(rows["logged in"]["status"], "ok")
        self.assertEqual(rows["logged in"]["detail"], "Logged in using ChatGPT")

    def test_doctor_not_installed(self):
        self.unfake("codex")
        rows = self.rows()
        self.assertEqual((rows["codex installed"]["status"], rows["codex installed"]["fix"]),
                         ("fail", "dot apply codex"))
        self.assertEqual(rows["logged in"]["status"], "fail")


class Plugin_(TnTestCase):
    def test_declaration(self):
        pl = self.load_plugin("codex")
        self.assertEqual(pl.groups, ["codex"])
        self.assertEqual(pl.requires, ["projects"])
        verbs = sorted(c.name for c in pl.commands)
        self.assertEqual(verbs, ["attach", "login", "ls", "start", "stop"])
