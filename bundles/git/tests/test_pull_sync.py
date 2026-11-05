"""tn git pull / sync (docs/tn.md §7.5)."""

from __future__ import annotations

from _gitbase import GitCase


class Pull(GitCase):
    def setUp(self):
        super().setUp()
        self.r = self.repo()
        self.bare_ = self.published(self.r)
        other = self.other_clone(self.bare_)
        self.new = self.commit(other, "upstream.txt")
        self.git(other, "push", "-q", "origin", "main")

    def test_default_pulls_the_upstream(self):
        r = self.ok(self.tn("git", "pull", "--json", cwd=self.r))
        self.assertEqual(r.json, [{"remote": "origin", "branch": "main", "ok": True}])
        self.assertEqual(self.head(self.r), self.new)

    def test_from_a_subdirectory(self):
        sub = self.r / "deep"
        sub.mkdir()
        self.ok(self.tn("git", "pull", cwd=sub))
        self.assertEqual(self.head(self.r), self.new)

    def test_remote(self):
        r = self.ok(self.tn("git", "pull", "--remote", "origin", "--json", cwd=self.r))
        self.assertEqual(r.json[0]["remote"], "origin")
        self.assertEqual(self.head(self.r), self.new)

    def test_unknown_remote_is_usage(self):
        r = self.tn("git", "pull", "--remote", "nope", "--json", cwd=self.r)
        self.assertExit(r, 2)
        self.assertEqual(r.error["choices"], ["origin"])

    def test_all_carries_on_past_a_failure(self):
        self.git(self.r, "remote", "add", "broken", str(self.tmp / "missing.git"))
        self.git(self.r, "remote", "add", "local", str(self.tmp / "ignored.git"))
        r = self.tn("git", "pull", "--all", "--json", cwd=self.r)
        self.assertExit(r, 1)
        self.assertEqual({(x["remote"], x["ok"]) for x in r.json},
                         {("origin", True), ("broken", False)})
        self.assertEqual(self.head(self.r), self.new)

    def test_no_upstream(self):
        self.git(self.r, "branch", "--unset-upstream")
        r = self.tn("git", "pull", cwd=self.r)
        self.assertExit(r, 1)
        self.assertIn("no upstream", r.stderr)
        self.assertIn("tn git pull --remote <name> (remotes: origin)", r.stderr)

    def test_detached_head(self):
        self.git(self.r, "checkout", "-q", "--detach")
        self.assertExit(self.tn("git", "pull", cwd=self.r), 1)

    def test_remote_and_all_exclude(self):
        self.assertExit(self.tn("git", "pull", "--all", "--remote", "origin", cwd=self.r), 2)

    def test_outside_a_repo(self):
        r = self.tn("git", "pull", "--json", cwd=self.home)
        self.assertExit(r, 2)
        self.assertEqual(r.error["message"], "not inside a git repository")

    def test_dry_run_changes_nothing(self):
        before = self.head(self.r)
        r = self.ok(self.tn("git", "pull", "--all", "-n", cwd=self.r))
        self.assertIn("would: run git -C", r.stderr)
        self.assertEqual(self.head(self.r), before)


class Sync(GitCase):
    def setUp(self):
        super().setUp()
        self.r = self.repo()
        self.bare_ = self.published(self.r)
        self.mine = self.commit(self.r, "mine.txt")

    def test_pulls_then_pushes_every_remote(self):
        second = self.published(self.r, "second", remote="backup", track=False)
        r = self.ok(self.tn("git", "sync", "--json", cwd=self.r))
        # in `git remote` order (by name)
        self.assertEqual(r.json, [
            {"remote": "backup", "branch": "main", "ok": True, "pushed": True},
            {"remote": "origin", "branch": "main", "ok": True, "pushed": True}])
        self.assertEqual(self.head(self.bare_, "main"), self.mine)
        self.assertEqual(self.head(second, "main"), self.mine)

    def test_one_remote(self):
        r = self.ok(self.tn("git", "sync", "--remote", "origin", "--json", cwd=self.r))
        self.assertEqual(len(r.json), 1)
        self.assertEqual(self.head(self.bare_, "main"), self.mine)

    def test_failed_pull_is_not_pushed(self):
        self.git(self.r, "remote", "add", "broken", str(self.tmp / "missing.git"))
        r = self.tn("git", "sync", "--json", cwd=self.r)
        self.assertExit(r, 1)
        rows = {x["remote"]: x for x in r.json}
        self.assertEqual((rows["broken"]["ok"], rows["broken"]["pushed"]), (False, False))
        self.assertTrue(rows["origin"]["pushed"])

    def test_no_remotes(self):
        r = self.repo("lonely")
        self.assertExit(self.tn("git", "sync", cwd=r), 1)

    def test_dry_run(self):
        r = self.ok(self.tn("git", "sync", "--dry-run", "--json", cwd=self.r))
        self.assertTrue(all(x["pushed"] for x in r.json))
        self.assertNotEqual(self.head(self.bare_, "main"), self.mine)
