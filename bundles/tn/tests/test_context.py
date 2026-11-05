import os
from pathlib import Path

from tn.config import Config
from tn.context import Context, locate, pascal, slugify, ws_id_of
from tn.errors import Missing, UsageError
from tn.options import Options
from tn.testing import TnTestCase


class Names(TnTestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Acme", "shop-app", "02"), "acme-shop-app-02")
        self.assertEqual(slugify("a.b:c#d", "", None, "x"), "a-b-c-d-x")
        self.assertEqual(slugify("--Ab__C--"), "ab-c")
        self.assertEqual(slugify("x", 3000), "x-3000")

    def test_pascal(self):
        self.assertEqual(pascal("shop-app"), "Shop App")
        self.assertEqual(pascal("blue_widget  x"), "Blue Widget X")
        self.assertEqual(pascal("iPhone-app"), "IPhone App")

    def test_ws_id(self):
        self.assertEqual(ws_id_of("src"), "00")
        self.assertEqual(ws_id_of("src-02"), "02")
        self.assertEqual(ws_id_of("src-review"), "review")
        self.assertEqual(ws_id_of("other"), "other")
        self.assertIsNone(ws_id_of(None))


class Build(TnTestCase):
    def ctx(self, path, **kw):
        cfg = Config.load()
        return Context.build(Path(path), Options(**kw), cfg)

    def test_repo_in_workspace(self):
        root = self.root_dir()
        c = self.ctx(root / "acme" / "src-02" / "shop-app" / "app" / "models")
        self.assertEqual(c.kind, "projects")
        self.assertEqual(c.root_key, "projects")
        self.assertEqual(c.root, root)
        self.assertEqual((c.project, c.ws, c.ws_id, c.repo), ("acme", "src-02", "02", "shop-app"))
        self.assertEqual(c.path, root / "acme" / "src-02" / "shop-app")
        self.assertEqual(c.project_dir, root / "acme")
        self.assertEqual(c.ws_dir, root / "acme" / "src-02")
        self.assertEqual(c.name, "acme/shop-app@02")
        self.assertEqual(c.slug, "acme-shop-app-02")
        self.assertEqual(c.session("claude"), "claude-acme-shop-app-02")
        self.assertEqual(c.tunnel_label(3000), "acme-shop-app-02-3000")
        self.assertEqual(c.label(), "Acme Shop App #T1-02")
        self.assertTrue(c.in_project)

    def test_src_workspace(self):
        c = self.ctx(self.root_dir() / "acme" / "src" / "shop-app")
        self.assertEqual(c.name, "acme/shop-app")
        self.assertEqual(c.slug, "acme-shop-app-00")
        self.assertEqual(c.tunnel_label(3000), "acme-shop-app-3000")
        self.assertEqual(c.label(), "Acme Shop App #T1-00")

    def test_short_repo(self):
        c = self.ctx(self.root_dir() / "hooli" / "src" / "hooli-even")
        self.assertEqual(c.kind, "projects")
        self.assertEqual(c.short_repo, "even")
        self.assertEqual(c.slug, "hooli-even-00")
        self.assertEqual(c.label(), "Hooli Even #T1-00")
        same = self.ctx(self.root_dir() / "x" / "src" / "x")
        self.assertEqual(same.short_repo, "")
        self.assertEqual(same.slug, "x-00")
        self.assertEqual(same.label(), "X #T1-00")

    def test_project_and_workspace_roots(self):
        c = self.ctx(self.root_dir() / "acme")
        self.assertEqual((c.project, c.ws, c.repo), ("acme", None, None))
        self.assertEqual(c.name, "acme")
        self.assertEqual(c.slug, "acme")
        self.assertEqual(c.label(), "Acme #T1")
        w = self.ctx(self.root_dir() / "acme" / "src-02")
        self.assertEqual(w.name, "acme@02")
        self.assertEqual(w.slug, "acme-02")
        self.assertEqual(w.label(), "Acme #T1")
        self.assertEqual(w.path, self.root_dir() / "acme" / "src-02")

    def test_literal_workspace(self):
        c = self.ctx(self.root_dir() / "p" / "misc" / "r")
        self.assertEqual((c.ws, c.ws_id), ("misc", "misc"))
        self.assertEqual(c.name, "p/r@misc")

    def test_outside_roots(self):
        d = self.tmp / "x"
        d.mkdir()
        c = self.ctx(d)
        self.assertIsNone(c.kind)
        self.assertIsNone(c.project)
        self.assertIsNone(c.name)
        self.assertEqual(c.path, d)
        self.assertEqual(c.slug, "x")
        self.assertEqual(c.session("claude"), "claude-x")
        self.assertEqual(c.tunnel_label(8080), "x-8080")
        self.assertEqual(c.label(), "X #T1")
        with self.assertRaises(UsageError) as cm:
            c.require("repo")
        self.assertIn("not inside a project", cm.exception.message)
        self.assertIn("pass a target", cm.exception.message)

    def test_at_root_itself(self):
        c = self.ctx(self.root_dir())
        self.assertEqual(c.kind, "projects")
        self.assertIsNone(c.project)
        self.assertEqual(c.slug, "myprojects")

    def test_require(self):
        c = self.ctx(self.root_dir() / "p")
        self.assertIs(c.require("project"), c)
        with self.assertRaises(UsageError) as cm:
            c.require("repo")
        self.assertIn("of p", cm.exception.message)

    def test_longest_root_wins(self):
        inner = self.root_dir() / "work" / "clients"
        self.config('[roots]\nclients = "%s"\n' % inner.as_posix())
        c = self.ctx(inner / "acme" / "src" / "api")
        self.assertEqual(c.root_key, "clients")
        self.assertEqual(c.project, "acme")
        self.assertEqual(c.kind, "projects")

    def test_roots_from_env_and_expansion(self):
        os.environ["MYPROJECTS_DIR"] = str(self.tmp / "elsewhere")
        c = self.ctx(self.tmp / "elsewhere" / "p")
        self.assertEqual(c.project, "p")
        os.environ["SOMEROOT"] = str(self.tmp / "via-var")
        self.config('[roots]\nprojects = "$SOMEROOT"\n')
        c = self.ctx(self.tmp / "via-var" / "q")
        self.assertEqual(c.project, "q")

    def test_symlinked_root_is_not_resolved(self):
        if os.name == "nt":
            self.skipTest("symlinks")
        real = self.tmp / "real-projects"
        (real / "p" / "src" / "r").mkdir(parents=True)
        link = self.home / "myprojects"
        link.symlink_to(real)
        c = self.ctx(link / "p" / "src" / "r")
        self.assertEqual(c.root, link)
        self.assertEqual(c.path, link / "p" / "src" / "r")
        # the resolved path still matches, reported under the configured root
        c2 = self.ctx(real / "p" / "src" / "r")
        self.assertEqual(c2.project, "p")
        self.assertEqual(c2.root, link)

    def test_locate_prefix_is_not_a_match(self):
        key, root, parts = locate(Path("/a/bcd/x"), {"projects": Path("/a/b")})
        self.assertIsNone(key)

    def test_git_root_and_json(self):
        repo = self.root_dir() / "p" / "src" / "r"
        (repo / ".git").mkdir(parents=True)
        (repo / "sub").mkdir()
        c = self.ctx(repo / "sub")
        self.assertEqual(c.git_root, repo)
        j = c.to_json()
        self.assertEqual(set(j), {"kind", "root", "project", "ws", "ws_id", "repo", "path",
                                  "name", "slug", "git_root", "machine"})
        self.assertEqual(j["git_root"], str(repo))
        self.assertEqual(j["machine"], "T1")
        # .git as a file (worktrees, submodules) counts too
        other = self.tmp / "wt"
        other.mkdir()
        (other / ".git").write_text("gitdir: /elsewhere\n")
        self.assertEqual(self.ctx(other).git_root, other)

    def test_for_path(self):
        c = self.ctx(self.tmp, dry_run=True)
        d = c.for_path(self.root_dir() / "p" / "src" / "r")
        self.assertEqual(d.name, "p/r")
        self.assertTrue(d.options.dry_run)


class Machine(TnTestCase):
    def test_env_wins(self):
        c = Context.build(self.tmp, Options(), Config.load())
        self.assertEqual(c.machine, "T1")

    def test_local_env(self):
        del os.environ["MY_MACHINE"]
        f = self.home / ".config" / "dot" / "local.env"
        f.parent.mkdir(parents=True)
        f.write_text('DOT_PROFILE=mac\nMY_MACHINE=OLD\nexport MY_MACHINE="U2"  \n')
        c = Context.build(self.tmp, Options(), Config.load())
        self.assertEqual(c.machine, "U2")

    def test_missing_is_exit_3(self):
        del os.environ["MY_MACHINE"]
        c = Context.build(self.tmp, Options(), Config.load())
        self.assertIsNone(c.machine)
        with self.assertRaises(Missing) as cm:
            c.label()
        self.assertEqual(cm.exception.code, 3)
        self.assertEqual(cm.exception.fix, "tn config set machine <name>")
        self.assertIn("MY_MACHINE is not set", cm.exception.message)
