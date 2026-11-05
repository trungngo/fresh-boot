"""tn ws new|ls|rm (parallel workspaces)."""

from __future__ import annotations

import os

from _base import ProjectsCase

SESSIONS_PLUGIN = '''
from tn import Plugin, Session
plugin = Plugin("fakesess", help="sessions for tests")

@plugin.sessions
def _s(ctx):
    return [Session(kind="claude", id="claude-acme-shop-app-01", name="x", dir=%r)]
'''


class WsNew(ProjectsCase):
    def setUp(self):
        super().setUp()
        self.p = self.make_project("acme", repos=["shop-app", "local-only"])
        self.src = self.p.repo("shop-app")
        self.published(self.src)
        # Local work the copy must not carry: a side branch, an unpushed commit on main,
        # an uncommitted file and an ignored one.
        self.git(self.src, "branch", "side")
        self.commit(self.src, "unpushed.txt")
        (self.src / "dirty.txt").write_text("d")
        (self.p.ws("src") / "notes").mkdir()                  # not a git repo: skipped
        self.git(self.p.repo("local-only"), "branch", "extra")

    def test_happy_path(self):
        before = self.git(self.src, "for-each-ref")
        r = self.ok(self.tn("ws", "new", "--json", cwd=self.src))
        ws = self.p.ws("src-01")
        self.assertEqual(r.json["workspace"], "src-01")
        self.assertEqual(r.json["ws_id"], "01")
        self.assertEqual(r.json["path"], str(ws))
        repos = {x["repo"]: x for x in r.json["repos"]}
        self.assertEqual(repos["notes"]["state"], "skipped")
        self.assertEqual(repos["notes"]["reason"], "not a git repository")
        a = repos["shop-app"]
        self.assertEqual((a["state"], a["branch"], a["primary_remote"], a["unpushed"]),
                         ("copied", "main", "origin", 1))
        copy = ws / "shop-app"
        self.assertFalse((copy / "unpushed.txt").exists())
        self.assertFalse((copy / "dirty.txt").exists())
        self.assertEqual(self.git(copy, "for-each-ref", "--format=%(refname:short)",
                                  "refs/heads").split(), ["main"])
        self.assertEqual(self.local_config(copy, "remote.origin.url"),
                         self.local_config(self.src, "remote.origin.url"))
        self.assertEqual(self.git(copy, "rev-parse", "--abbrev-ref", "@{u}").strip(),
                         "origin/main")
        b = repos["local-only"]
        self.assertEqual((b["state"], b["primary_remote"]), ("copied", None))
        self.assertEqual(self.git(ws / "local-only", "remote").strip(), "")
        self.assertEqual(self.git(ws / "local-only", "for-each-ref", "refs/heads",
                                  "--format=%(refname:short)").split(), ["main"])
        # The source is untouched.
        self.assertEqual(self.git(self.src, "for-each-ref"), before)
        self.assertTrue((self.src / "dirty.txt").exists())

    def test_text_output(self):
        r = self.ok(self.tn("ws", "new", cwd=self.p.dir))
        self.assertEqual(r.stdout.strip(), str(self.p.ws("src-01")))
        self.assertIn("note: src/shop-app is 1 unpushed commit(s) ahead - not copied", r.stderr)
        self.assertIn("Created ", r.stderr)
        self.assertIn("2 copied, 1 skipped, 0 failed", r.stderr)
        self.assertIn("untrusted", r.stderr)

    def test_ids(self):
        self.ok(self.tn("ws", "new", cwd=self.p.dir))
        r = self.ok(self.tn("ws", "new", "--json", cwd=self.p.dir))
        self.assertEqual(r.json["workspace"], "src-02")
        r = self.ok(self.tn("ws", "new", "src-05", "--json", cwd=self.p.dir))
        self.assertEqual(r.json["workspace"], "src-05")
        r = self.ok(self.tn("ws", "new", "review", "--json", cwd=self.p.dir))
        self.assertEqual((r.json["workspace"], r.json["ws_id"]), ("src-review", "review"))
        self.assertExit(self.tn("ws", "new", "02", cwd=self.p.dir), 1)
        self.assertExit(self.tn("ws", "new", "00", cwd=self.p.dir), 2)

    def test_default_branch_from_origin_head(self):
        self.git(self.src, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.git(self.src, "checkout", "-q", "side")
        r = self.ok(self.tn("ws", "new", "--json", cwd=self.p.dir))
        a = [x for x in r.json["repos"] if x["repo"] == "shop-app"][0]
        self.assertEqual(a["branch"], "main")
        self.assertEqual(self.git(self.p.repo("shop-app", "src-01"), "branch",
                                  "--show-current").strip(), "main")

    def test_submodule_note(self):
        (self.p.repo("local-only") / ".gitmodules").write_text("")
        self.git(self.p.repo("local-only"), "add", ".gitmodules")
        self.git(self.p.repo("local-only"), "commit", "-q", "-m", "mods")
        r = self.ok(self.tn("ws", "new", "--json", cwd=self.p.dir))
        b = [x for x in r.json["repos"] if x["repo"] == "local-only"][0]
        self.assertTrue(b["submodules"])

    def test_empty_repo_is_skipped(self):
        self.git(self.p.ws("src"), "init", "-q", "empty")
        r = self.ok(self.tn("ws", "new", "--json", cwd=self.p.dir))
        e = [x for x in r.json["repos"] if x["repo"] == "empty"][0]
        self.assertEqual((e["state"], e["reason"]), ("skipped", "no branch to check out"))

    def test_no_src(self):
        self.make_project("bare", dirs=("bin",))
        (self.projects / "bare" / "src").rmdir()       # make_project always makes src/
        r = self.tn("ws", "new", cwd=self.projects / "bare")
        self.assertExit(r, 1)
        self.assertIn("nothing to copy", r.stderr)

    def test_outside(self):
        self.assertExit(self.tn("ws", "new"), 2)

    def test_dry_run(self):
        r = self.ok(self.tn("ws", "new", "-n", "--json", cwd=self.p.dir))
        self.assertTrue(r.json["dry_run"])
        self.assertIn("would: run git clone --quiet", r.stderr)
        self.assertFalse(self.p.ws("src-01").exists())

    def test_cd(self):
        r = self.ok(self.tn("ws", "new", "--cd", cwd=self.p.dir))
        self.assertEqual(r.cd, str(self.p.ws("src-01")))


class WsLsRm(ProjectsCase):
    def setUp(self):
        super().setUp()
        self.p = self.make_project("acme", repos=["shop-app"])
        self.published(self.p.repo("shop-app"))
        self.ok(self.tn("ws", "new", cwd=self.p.dir))
        self.copy = self.p.repo("shop-app", "src-01")

    def test_ls(self):
        (self.copy / "x.txt").write_text("x")
        r = self.ok(self.tn("ws", "ls", "--json", cwd=self.p.dir))
        rows = {x["ws"]: x for x in r.json}
        self.assertEqual(sorted(rows), ["src", "src-01"])
        self.assertEqual(rows["src-01"]["ws_id"], "01")
        self.assertEqual(rows["src-01"]["repos"], ["shop-app"])
        self.assertEqual(rows["src-01"]["dirty_repos"], 1)
        self.assertEqual(rows["src-01"]["unpushed_repos"], 1)
        self.assertEqual(rows["src"]["dirty_repos"], 0)
        self.assertEqual(rows["src"]["sessions"], [])
        self.assertIsInstance(rows["src"]["age_seconds"], int)
        r = self.ok(self.tn("ws", "ls", "acme"))
        self.assertTrue(r.stdout.startswith("WS"))

    def test_ls_sessions(self):
        self.write_plugin("fakesess", SESSIONS_PLUGIN % str(self.copy))
        r = self.ok(self.tn("ws", "ls", "--json", cwd=self.p.dir))
        rows = {x["ws"]: x for x in r.json}
        self.assertEqual(rows["src-01"]["sessions"], ["claude-acme-shop-app-01"])

    def test_rm(self):
        r = self.ok(self.tn("ws", "rm", "01", "--yes", "--json", cwd=self.copy))
        self.assertEqual(r.json, {"project": "acme", "workspace": "src-01",
                                  "path": str(self.p.ws("src-01")), "removed": True,
                                  "repos": ["shop-app"]})
        self.assertFalse(self.p.ws("src-01").exists())
        self.assertEqual(r.cd, str(self.p.dir))

    def test_rm_confirms(self):
        r = self.tn("ws", "rm", "src-01", cwd=self.p.dir)
        self.assertExit(r, 2)
        self.assertIn("pass --yes", r.stderr)
        self.assertTrue(self.p.ws("src-01").exists())
        r = self.tn("ws", "rm", "01", cwd=self.p.dir, tty=True, stdin="n\n")
        self.assertExit(r, 1)
        self.assertTrue(self.p.ws("src-01").exists())
        self.ok(self.tn("ws", "rm", "01", cwd=self.p.dir, tty=True, stdin="y\n"))
        self.assertFalse(self.p.ws("src-01").exists())

    def test_refuses_uncommitted_stash_and_unpushed(self):
        (self.copy / "new.txt").write_text("n")
        r = self.tn("ws", "rm", "01", "--yes", "--json", cwd=self.p.dir)
        self.assertExit(r, 1)
        self.assertIn("uncommitted", r.error["hint"])
        self.git(self.copy, "stash", "-u", "-q")
        r = self.tn("ws", "rm", "01", "--yes", cwd=self.p.dir)
        self.assertExit(r, 1)
        self.assertIn("stash", r.stderr)
        self.git(self.copy, "stash", "drop", "-q")
        self.commit(self.copy, "local.txt")
        r = self.tn("ws", "rm", "01", "--yes", cwd=self.p.dir)
        self.assertExit(r, 1)
        self.assertIn("1 commit on no remote", r.stderr)
        self.git(self.copy, "push", "-q", "origin", "main")
        self.git(self.copy, "switch", "-q", "-c", "topic")
        self.commit(self.copy, "topic.txt")
        r = self.tn("ws", "rm", "01", "--yes", cwd=self.p.dir)
        self.assertExit(r, 1)
        self.assertTrue(self.p.ws("src-01").exists())
        self.git(self.copy, "push", "-q", "origin", "topic")
        self.ok(self.tn("ws", "rm", "01", "--yes", cwd=self.p.dir))

    def test_refuses_a_repo_without_remote_and_stray_files(self):
        self.make_repo(self.p.repo("mine", "src-01"))
        r = self.tn("ws", "rm", "01", "--yes", cwd=self.p.dir)
        self.assertExit(r, 1)
        self.assertIn("mine: no remote", r.stderr)
        import shutil
        shutil.rmtree(self.p.repo("mine", "src-01"))
        (self.p.ws("src-01") / "notes.txt").write_text("keep me")
        r = self.tn("ws", "rm", "01", "--yes", cwd=self.p.dir)
        self.assertExit(r, 1)
        self.assertIn("notes.txt: not a git repository", r.stderr)

    def test_copy_of_a_repo_without_remotes(self):
        # Regression: a copy of a `tn repo new` repo (no remotes) could never be removed.
        d = self.make_project("demo", repos=["app"])
        self.ok(self.tn("ws", "new", cwd=d.dir))
        copy = d.repo("app", "src-01")
        self.commit(copy, "mine.txt")
        r = self.tn("ws", "rm", "01", "--yes", "--json", cwd=d.dir)
        self.assertExit(r, 1)
        self.assertIn("app: 1 commit on no remote and not in src/app", r.error["hint"])
        self.git(copy, "reset", "-q", "--hard", "HEAD~1")    # back to what src/app has
        self.ok(self.tn("ws", "rm", "01", "--yes", cwd=d.dir))
        self.assertFalse(d.ws("src-01").exists())
        self.assertTrue(d.repo("app").exists())

    def test_refuses_commits_on_a_detached_head_and_local_tags(self):
        # Regression: rev-list --branches missed commits reachable only from HEAD or a tag.
        self.git(self.copy, "checkout", "-q", "--detach")
        self.commit(self.copy, "a.txt")
        self.commit(self.copy, "b.txt")
        r = self.tn("ws", "rm", "01", "--yes", "--json", cwd=self.p.dir)
        self.assertExit(r, 1)
        self.assertIn("2 commits on no remote", r.error["hint"])
        self.git(self.copy, "tag", "keep")
        self.git(self.copy, "checkout", "-q", "main")
        r = self.tn("ws", "rm", "01", "--yes", "--json", cwd=self.p.dir)
        self.assertExit(r, 1)
        self.assertIn("2 commits on no remote", r.error["hint"])
        self.git(self.copy, "tag", "-d", "keep")
        self.ok(self.tn("ws", "rm", "01", "--yes", cwd=self.p.dir))

    def test_refuses_an_operation_in_progress(self):
        gd = self.copy / ".git"
        for marker in ("rebase-merge", "MERGE_HEAD"):
            p = gd / marker
            p.mkdir() if marker == "rebase-merge" else p.write_text("0" * 40 + "\n")
            r = self.tn("ws", "rm", "01", "--yes", "--json", cwd=self.p.dir)
            self.assertExit(r, 1)
            self.assertIn("in progress", r.error["hint"])
            p.rmdir() if marker == "rebase-merge" else p.unlink()

    def test_hidden_entries_are_checked(self):
        # Regression: dot-entries were skipped by the check but deleted by the rmtree.
        ws = self.p.ws("src-01")
        (ws / ".DS_Store").write_text("")                    # harmless: never blocks
        (ws / ".notes").mkdir()
        (ws / ".notes" / "todo.md").write_text("keep")
        r = self.tn("ws", "rm", "01", "--yes", "--json", cwd=self.p.dir)
        self.assertExit(r, 1)
        self.assertIn(".notes: not a git repository", r.error["hint"])
        import shutil
        shutil.rmtree(ws / ".notes")
        self.make_repo(ws / ".tools")
        r = self.tn("ws", "rm", "01", "--yes", "--json", cwd=self.p.dir)
        self.assertExit(r, 1)
        self.assertIn(".tools: no remote", r.error["hint"])
        self.assertTrue((ws / ".tools").exists())
        shutil.rmtree(ws / ".tools")
        self.ok(self.tn("ws", "rm", "01", "--yes", cwd=self.p.dir))

    def test_id_cannot_escape_the_workspace_namespace(self):
        # Regression: '01/../../acme/src' reached the original src/ and deleted it.
        for bad in ("01/../../acme/src", "../src", "01/..", "src-01/../src"):
            r = self.tn("ws", "rm", bad, "--yes", cwd=self.p.dir)
            self.assertExit(r, 2)
        self.assertTrue(self.p.repo("shop-app").exists())
        self.assertTrue(self.p.ws("src-01").exists())

    def test_refuses_a_running_session(self):
        self.write_plugin("fakesess", SESSIONS_PLUGIN % str(self.copy))
        r = self.tn("ws", "rm", "01", "--yes", cwd=self.p.dir)
        self.assertExit(r, 1)
        self.assertIn("tn claude stop claude-acme-shop-app-01", r.stderr)

    def test_refuses_src_and_unknown(self):
        self.assertExit(self.tn("ws", "rm", "00", "--yes", cwd=self.p.dir), 2)
        self.assertExit(self.tn("ws", "rm", "src", "--yes", cwd=self.p.dir), 2)
        r = self.tn("ws", "rm", "07", "--yes", "--json", cwd=self.p.dir)
        self.assertExit(r, 2)
        self.assertEqual(r.error["choices"], ["src-01"])
        self.assertExit(self.tn("ws", "rm", "01", "--yes"), 2)

    def test_dry_run(self):
        r = self.ok(self.tn("ws", "rm", "01", "-n", "--yes", "--json", cwd=self.p.dir))
        self.assertTrue(r.json["dry_run"])
        self.assertFalse(r.json["removed"])
        self.assertIn("would: remove", r.stderr)
        self.assertTrue(self.p.ws("src-01").exists())

    def test_rm_outside_cwd_does_not_cd(self):
        r = self.ok(self.tn("ws", "rm", "01", "--yes", cwd=self.p.dir))
        self.assertIsNone(r.cd)
        self.assertTrue(os.path.isdir(self.p.dir))
