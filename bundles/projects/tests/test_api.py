"""The Python API other plugins import: resolve, iterators, identity."""

from __future__ import annotations

from pathlib import Path

from tn.plugins import projects  # noqa: E402 - tn/plugins/__init__.py maps TN_PLUGIN_PATH

from _base import ProjectsCase

# A plugin that uses the API the way claude/git do, so resolve runs inside a real tn call.
USER_PLUGIN = '''
from tn import Plugin, arg, out
from tn.plugins import projects

plugin = Plugin("apiuser", help="uses the projects API", requires=["projects"])

@plugin.command(help="resolve a target")
@arg("target", nargs="?")
@arg("--ws")
@arg("--prefer-repo", action="store_true")
def where(ctx, args):
    w = projects.resolve(ctx, args.target, ws=args.ws, prefer_repo=args.prefer_repo)
    d = w.to_json()
    d["session"] = w.session("claude")
    d["label"] = w.label()
    d["session_name"] = projects.session_name(w, "codex")
    out.json(d)
'''


class Resolve(ProjectsCase):
    def setUp(self):
        super().setUp()
        self.write_plugin("apiuser", USER_PLUGIN)
        self.p = self.make_project("acme", repos=["shop-app", "shop-all"],
                                   workspaces=["src-02"])
        self.one = self.make_project("hooli", repos=["hooli-even"])

    def where(self, *argv, code=0, **kw):
        r = self.tn("apiuser", "where", *argv, **kw)
        self.assertExit(r, code)
        return r.json if code == 0 else r

    def test_context(self):
        j = self.where(cwd=self.p.repo("shop-app", "src-02") / ".git")
        self.assertEqual(j["path"], str(self.p.repo("shop-app", "src-02")))
        self.assertEqual(j["session"], "claude-acme-shop-app-02")
        self.assertEqual(j["label"], "Acme Shop App #T1-02")
        self.assertEqual(j["session_name"], "codex-acme-shop-app-02")
        self.assertEqual(j["git_root"], j["path"])

    def test_outside_the_roots(self):
        d = self.home / "scratch"
        d.mkdir()
        j = self.where(cwd=d)
        self.assertEqual((j["path"], j["session"], j["name"]), (str(d), "claude-scratch", None))

    def test_project_repo_and_ws_suffix(self):
        self.assertEqual(self.where("acme/shop-all")["path"], str(self.p.repo("shop-all")))
        j = self.where("acme/shop-app@02")
        self.assertEqual((j["path"], j["name"]), (str(self.p.repo("shop-app", "src-02")),
                                                  "acme/shop-app@02"))
        self.assertEqual(self.where("acme@02")["path"], str(self.p.ws("src-02")))
        self.assertEqual(self.where("acme")["path"], str(self.p.dir))

    def test_bare_words(self):
        self.assertEqual(self.where("shop-all")["path"], str(self.p.repo("shop-all")))

    def test_prefer_repo(self):
        j = self.where("hooli", "--prefer-repo")
        self.assertEqual(j["path"], str(self.one.repo("hooli-even")))
        self.assertEqual(j["session"], "claude-hooli-even-00")
        self.assertEqual(j["label"], "Hooli Even #T1-00")
        j = self.where("acme", "--prefer-repo")               # two repos: stays the project
        self.assertEqual(j["path"], str(self.p.dir))

    def test_ws_option(self):
        j = self.where("--ws", "02", cwd=self.p.repo("shop-app") / ".git")
        self.assertEqual(j["path"], str(self.p.repo("shop-app", "src-02")))
        r = self.where("acme/shop-app", "--ws", "05", code=2)
        self.assertIn("no workspace src-05 in acme: tn ws new 05", r.stderr)
        r = self.where("--ws", "02", code=2)
        self.assertIn("needs a project", r.stderr)

    def test_ws_new(self):
        j = self.where("acme/shop-app", "--ws", "new")
        self.assertEqual(j["workspace_created"], "src-01")
        self.assertEqual(j["path"], str(self.p.repo("shop-app", "src-01")))
        self.assertTrue(Path(j["path"], ".git").exists())

    def test_directories(self):
        j = self.where(str(self.p.repo("shop-all")))
        self.assertEqual(j["name"], "acme/shop-all")
        j = self.where("./src/shop-app", cwd=self.p.dir)
        self.assertEqual(j["path"], str(self.p.repo("shop-app")))
        r = self.where("./nope", code=2)
        self.assertIn("no such directory", r.stderr)

    def test_several_matches(self):
        self.make_project("other", repos=["shop-all"])
        r = self.where("shop-all", "--json", code=2)
        self.assertEqual(sorted(r.error["choices"]), ["acme/shop-all", "other/shop-all"])
        j = self.where("shop-all", tty=True, stdin="2\n")
        self.assertEqual(j["path"], str(self.projects / "other" / "src" / "shop-all"))
        # Inside a project, its own repo wins.
        j = self.where("shop-all", cwd=self.p.dir)
        self.assertEqual(j["path"], str(self.p.repo("shop-all")))

    def test_ws_suffix_cannot_leave_the_project(self):
        r = self.where("acme@02/../../hooli/src", code=2)
        self.assertIn("invalid workspace", r.stderr)

    def test_no_match(self):
        r = self.where("nothing-here", code=2)
        self.assertIn('matches "nothing-here"', r.stderr)


class Helpers(ProjectsCase):
    def test_iterators_and_default_branch(self):
        p = self.make_project("acme", repos=["b", "a"], workspaces=["src-02", "src-01"])
        (p.ws("src") / "notes").mkdir()
        self.assertEqual(projects.workspaces(p.dir), ["src", "src-01", "src-02"])
        self.assertEqual([r.name for r in projects.iter_repos(p.dir)], ["a", "b"])
        self.assertEqual(len(list(projects.iter_repos(p.dir, "all"))), 6)
        self.assertEqual({r.ws_id for r in projects.iter_repos(p.dir, "02")}, {"02"})
        self.assertEqual(projects.default_branch(p.repo("a")), "main")
        self.git(p.repo("a"), "branch", "-m", "main", "trunk")
        self.assertEqual(projects.default_branch(p.repo("a")), "trunk")
        self.assertEqual(projects.ws_dir_name("01"), "src-01")
        self.assertEqual(projects.ws_dir_name("src-01"), "src-01")
        self.assertEqual(projects.ws_dir_name("00"), "src")
        self.assertEqual(projects.ws_dir_name("review"), "src-review")

    def test_read_remotes_and_identity(self):
        repo = self.make_repo(self.tmp / "r", {"origin": "git@a.example:x/y.git",
                                               "gitlab": "https://b.example/z.git"})
        self.git(repo, "config", "user.email", "me@example.com")
        self.assertEqual(projects.read_remotes(repo), [("origin", "git@a.example:x/y.git"),
                                                       ("gitlab", "https://b.example/z.git")])
        self.assertEqual(projects.read_identity(repo), (None, "me@example.com"))
        self.assertEqual(projects.read_remotes(self.tmp), [])

    def test_ws_blockers(self):
        repo = self.make_repo(self.tmp / "r")
        self.assertEqual(projects.ws_blockers(repo), ["no remote"])
        self.published(repo)
        self.assertEqual(projects.ws_blockers(repo), [])
        (repo / "u.txt").write_text("u")
        self.assertEqual(projects.ws_blockers(repo), ["1 uncommitted or untracked change"])
