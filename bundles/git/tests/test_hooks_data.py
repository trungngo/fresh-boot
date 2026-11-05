"""Status and doctor hooks, completers, and the config fragments the bundle ships."""

from __future__ import annotations

import os
import shutil
import tomllib

from tn import Config

from _gitbase import BUNDLE, GH_FAKE, GitCase


class Status(GitCase):
    def test_line(self):
        r = self.repo()
        self.published(r)
        self.commit(r, "a.txt")
        (r / "dirty.txt").write_text("x", encoding="utf-8")
        res = self.ok(self.tn("status", "--json", cwd=r))
        self.assertEqual(res.json["plugins"]["git"], ["main, 1 changed, ahead 1"])

    def test_no_upstream_and_outside(self):
        r = self.repo()
        res = self.ok(self.tn("status", "--json", cwd=r))
        self.assertEqual(res.json["plugins"]["git"], ["main, 0 changed, no upstream"])
        res = self.ok(self.tn("status", "--json", cwd=self.home))
        self.assertNotIn("git", res.json["plugins"])


class Doctor(GitCase):
    def rows(self, **kw):
        r = self.tn("doctor", "--json", **kw)
        return {row["check"]: row for row in r.json if row["plugin"] == "git"}

    def problem(self, start, **kw):
        """A failed check's row: its message is the check column (tn doctor)."""
        found = [row for c, row in self.rows(**kw).items() if c.startswith(start)]
        self.assertEqual(len(found), 1, self.rows(**kw))
        return found[0]

    def test_identity_mismatch_is_a_warning(self):
        p = self.make_project("acme", repos=["good", "bad"], workspaces=["src-01"],
                              toml='identity = "bobsmith"\n')
        for ws in ("src", "src-01"):
            self.git(p.repo("good", ws), "config", "user.email", "BobSmith@example.com")
        self.git(p.repo("bad"), "config", "user.email", "other@example.com")
        self.make_project("free", repos=["x"])
        row = self.problem("identity of ")
        self.assertEqual(row["status"], "warn")
        self.assertIn("acme/src/bad is other@example.com, tn.toml says bobsmith@example.com"
                      " (and 1 more)", row["check"])
        self.assertEqual(row["fix"], "tn -C %s git as bobsmith" % p.repo("bad"))

    def test_identity_ok(self):
        p = self.make_project("acme", repos=["good"], toml='identity = "bobsmith"\n')
        self.git(p.repo("good"), "config", "user.email", "bobsmith@example.com")
        self.assertEqual(self.rows()["repo identities match tn.toml"]["status"], "ok")

    def test_forge_logins(self):
        self.fake("gh", script=GH_FAKE)
        row = self.rows()["forge CLIs logged in"]
        self.assertEqual((row["status"], row["detail"]), ("ok", "gh github.com"))
        self.assertIn(["auth", "status", "--hostname", "github.com"], self.calls("gh"))
        row = self.problem("not logged in", env={"FAKE_GH_AUTH": "1"})
        self.assertEqual((row["check"], row["status"], row["fix"]),
                         ("not logged in: gh github.com", "warn",
                          "gh auth login --hostname github.com"))
        self.fake("glab", exit=1)
        row = self.problem("not logged in")
        self.assertEqual(row["fix"], "glab auth login --hostname gitlab.example.com --web")

    def test_git_installed(self):
        self.assertEqual(self.rows()["git installed"]["status"], "ok")


class Completion(GitCase):
    def test_person_and_forge(self):
        r = self.ok(self.tn("__complete", "3", "--", "tn", "git", "as", "bo"))
        values = [line.split("\t")[0] for line in r.stdout.splitlines()]
        self.assertIn("bobsmith", values)
        r = self.ok(self.tn("__complete", "4", "--", "tn", "git", "remote", "add", ""))
        values = [line.split("\t")[0] for line in r.stdout.splitlines()]
        self.assertIn("work", values)


class ShippedConfig(GitCase):
    """bundles/git/git-forges.toml (public, copied) plus private.toml.example standing in for the
    private git-private.toml you write by hand (docs/private-overlay.md)."""

    def setUp(self):
        super().setUp()
        confd = self.config_dir / "conf.d"
        shutil.rmtree(confd)
        confd.mkdir()
        shutil.copy(BUNDLE / "git-forges.toml", confd / "git-forges.toml")
        shutil.copy(BUNDLE / "private.toml.example", confd / "git-private.toml")

    def test_public_forges_alone(self):
        os.unlink(self.config_dir / "conf.d" / "git-private.toml")
        cfg = Config.load()
        self.assertEqual({f.key: (f.host, f.cli, f.remote, f.owner) for f in cfg.forges()}, {
            "gh": ("github.com", "gh", "github", None),
            "gitlab": ("gitlab.com", "glab", "gitlab-com", None),
            "bitbucket": ("bitbucket.org", "none", "bitbucket", None)})
        self.assertEqual([p.key for p in cfg.people() if p.key != "me"], [])

    def test_parses_and_validates(self):
        cfg = Config.load()
        self.assertEqual({f.key: (f.host, f.cli, f.remote) for f in cfg.forges()}, {
            "gh": ("github.com", "gh", "github"),
            "gitlab": ("gitlab.com", "glab", "gitlab-com"),
            "work": ("gitlab.example.com", "glab", "gitlab"),
            "bitbucket": ("bitbucket.org", "none", "bitbucket")})
        self.assertEqual(cfg.forge("bitbucket").kind, "bitbucket")
        self.assertEqual(cfg.forge("gh").owner, "alex")
        remotes = [f.remote for f in cfg.forges()]
        self.assertEqual(len(remotes), len(set(remotes)))

    def test_example_people_are_example_data(self):
        with open(BUNDLE / "private.toml.example", "rb") as f:
            people = tomllib.load(f)["people"]
        self.assertGreaterEqual(len(people), 1)
        for key, p in people.items():
            self.assertRegex(key, r"^[a-z0-9_-]+$")
            self.assertRegex(p["email"], r"^[^@\s]+@example\.(com|org)$")
            self.assertTrue(p["name"].strip())

    def test_as_uses_the_private_people(self):
        r = self.repo()
        res = self.ok(self.tn("git", "as", "jane_roe", "--json", cwd=r))
        self.assertEqual(res.json["email"], "jane.roe@example.com")

    def test_no_secrets(self):
        for name in ("git-forges.toml", "private.toml.example"):
            text = (BUNDLE / name).read_text(encoding="utf-8").lower()
            for word in ("token", "password", "secret"):
                for line in text.splitlines():
                    if not line.lstrip().startswith("#"):
                        self.assertNotIn(word, line, name)
        self.assertTrue(os.path.isfile(BUNDLE / "plugin.py"))
