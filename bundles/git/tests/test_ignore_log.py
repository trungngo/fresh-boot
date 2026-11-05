"""tn git ignore / log / changed / authors (docs/tn.md §7.5)."""

from __future__ import annotations

from tn.plugins import git as gitplugin  # noqa: E402

from _gitbase import GH_FAKE, TEST_EMAIL, TEST_NAME, GitCase


class Ignore(GitCase):
    def setUp(self):
        super().setUp()
        self.r = self.repo()
        self.fake("gh", script=GH_FAKE)

    def test_appends_templates(self):
        r = self.ok(self.tn("git", "ignore", "python", "NODE", "--json", cwd=self.r))
        self.assertEqual(r.json, {"file": str(self.r / ".gitignore"), "added": ["Python", "Node"],
                                  "skipped": []})
        self.assertEqual((self.r / ".gitignore").read_text(),
                         "### Python (github/gitignore)\n__pycache__/\n*.py[cod]\n"
                         "\n### Node (github/gitignore)\nnode_modules/\n")
        self.assertIn(["api", "gitignore/templates/Python"], self.calls("gh"))

    def test_skips_what_is_there_and_keeps_existing_text(self):
        (self.r / ".gitignore").write_text("*.log", encoding="utf-8")
        self.ok(self.tn("git", "ignore", "py", cwd=self.r))
        r = self.ok(self.tn("git", "ignore", "python", "golang", "--json", cwd=self.r))
        self.assertEqual((r.json["added"], r.json["skipped"]), (["Go"], ["Python"]))
        text = (self.r / ".gitignore").read_text()
        self.assertTrue(text.startswith("*.log\n\n### Python (github/gitignore)\n"))
        self.assertEqual(text.count("### Python"), 1)

    def test_unknown_template(self):
        r = self.tn("git", "ignore", "pythn", "--json", cwd=self.r)
        self.assertExit(r, 2)
        self.assertIn("Python", r.error["choices"])
        self.assertFalse((self.r / ".gitignore").exists())

    def test_list(self):
        r = self.ok(self.tn("git", "ignore", "--list", "--json", cwd=self.home))
        self.assertEqual(r.json, ["C++", "Go", "Node", "Python"])
        r = self.ok(self.tn("git", "ignore", "--list", cwd=self.home))
        self.assertEqual(r.stdout.split(), ["C++", "Go", "Node", "Python"])

    def test_no_templates_and_no_repo(self):
        self.assertExit(self.tn("git", "ignore", cwd=self.r), 2)
        self.assertExit(self.tn("git", "ignore", "python", cwd=self.home), 2)

    def test_gh_missing(self):
        self.unfake("gh")
        r = self.tn("git", "ignore", "python", "--json", cwd=self.r)
        self.assertExit(r, 3)
        self.assertEqual(r.error["fix"], "dot apply gh")

    def test_gh_not_logged_in(self):
        r = self.tn("git", "ignore", "python", "--json", cwd=self.r, env={"FAKE_GH_401": "1"})
        self.assertExit(r, 3)
        self.assertEqual(r.error["fix"], "gh auth login")

    def test_dry_run(self):
        r = self.ok(self.tn("git", "ignore", "python", "-n", cwd=self.r))
        self.assertIn("would: append to", r.stderr)
        self.assertFalse((self.r / ".gitignore").exists())


class Log(GitCase):
    def setUp(self):
        super().setUp()
        self.r = self.repo()
        self.freeze_time(2_000_000_000)
        for i in range(3):
            self.commit(self.r, "f%d.txt" % i, msg="commit %d" % i)

    def test_json(self):
        r = self.ok(self.tn("git", "log", "--json", cwd=self.r))
        self.assertEqual([x["subject"] for x in r.json],
                         ["commit 2", "commit 1", "commit 0", "initial"])
        row = r.json[0]
        self.assertEqual(row["hash"], self.head(self.r))
        self.assertEqual(row["short"], row["hash"][:len(row["short"])])
        self.assertEqual((row["author_name"], row["author_email"]), (TEST_NAME, TEST_EMAIL))
        self.assertIn("HEAD -> main", row["refs"])
        self.assertTrue(row["date"].endswith("Z"))
        self.assertIsInstance(row["age_seconds"], int)

    def test_max_count_range_and_author(self):
        r = self.ok(self.tn("git", "log", "--max-count", "2", "--json", cwd=self.r))
        self.assertEqual(len(r.json), 2)
        r = self.ok(self.tn("git", "log", "HEAD~1..HEAD", "--limit", "5", "--json", cwd=self.r))
        self.assertEqual([x["subject"] for x in r.json], ["commit 2"])
        r = self.ok(self.tn("git", "log", "--author", "nobody", "--json", cwd=self.r))
        self.assertEqual(r.json, [])

    def test_dash_n_is_dry_run_not_a_count(self):
        r = self.ok(self.tn("git", "log", "-n", "--json", cwd=self.r))
        self.assertEqual(len(r.json), 4)

    def test_text_and_bad_range(self):
        r = self.ok(self.tn("git", "log", cwd=self.r))
        self.assertTrue(r.stdout.startswith("COMMIT"))
        self.assertExit(self.tn("git", "log", "nope..HEAD", cwd=self.r), 2)

    def test_no_commits(self):
        d = self.home / "empty"
        d.mkdir()
        self.git(d, "init", "-q")
        r = self.ok(self.tn("git", "log", "--json", cwd=d))
        self.assertEqual(r.json, [])


class Changed(GitCase):
    def test_rows(self):
        r = self.repo()
        self.commit(r, "gone.txt")
        self.commit(r, "old.txt", text="rename me\n" * 5)
        (r / "README.md").write_text("changed\n", encoding="utf-8")
        (r / "new.txt").write_text("n\n", encoding="utf-8")
        self.git(r, "add", "new.txt")
        (r / "new.txt").write_text("n2\n", encoding="utf-8")
        (r / "gone.txt").unlink()
        self.git(r, "mv", "old.txt", "moved.txt")
        (r / "untracked file.txt").write_text("u\n", encoding="utf-8")
        res = self.ok(self.tn("git", "changed", "--json", cwd=r))
        rows = {x["path"]: x for x in res.json}
        self.assertEqual(rows["README.md"], {"path": "README.md", "status": "modified",
                                             "staged": False, "unstaged": True,
                                             "orig_path": None})
        self.assertEqual((rows["new.txt"]["status"], rows["new.txt"]["staged"],
                          rows["new.txt"]["unstaged"]), ("added", True, True))
        self.assertEqual(rows["gone.txt"]["status"], "deleted")
        self.assertEqual((rows["moved.txt"]["status"], rows["moved.txt"]["orig_path"]),
                         ("renamed", "old.txt"))
        self.assertEqual(rows["untracked file.txt"]["status"], "untracked")
        text = self.ok(self.tn("git", "changed", cwd=r))
        self.assertIn("old.txt -> moved.txt", text.stdout)

    def test_conflicted(self):
        rows = gitplugin.parse_status_z(
            "u UU N... 100644 100644 100644 100644 a b c both.txt\0")
        self.assertEqual(rows[0]["status"], "conflicted")

    def test_clean(self):
        r = self.ok(self.tn("git", "changed", cwd=self.repo()))
        self.assertEqual(r.stdout, "")
        self.assertIn("Nothing changed.", r.stderr)


class Authors(GitCase):
    def test_counts_and_people(self):
        r = self.repo()
        self.git(r, "-c", "user.name=Bob Smith", "-c", "user.email=BOBSMITH@example.com",
                 "commit", "-q", "--allow-empty", "-m", "x")
        res = self.ok(self.tn("git", "authors", "--json", cwd=r))
        self.assertEqual(res.json, [
            {"name": "Bob Smith", "email": "BOBSMITH@example.com", "commits": 1,
             "person": "bobsmith"},
            {"name": TEST_NAME, "email": TEST_EMAIL, "commits": 1, "person": "me"}])
        text = self.ok(self.tn("git", "authors", cwd=r))
        self.assertTrue(text.stdout.startswith("COMMITS"))

    def test_no_commits(self):
        d = self.home / "empty"
        d.mkdir()
        self.git(d, "init", "-q")
        self.assertEqual(self.ok(self.tn("git", "authors", "--json", cwd=d)).json, [])
