"""tn git export / feature new / feature ls (docs/tn.md §7.5)."""

from __future__ import annotations

import time
import zipfile

from _gitbase import GitCase


class Export(GitCase):
    def setUp(self):
        super().setUp()
        self.p = self.make_project("acme", repos=["shop-web"], workspaces=["src-02"])
        self.r = self.p.repo("shop-web")
        self.ts = time.mktime((2026, 9, 30, 12, 0, 0, 0, 0, -1))
        self.freeze_time(self.ts)

    def test_default_file_in_rel(self):
        res = self.ok(self.tn("git", "export", "--json", cwd=self.r / "."))
        f = self.p.dir / "rel" / "acme-shop-web-20260930.zip"
        self.assertEqual(res.json, {"file": str(f), "ref": "HEAD", "commit": self.head(self.r),
                                    "bytes": f.stat().st_size})
        with zipfile.ZipFile(f) as z:
            self.assertEqual(z.namelist(), ["README.md"])

    def test_text_prints_the_path_and_workspace_repo(self):
        r2 = self.p.repo("shop-web", "src-02")
        res = self.ok(self.tn("git", "export", cwd=r2))
        self.assertEqual(res.stdout.strip(),
                         str(self.p.dir / "rel" / "acme-shop-web-20260930.zip"))

    def test_needs_a_repo(self):
        self.assertExit(self.tn("git", "export", "-o", "x.zip", cwd=self.home), 2)

    def test_absolute_output_with_dash_c(self):
        out = self.tmp / "exports" / "x.zip"
        res = self.ok(self.tn("-C", str(self.r), "git", "export", "-o", str(out), "--json"))
        self.assertEqual(res.json["file"], str(out))
        self.assertTrue(out.is_file())

    def test_ref_and_relative_output(self):
        first = self.head(self.r)
        self.commit(self.r, "later.txt")
        sub = self.r / "sub"
        sub.mkdir()
        res = self.ok(self.tn("git", "export", first, "-o", "x.zip", "--json", cwd=sub))
        self.assertEqual((res.json["file"], res.json["commit"]), (str(sub / "x.zip"), first))
        with zipfile.ZipFile(sub / "x.zip") as z:
            self.assertNotIn("later.txt", z.namelist())

    def test_outside_a_project_needs_output(self):
        d = self.make_repo(self.home / "loose")
        r = self.tn("git", "export", "--json", cwd=d)
        self.assertExit(r, 2)
        self.assertIn("-o", r.error["message"])

    def test_unknown_ref(self):
        self.assertExit(self.tn("git", "export", "nope", cwd=self.r), 2)

    def test_overwrite_confirms(self):
        self.ok(self.tn("git", "export", cwd=self.r))
        r = self.tn("git", "export", "--json", cwd=self.r)
        self.assertExit(r, 2)
        self.assertIn("pass --yes", r.error["message"])
        self.ok(self.tn("git", "export", "--yes", cwd=self.r))
        self.assertExit(self.tn("git", "export", cwd=self.r, tty=True, stdin="n\n"), 1)

    def test_dry_run(self):
        res = self.ok(self.tn("git", "export", "-n", "--json", cwd=self.r))
        self.assertIsNone(res.json["bytes"])
        self.assertFalse((self.p.dir / "rel").exists())


class Feature(GitCase):
    def setUp(self):
        super().setUp()
        self.r = self.repo()

    def branch(self):
        return self.git(self.r, "branch", "--show-current").strip()

    def test_from_default_branch(self):
        res = self.ok(self.tn("git", "feature", "new", "login", "--json", cwd=self.r))
        self.assertEqual(res.json, {"branch": "feature/login", "base": "main"})
        self.assertEqual(self.branch(), "feature/login")

    def test_prefers_develop_local_then_remote(self):
        self.git(self.r, "branch", "develop")
        res = self.ok(self.tn("git", "feature", "new", "a", "--json", cwd=self.r))
        self.assertEqual(res.json["base"], "develop")
        self.git(self.r, "checkout", "-q", "main")
        bare = self.published(self.r)
        self.git(self.r, "push", "-q", "origin", "develop")
        self.git(self.r, "branch", "-D", "develop")
        res = self.ok(self.tn("git", "feature", "new", "b", "--json", cwd=self.r))
        self.assertEqual(res.json["base"], "origin/develop")
        self.assertTrue(bare.exists())
        # --no-track: the feature branch does not track origin/develop
        self.assertEqual(self.git(self.r, "config", "--get-regexp", "^branch\\.").count(
            "feature/b"), 0)

    def test_from_and_errors(self):
        self.git(self.r, "branch", "release")
        res = self.ok(self.tn("git", "feature", "new", "feature/x", "--from", "release", "--json",
                              cwd=self.r))
        self.assertEqual(res.json, {"branch": "feature/x", "base": "release"})
        self.assertExit(self.tn("git", "feature", "new", "x", cwd=self.r), 1)
        self.assertExit(self.tn("git", "feature", "new", "y", "--from", "nope", cwd=self.r), 2)
        self.assertExit(self.tn("git", "feature", "new", "bad..name", cwd=self.r), 2)
        self.assertExit(self.tn("git", "feature", cwd=self.r), 2)

    def test_detached(self):
        self.git(self.r, "checkout", "-q", "--detach")
        self.assertExit(self.tn("git", "feature", "new", "x", cwd=self.r), 1)

    def test_dry_run(self):
        r = self.ok(self.tn("git", "feature", "new", "x", "-n", cwd=self.r))
        self.assertIn("would: run git -C", r.stderr)
        self.assertEqual(self.branch(), "main")

    def test_ls(self):
        self.published(self.r)
        self.ok(self.tn("git", "feature", "new", "one", cwd=self.r))
        self.commit(self.r, "one.txt")
        self.git(self.r, "push", "-q", "origin", "feature/one")
        self.git(self.r, "checkout", "-q", "main")
        self.ok(self.tn("git", "feature", "new", "two", cwd=self.r))
        self.git(self.r, "push", "-q", "origin", "feature/two:feature/three")
        self.git(self.r, "checkout", "-q", "main")
        self.commit(self.r, "main.txt")
        res = self.ok(self.tn("git", "feature", "ls", "--json", cwd=self.r))
        rows = {x["name"]: x for x in res.json}
        self.assertEqual(sorted(rows), ["one", "three", "two"])
        self.assertEqual((rows["one"]["local"], rows["one"]["remote"], rows["one"]["ahead"],
                          rows["one"]["behind"]), (True, "origin", 1, 1))
        self.assertEqual((rows["two"]["local"], rows["two"]["remote"]), (True, None))
        self.assertEqual((rows["three"]["local"], rows["three"]["remote"],
                          rows["three"]["branch"]), (False, "origin", "feature/three"))
        self.assertTrue(rows["one"]["last_commit_date"].endswith("Z"))
        text = self.ok(self.tn("git", "feature", "ls", cwd=self.r))
        self.assertTrue(text.stdout.startswith("BRANCH"))

    def test_ls_empty(self):
        r = self.ok(self.tn("git", "feature", "ls", cwd=self.r))
        self.assertIn("No feature branches", r.stderr)
