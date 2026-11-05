"""tn repo new|clone|ls|show."""

from __future__ import annotations

from pathlib import Path

from _base import TEST_EMAIL, TEST_NAME, ProjectsCase

# A fake gh / glab whose `repo clone <path> <dir>` makes a real (empty) git repo at <dir>.
CLI_CLONE = """
import subprocess
if argv[:2] == ["repo", "clone"]:
    subprocess.run(["git", "init", "-q", argv[3]], check=True)
"""


class RepoNew(ProjectsCase):
    def setUp(self):
        super().setUp()
        self.p = self.make_project("acme", repos=["shop-app"], workspaces=["src-02"],
                                   toml='forge = "work"\ngroup = "acme/web"\n'
                                        'identity = "alex-work"\n')

    def test_happy_path(self):
        r = self.ok(self.tn("repo", "new", "shop-api", "--json", cwd=self.p.dir))
        target = self.p.repo("shop-api")
        self.assertEqual(r.json, {"project": "acme", "repo": "shop-api", "path": str(target),
                                  "identity": {"key": "alex-work", "name": "Alex Work",
                                               "email": "alex@example.com"},
                                  "remote": None})
        self.assertTrue((target / ".git").is_dir())
        self.assertEqual((target / ".gitattributes").read_text(), "* text=auto\n*.sh text eol=lf\n")
        self.assertEqual(self.local_config(target, "user.email"), "alex@example.com")
        self.assertEqual(self.local_config(target, "user.name"), "Alex Work")
        self.assertIn("tn git remote add", r.stderr)

    def test_goes_to_src_even_from_a_workspace(self):
        r = self.ok(self.tn("repo", "new", "x", "--json", cwd=self.p.repo("shop-app", "src-02")))
        self.assertEqual(r.json["path"], str(self.p.repo("x")))

    def test_identity_falls_back_to_me(self):
        self.make_project("mine")
        r = self.ok(self.tn("repo", "new", "app", "-p", "mine", "--json"))
        self.assertEqual(r.json["identity"]["key"], "me")
        self.assertEqual(self.local_config(Path(r.json["path"]), "user.email"), TEST_EMAIL)
        self.assertEqual(self.local_config(Path(r.json["path"]), "user.name"), TEST_NAME)

    def test_no_identity_at_all(self):
        self.make_project("mine")
        r = self.ok(self.tn("repo", "new", "app", "-p", "mine", "--json",
                            env={"MY_NAME": None, "MY_EMAIL": None}))
        self.assertIsNone(r.json["identity"])
        self.assertIn("global git identity", r.stderr)

    def test_forge_adds_the_remote(self):
        r = self.ok(self.tn("repo", "new", "shop-api", "--forge", "--json", cwd=self.p.dir))
        url = "git@gitlab.example.com:acme/web/shop-api.git"
        self.assertEqual(r.json["remote"], {"name": "gitlab", "url": url})
        self.assertEqual(self.local_config(self.p.repo("shop-api"), "remote.gitlab.url"), url)
        self.assertIn("create it: https://gitlab.example.com/acme/web/shop-api", r.stderr)

    def test_forge_named(self):
        r = self.ok(self.tn("repo", "new", "api", "--forge", "bb", "--no-color", "--json",
                            cwd=self.p.dir))
        self.assertEqual(r.json["remote"]["url"], "git@bitbucket.org:alex/acme-api.git")
        self.assertEqual(r.json["remote"]["name"], "bb")

    def test_forge_default_needs_a_project_forge(self):
        self.make_project("mine")
        r = self.tn("repo", "new", "app", "-p", "mine", "--forge", "--json")
        self.assertExit(r, 2)
        self.assertIn("gh", r.error["choices"])
        self.assertFalse((self.projects / "mine" / "src" / "app").exists())

    def test_exists_and_outside(self):
        self.assertExit(self.tn("repo", "new", "shop-app", cwd=self.p.dir), 1)
        r = self.tn("repo", "new", "x")
        self.assertExit(r, 2)
        self.assertIn("not inside a project", r.stderr)
        self.assertExit(self.tn("repo", "new", "bad/name", cwd=self.p.dir), 2)
        self.assertExit(self.tn("repo", "new", "x", "-p", "nope"), 2)

    def test_dry_run(self):
        r = self.ok(self.tn("repo", "new", "dry", "-n", "--forge", "--json", cwd=self.p.dir))
        self.assertTrue(r.json["dry_run"])
        self.assertIn("would: run git init", r.stderr)
        self.assertFalse(self.p.repo("dry").exists())

    def test_git_missing(self):
        self.config('[roots]\nprojects = "%s"\n' % self.projects)
        import os
        os.environ["PATH"] = str(self.bin)
        r = self.tn("repo", "new", "y", cwd=self.p.dir)
        self.assertExit(r, 3)
        self.assertIn("run: dot apply git", r.stderr)


class RepoClone(ProjectsCase):
    def setUp(self):
        super().setUp()
        self.p = self.make_project("demo", toml='identity = "alex-work"\n')

    def test_url(self):
        src = self.make_repo(self.tmp / "upstream" / "demo-app")
        bare = self.bare("demo-app")
        self.git(src, "remote", "add", "origin", str(bare))
        self.git(src, "push", "-q", "origin", "main")
        url = "file://" + str(bare)
        r = self.ok(self.tn("repo", "clone", url, "app", "--json", cwd=self.p.dir))
        target = self.p.repo("app")
        self.assertEqual(r.json["path"], str(target))
        self.assertEqual(r.json["url"], url)
        self.assertIsNone(r.json["forge"])
        self.assertEqual(r.json["identity"]["key"], "alex-work")
        self.assertTrue((target / "README.md").is_file())
        self.assertEqual(self.local_config(target, "user.email"), "alex@example.com")
        self.assertIn("committer here: Alex Work <alex@example.com>", r.stderr)

    def test_default_name(self):
        bare = self.bare("thing")
        r = self.ok(self.tn("repo", "clone", "file://" + str(bare), "--json", cwd=self.p.dir))
        self.assertEqual(r.json["repo"], "thing")

    def test_asks_for_the_name_on_a_tty(self):
        bare = self.bare("thing")
        r = self.ok(self.tn("repo", "clone", "file://" + str(bare), cwd=self.p.dir, tty=True,
                            stdin="mine\n"))
        self.assertTrue(self.p.repo("mine").is_dir())
        self.assertIn("local name [thing]", r.stderr)

    def test_forge_spec_through_gh(self):
        self.fake("gh", script=CLI_CLONE)
        r = self.ok(self.tn("repo", "clone", "gh:alex/demo-app", "app", "--json",
                            cwd=self.p.dir))
        target = self.p.repo("app")
        self.assertEqual(self.calls("gh"), [["repo", "clone", "alex/demo-app",
                                             str(target)]])
        self.assertEqual(r.json["forge"], "gh")
        self.assertEqual(r.json["source"], "gh:alex/demo-app")
        self.assertEqual(r.json["url"], "git@github.com:alex/demo-app.git")
        self.assertEqual(self.local_config(target, "user.email"), "alex@example.com")

    def test_glab_gets_the_host(self):
        self.fake("glab", script=CLI_CLONE
                  + "\nprint(os.environ.get('GITLAB_HOST'), file=sys.stderr)")
        r = self.ok(self.tn("repo", "clone", "work:acme/web/shop-all", "--json",
                            cwd=self.p.dir))
        self.assertEqual(r.json["repo"], "shop-all")
        self.assertIn("gitlab.example.com", r.stderr)

    def test_bare_owner_repo_uses_the_project_forge(self):
        self.project_toml("demo", 'forge = "gh"\n')
        self.fake("gh", script=CLI_CLONE)
        self.ok(self.tn("repo", "clone", "alex/x", cwd=self.p.dir))
        self.assertEqual(self.calls("gh")[0][:3], ["repo", "clone", "alex/x"])

    def test_bare_owner_repo_without_forge(self):
        r = self.tn("repo", "clone", "alex/x", cwd=self.p.dir)
        self.assertExit(r, 2)
        self.assertIn("say which forge: tn repo clone gh:alex/x", r.stderr)

    def test_unknown_forge(self):
        r = self.tn("repo", "clone", "zz:a/b", "--json", cwd=self.p.dir)
        self.assertExit(r, 2)
        self.assertIn("work", r.error["choices"])

    def test_cli_missing(self):
        r = self.tn("repo", "clone", "gh:alex/x", cwd=self.p.dir)
        self.assertExit(r, 3)
        self.assertIn("run: dot apply gh", r.stderr)

    def test_failed_clone(self):
        r = self.tn("repo", "clone", "file://" + str(self.tmp / "nothing.git"), "x",
                    cwd=self.p.dir)
        self.assertExit(r, 1)
        self.assertFalse(self.p.repo("x").exists())

    def test_exists(self):
        self.make_repo(self.p.repo("app"))
        self.assertExit(self.tn("repo", "clone", "gh:a/app", cwd=self.p.dir), 1)

    def test_dry_run(self):
        self.fake("gh", script=CLI_CLONE)
        r = self.ok(self.tn("repo", "clone", "gh:a/b", "-n", "--json", cwd=self.p.dir))
        self.assertEqual(self.calls("gh"), [])
        self.assertIn("would: run gh repo clone a/b", r.stderr)
        self.assertFalse(self.p.repo("b").exists())

    def test_outside_a_project(self):
        self.assertExit(self.tn("repo", "clone", "gh:a/b"), 2)


class RepoLs(ProjectsCase):
    def setUp(self):
        super().setUp()
        self.p = self.make_project("acme", repos=["shop-app", "shop-all"],
                                   workspaces=["src-02"], toml='identity = "alex-work"\n')
        self.shop_repo = self.p.repo("shop-app")
        self.published(self.shop_repo)
        self.commit(self.shop_repo)                               # ahead 1
        (self.shop_repo / "untracked.txt").write_text("u")        # dirty 1
        self.git(self.shop_repo, "config", "user.email", "alex@example.com")

    def test_json(self):
        r = self.ok(self.tn("repo", "ls", "--json", cwd=self.p.dir))
        rows = {x["repo"]: x for x in r.json}
        self.assertEqual(sorted(rows), ["shop-all", "shop-app"])
        a = rows["shop-app"]
        self.assertEqual(a["branch"], "main")
        self.assertEqual(a["dirty"], 1)
        self.assertEqual((a["ahead"], a["behind"]), (1, 0))
        self.assertEqual(a["upstream"], "origin/main")
        self.assertEqual(a["ws_id"], "00")
        self.assertEqual(a["project"], "acme")
        self.assertEqual(a["remote"], a["remotes"][0]["url"])
        self.assertEqual(a["remotes"][0]["name"], "origin")
        self.assertIsNone(a["remotes"][0]["forge"])
        self.assertEqual(a["identity"], {"name": None, "email": "alex@example.com"})
        self.assertTrue(a["identity_ok"])
        b = rows["shop-all"]
        self.assertIsNone(b["upstream"])
        self.assertIsNone(b["ahead"])
        self.assertIsNone(b["remote"])
        self.assertFalse(b["identity_ok"])

    def test_forge_spec_remote(self):
        self.git(self.p.repo("shop-all"), "remote", "add", "gitlab",
                 "git@gitlab.example.com:acme/web/shop-all.git")
        r = self.ok(self.tn("repo", "ls", "--json", cwd=self.p.dir))
        b = [x for x in r.json if x["repo"] == "shop-all"][0]
        self.assertEqual(b["remote"], "work:acme/web/shop-all")
        self.assertEqual(b["remotes"][0]["forge"], "work")

    def test_workspace_of_the_context(self):
        r = self.ok(self.tn("repo", "ls", "--json", cwd=self.p.ws("src-02")))
        self.assertEqual({x["ws_id"] for x in r.json}, {"02"})
        r = self.ok(self.tn("repo", "ls", "--all-ws", "--json", cwd=self.p.dir))
        self.assertEqual(len(r.json), 4)
        r = self.ok(self.tn("repo", "ls", "acme", "--ws", "02", "--json"))
        self.assertEqual({x["ws_id"] for x in r.json}, {"02"})

    def test_all(self):
        self.make_project("other", repos=["o"])
        r = self.ok(self.tn("repo", "ls", "--all", "--json"))
        self.assertEqual(sorted(x["repo"] for x in r.json), ["o", "shop-all", "shop-app"])
        r = self.ok(self.tn("repo", "ls", "--all"))
        self.assertTrue(r.stdout.startswith("PROJECT"))

    def test_text_and_detached(self):
        head = self.git(self.p.repo("shop-all"), "rev-parse", "HEAD").strip()
        self.git(self.p.repo("shop-all"), "checkout", "-q", "--detach")
        r = self.ok(self.tn("repo", "ls", cwd=self.p.dir))
        self.assertIn("REPO", r.stdout.splitlines()[0])
        self.assertIn("(detached %s)" % head[:7], r.stdout)
        r = self.ok(self.tn("repo", "ls", "--json", cwd=self.p.dir))
        self.assertIsNone([x for x in r.json if x["repo"] == "shop-all"][0]["branch"])

    def test_fetch(self):
        r = self.ok(self.tn("repo", "ls", "--fetch", "--json", cwd=self.p.dir))
        self.assertEqual(len(r.json), 2)

    def test_needs_a_project(self):
        r = self.tn("repo", "ls", "--json")
        self.assertExit(r, 2)
        self.assertIn("acme", r.error["choices"])

    def test_empty(self):
        self.make_project("empty")
        r = self.ok(self.tn("repo", "ls", "empty"))
        self.assertIn("No repos", r.stderr)


class RepoShow(ProjectsCase):
    def test_show(self):
        p = self.make_project("acme", repos=["shop-app"])
        repo = p.repo("shop-app")
        (repo / "web").mkdir()
        (repo / "web" / "package.json").write_text("{}")
        (repo / "manage.py").write_text("")
        (repo / "nginx.conf").write_text("")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-q", "-m", "more")
        r = self.ok(self.tn("repo", "show", "--json", cwd=repo / "web"))
        j = r.json
        self.assertEqual(j["repo"], "shop-app")
        self.assertEqual(j["last_commit"]["subject"], "more")
        self.assertEqual(j["authors"], [{"name": TEST_NAME, "email": TEST_EMAIL, "commits": 2}])
        exts = {f["ext"]: f["count"] for f in j["files"]}
        self.assertEqual(exts[".json"], 1)
        self.assertEqual(exts[".md"], 1)
        self.assertEqual(j["markers"], {"package.json": ["web"], "manage.py": ["."],
                                        "nginx*": ["."]})
        r = self.ok(self.tn("repo", "show", "acme/shop-app"))
        self.assertIn("Last commit:", r.stdout)

    def test_last_commit_date_is_utc(self):
        # Regression: the date kept the author's offset (%aI) and had no age_seconds (§2.4).
        p = self.make_project("acme", repos=["shop-app"])
        repo = p.repo("shop-app")
        (repo / "x.txt").write_text("x")
        self.git(repo, "add", "x.txt")
        self.git(repo, "commit", "-q", "-m", "tz", "--date", "2026-09-30T13:16:01+07:00")
        self.freeze_time(1790748961 + 60)           # 2026-09-30T06:16:01Z plus a minute
        lc = self.ok(self.tn("repo", "show", "--json", cwd=repo)).json["last_commit"]
        self.assertEqual(lc["date"], "2026-09-30T06:16:01Z")
        self.assertEqual(lc["age_seconds"], 60)

    def test_picks_at_a_project_root(self):
        p = self.make_project("acme", repos=["a", "b"])
        r = self.tn("repo", "show", "--json", cwd=p.dir)
        self.assertExit(r, 2)
        self.assertEqual(r.error["choices"], ["a", "b"])
        r = self.ok(self.tn("repo", "show", cwd=p.dir, tty=True, stdin="2\n"))
        self.assertIn("Repo:", r.stdout)
        self.assertIn(" b", r.stdout)

    def test_outside(self):
        self.assertExit(self.tn("repo", "show"), 2)
