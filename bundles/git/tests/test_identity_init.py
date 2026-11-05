"""tn git as / whoami / init (docs/tn.md §7.5)."""

from __future__ import annotations

from tn import Config
from tn.plugins import git as gitplugin  # noqa: E402

from _gitbase import TEST_EMAIL, TEST_NAME, GitCase


class As(GitCase):
    def setUp(self):
        super().setUp()
        self.r = self.repo()

    def who(self):
        return self.local_config(self.r, "user.name"), self.local_config(self.r, "user.email")

    def test_exact_key(self):
        r = self.ok(self.tn("git", "as", "jane_roe", "--json", cwd=self.r))
        self.assertEqual(r.json, {"key": "jane_roe", "name": "Jane Roe",
                                  "email": "jane.roe@example.com", "repo": str(self.r)})
        self.assertEqual(self.who(), ("Jane Roe", "jane.roe@example.com"))

    def test_text_output(self):
        r = self.ok(self.tn("git", "as", "bobsmith", cwd=self.r))
        self.assertEqual(r.stdout, "committer: Bob Smith <bobsmith@example.com>\n")

    def test_alias_wins_over_prefixes(self):
        r = self.ok(self.tn("git", "as", "alex", "--json", cwd=self.r))
        self.assertEqual(r.json["key"], "alex-work")

    def test_fuzzy_prefix_name_and_email(self):
        self.assertEqual(self.ok(self.tn("git", "as", "jane", "--json", cwd=self.r)).json["key"],
                         "jane_roe")
        self.assertEqual(self.ok(self.tn("git", "as", "brown", "--json",
                                         cwd=self.r)).json["key"], "dan_brown")
        self.assertEqual(self.ok(self.tn("git", "as", "Carol White", "--json",
                                         cwd=self.r)).json["key"], "carolw")

    def test_ambiguous_without_tty(self):
        r = self.tn("git", "as", "it", "--json", cwd=self.r)
        self.assertExit(r, 2)
        self.assertEqual(sorted(r.error["choices"]), ["bobsmith", "carolw"])
        self.assertEqual(self.git(self.r, "config", "--local", "--list").count("user."), 0)

    def test_ambiguous_picks_on_a_tty(self):
        self.ok(self.tn("git", "as", "it", cwd=self.r, tty=True, stdin="2\n"))
        self.assertEqual(self.who(), ("Carol White", "carolw@example.com"))

    def test_no_match(self):
        r = self.tn("git", "as", "zzzz", "--json", cwd=self.r)
        self.assertExit(r, 2)
        self.assertEqual(r.error["hint"], "tn git as --list")

    def test_me(self):
        r = self.ok(self.tn("git", "as", "me", "--json", cwd=self.r))
        self.assertEqual((r.json["name"], r.json["email"]), (TEST_NAME, TEST_EMAIL))

    def test_me_missing(self):
        r = self.tn("git", "as", "me", "--json", cwd=self.r, env={"MY_NAME": None})
        self.assertExit(r, 3)
        self.assertEqual(r.error["fix"], "set MY_NAME/MY_EMAIL (dot apply asks for them once; ~/.config/dot/local.env)")

    def test_list_works_anywhere(self):
        r = self.ok(self.tn("git", "as", "--list", "--json", cwd=self.home))
        keys = [p["key"] for p in r.json]
        self.assertIn("jane_roe", keys)
        self.assertIn("me", keys)
        self.assertEqual(r.json[0], {"key": "jane_roe", "name": "Jane Roe",
                                     "email": "jane.roe@example.com", "aliases": []})
        text = self.ok(self.tn("git", "as", "--list", cwd=self.home))
        self.assertTrue(text.stdout.startswith("KEY"))

    def test_needs_a_repo(self):
        self.assertExit(self.tn("git", "as", "bobsmith", cwd=self.home), 2)

    def test_dry_run(self):
        r = self.ok(self.tn("git", "as", "bobsmith", "-n", cwd=self.r))
        self.assertIn("would: run git -C", r.stderr)
        self.assertNotIn("user.email", self.git(self.r, "config", "--local", "--list"))

    def test_matcher(self):
        people = Config.load().people()
        self.assertEqual([p.key for p in gitplugin.match_people("BOBSMITH", people)], ["bobsmith"])
        self.assertEqual([p.key for p in gitplugin.match_people("carolw@example.com", people)],
                         ["carolw"])
        self.assertEqual([p.key for p in gitplugin.match_people("bbsh", people)], ["bobsmith"])


class Whoami(GitCase):
    def test_local_matches_expected(self):
        r = self.repo(toml='identity = "alex-work"\n')
        self.git(r, "config", "user.name", "Alex Work")
        self.git(r, "config", "user.email", "alex@example.com")
        res = self.ok(self.tn("git", "whoami", "--json", cwd=r))
        self.assertEqual(res.json, {
            "name": "Alex Work", "email": "alex@example.com", "source": "local",
            "expected": {"key": "alex-work", "name": "Alex Work",
                         "email": "alex@example.com"}, "matches": True})

    def test_global_and_mismatch(self):
        r = self.repo(toml='identity = "alex-work"\n')
        (self.home / ".gitconfig").write_text("[user]\n\tname = G\n\temail = g@example.com\n",
                                              encoding="utf-8")
        res = self.ok(self.tn("git", "whoami", "--json", cwd=r))
        self.assertEqual((res.json["email"], res.json["source"], res.json["matches"]),
                         ("g@example.com", "global", False))
        text = self.ok(self.tn("git", "whoami", cwd=r))
        self.assertIn("differs: tn git as alex-work", text.stdout)

    def test_unset_expects_me(self):
        r = self.repo()
        res = self.ok(self.tn("git", "whoami", "--json", cwd=r))
        self.assertEqual((res.json["source"], res.json["email"], res.json["matches"]),
                         ("unset", None, False))
        self.assertEqual(res.json["expected"]["key"], "me")

    def test_no_expected_identity(self):
        r = self.make_repo(self.home / "loose")
        res = self.ok(self.tn("git", "whoami", "--json", cwd=r, env={"MY_NAME": None}))
        self.assertIsNone(res.json["expected"])
        self.assertIsNone(res.json["matches"])


class Init(GitCase):
    def test_new_directory(self):
        d = self.projects / "acme" / "src" / "fresh"
        d.mkdir(parents=True)
        self.project_toml("acme", 'identity = "bobsmith"\nforge = "work"\n')
        r = self.ok(self.tn("git", "init", "--forge", "--json", cwd=d))
        self.assertEqual(r.json, {
            "path": str(d), "initialized": True, "gitattributes": True,
            "identity": {"key": "bobsmith", "name": "Bob Smith", "email": "bobsmith@example.com"},
            "remote": {"name": "gitlab", "url": "git@gitlab.example.com:acme/fresh.git"}})
        self.assertTrue((d / ".git").is_dir())
        self.assertEqual((d / ".gitattributes").read_text(), "* text=auto\n*.sh text eol=lf\n")
        self.assertEqual(self.local_config(d, "user.email"), "bobsmith@example.com")

    def test_idempotent(self):
        r = self.repo()
        (r / ".gitattributes").write_text("custom\n", encoding="utf-8")
        res = self.ok(self.tn("git", "init", "--json", cwd=r / "."))
        self.assertEqual((res.json["initialized"], res.json["gitattributes"], res.json["identity"]),
                         (False, False, None))
        self.assertEqual((r / ".gitattributes").read_text(), "custom\n")

    def test_existing_repo_gets_gitattributes_from_subdir(self):
        r = self.repo()
        sub = r / "sub"
        sub.mkdir()
        res = self.ok(self.tn("git", "init", "--json", cwd=sub))
        self.assertEqual(res.json["path"], str(r))
        self.assertTrue((r / ".gitattributes").is_file())
        self.assertFalse((sub / ".git").exists())

    def test_forge_without_project_forge(self):
        d = self.home / "x"
        d.mkdir()
        self.assertExit(self.tn("git", "init", "--forge", cwd=d), 2)
        self.assertExit(self.tn("git", "init", "--forge", "nope", cwd=d), 2)
        self.assertFalse((d / ".git").exists())

    def test_dry_run(self):
        d = self.home / "x"
        d.mkdir()
        r = self.ok(self.tn("git", "init", "-n", "--json", cwd=d))
        self.assertTrue(r.json["dry_run"])
        self.assertEqual(list(d.iterdir()), [])
