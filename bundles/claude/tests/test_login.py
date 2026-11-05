"""tn claude login, and the doctor checks."""

from __future__ import annotations

import json
import os

from _base import LOGGED_IN, ClaudeCase, mock_windows


class Login(ClaudeCase):
    def login_calls(self):
        return [c for c in self.calls("claude") if c[:2] == ["auth", "login"]]

    def test_json_is_status_only(self):
        self.set_auth(LOGGED_IN)
        r = self.tn("claude", "login", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, {"logged_in": True, "email": "me@example.com",
                                  "auth_method": "claude.ai", "subscription": "max"})
        self.assertEqual(self.login_calls(), [])

    def test_json_logged_out(self):
        r = self.tn("claude", "login", "--json")
        self.assertEqual(r.json, {"logged_in": False, "email": None, "auth_method": None,
                                  "subscription": None})

    def test_logs_in_when_signed_out(self):
        r = self.tn("claude", "login", "--console", "--email", "a@b.c", "--", "--extra")
        self.assertExit(r, 0)
        self.assertEqual(self.login_calls(), [["auth", "login", "--console", "--email", "a@b.c",
                                               "--extra"]])
        self.assertIn("currently: not signed in", r.stderr)
        self.assertIn("now: new@example.com via claude.ai (max)", r.stderr)

    def test_login_does_not_inherit_the_shell_function_env(self):
        r = self.tn("claude", "login", env={"TN_SHELL": "1"})
        self.assertExit(r, 0)
        env = json.loads((self.state_dir / "login-env.json").read_text())
        self.assertEqual(env, {"TN_CD_FILE": None, "TN_SHELL": None})

    def test_signed_in_asks_first(self):
        self.set_auth(LOGGED_IN)
        r = self.tn("claude", "login")
        self.assertExit(r, 2)
        self.assertIn("sign in again, replacing this? — pass --yes to confirm", r.stderr)
        self.assertEqual(self.login_calls(), [])
        r = self.tn("claude", "login", tty=True, stdin="n\n")
        self.assertExit(r, 0)
        self.assertIn("keeping the current login", r.stderr)
        self.assertEqual(self.login_calls(), [])
        r = self.tn("claude", "login", "--sso", "--yes")
        self.assertExit(r, 0)
        self.assertEqual(self.login_calls(), [["auth", "login", "--sso"]])
        self.assertIn("currently: me@example.com via claude.ai (max)", r.stderr)

    def test_dry_run(self):
        self.set_auth(LOGGED_IN)
        r = self.tn("claude", "login", "-n")
        self.assertExit(r, 0)
        self.assertEqual(self.login_calls(), [])
        self.assertIn("would: run ", r.stderr)

    def test_unreadable_status(self):
        self.set_auth("oops")
        r = self.tn("claude", "login", "-n")
        self.assertIn("currently: unknown", r.stderr)

    def test_claude_missing(self):
        self.unfake("claude")
        r = self.tn("claude", "login")
        self.assertExit(r, 3)
        self.assertIn("run: dot apply claude", r.stderr)

    def test_works_on_windows(self):
        with mock_windows():
            r = self.tn("claude", "login", "--json")
        self.assertExit(r, 0)


class Doctor(ClaudeCase):
    def rows(self):
        r = self.tn("doctor", "--json")
        return {x["check"]: x for x in r.json if x["plugin"] == "claude"}

    def test_all_ok(self):
        self.set_auth(LOGGED_IN)
        rows = self.rows()
        self.assertEqual({k: v["status"] for k, v in rows.items()},
                         {"claude installed": "ok", "tmux installed": "ok", "logged in": "ok",
                          "first-run setup done": "ok", "MY_MACHINE set": "ok"})
        self.assertEqual(rows["logged in"]["detail"], "me@example.com via claude.ai (max)")

    def test_failures_carry_fixes(self):
        self.unfake("tmux")
        os.environ.pop("MY_MACHINE")
        self.claude_json().write_text("{}")
        rows = self.rows()
        self.assertEqual((rows["first-run setup done"]["status"],
                          rows["first-run setup done"]["fix"]), ("fail", "claude"))
        self.assertEqual((rows["logged in"]["status"], rows["logged in"]["fix"]),
                         ("fail", "tn claude login"))
        self.assertEqual((rows["tmux installed"]["status"], rows["tmux installed"]["fix"]),
                         ("fail", "dot apply tmux"))
        self.assertEqual((rows["MY_MACHINE set"]["status"], rows["MY_MACHINE set"]["fix"]),
                         ("fail", "tn config set machine <name>"))

    def test_claude_missing(self):
        self.unfake("claude")
        rows = self.rows()
        self.assertEqual(rows["claude installed"]["fix"], "dot apply claude")
        self.assertEqual(rows["logged in"]["status"], "fail")
        self.assertEqual(rows["first-run setup done"]["fix"], "dot apply claude")
