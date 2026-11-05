"""tn proj new|ls|show, status and doctor hooks, completion."""

from __future__ import annotations

import tomllib

from _base import ProjectsCase


class ProjNew(ProjectsCase):
    def test_creates_the_standard_dirs(self):
        r = self.ok(self.tn("proj", "new", "demo", "--json"))
        pdir = self.projects / "demo"
        self.assertEqual(r.json["project"], "demo")
        self.assertEqual(r.json["root"], "projects")
        self.assertEqual(r.json["path"], str(pdir))
        self.assertEqual(r.json["dirs"], ["src", "bin", "rel", "key", "tmp"])
        self.assertEqual(r.json["config"], {"forge": None, "group": None, "identity": None})
        for d in ("src", "bin", "rel", "key", "tmp"):
            self.assertTrue((pdir / d).is_dir(), d)
        self.assertFalse((pdir / "tn.toml").exists())
        self.assertIn("tn repo new <name> -p demo", r.stderr)

    def test_text_prints_the_path(self):
        r = self.ok(self.tn("proj", "new", "abc"))
        self.assertEqual(r.stdout.strip(), str(self.projects / "abc"))

    def test_writes_tn_toml(self):
        r = self.ok(self.tn("proj", "new", "acme", "--forge", "work", "--group",
                            "acme/web", "--identity", "alex-work", "--json"))
        data = tomllib.loads((self.projects / "acme" / "tn.toml").read_text())
        self.assertEqual(data, {"forge": "work", "group": "acme/web",
                                "identity": "alex-work"})
        self.assertEqual(r.json["config"]["forge"], "work")

    def test_proj_dirs_from_config(self):
        self.config('[proj]\ndirs = ["src", "docs"]\n')
        self.ok(self.tn("proj", "new", "p1"))
        self.assertTrue((self.projects / "p1" / "docs").is_dir())
        self.assertFalse((self.projects / "p1" / "bin").exists())

    def test_invalid_name(self):
        r = self.tn("proj", "new", "Bad Name")
        self.assertExit(r, 2)
        self.assertIn("invalid project name", r.stderr)

    def test_unknown_root(self):
        r = self.tn("proj", "new", "x", "--root", "nope", "--json")
        self.assertExit(r, 2)
        self.assertEqual(r.error["choices"], ["projects"])

    def test_unknown_forge_and_person(self):
        r = self.tn("proj", "new", "x", "--forge", "nope", "--json")
        self.assertExit(r, 2)
        self.assertIn("gh", r.error["choices"])
        r = self.tn("proj", "new", "x", "--identity", "nobody", "--json")
        self.assertExit(r, 2)
        self.assertIn("alex-work", r.error["choices"])
        self.assertFalse((self.projects / "x").exists())

    def test_exists(self):
        self.make_project("dup")
        r = self.tn("proj", "new", "dup")
        self.assertExit(r, 1)
        self.assertIn("already exists", r.stderr)

    def test_dry_run_changes_nothing(self):
        r = self.ok(self.tn("proj", "new", "dry", "-n", "--forge", "gh", "--json"))
        self.assertTrue(r.json["dry_run"])
        self.assertIn("would: mkdir", r.stderr)
        self.assertIn("would: write", r.stderr)
        self.assertFalse((self.projects / "dry").exists())

    def test_cd(self):
        r = self.ok(self.tn("proj", "new", "go", "--cd"))
        self.assertEqual(r.cd, str(self.projects / "go"))


class ProjLs(ProjectsCase):
    def setUp(self):
        super().setUp()
        self.make_project("acme", repos=["shop-app", "shop-all"], workspaces=["src-02"],
                          toml='forge = "work"\nidentity = "alex-work"\n')
        self.make_project("demo", repos=["app"])
        (self.projects / ".hidden").mkdir()
        (self.projects / "notes.txt").write_text("x")

    def test_json(self):
        r = self.ok(self.tn("proj", "ls", "--json"))
        rows = {x["name"]: x for x in r.json}
        self.assertEqual(sorted(rows), ["acme", "demo"])
        h = rows["acme"]
        self.assertEqual(h["repos"], ["shop-all", "shop-app"])
        self.assertEqual(h["workspaces"], ["02"])
        self.assertEqual(h["forge"], "work")
        self.assertEqual(h["identity"], "alex-work")
        self.assertEqual(h["root"], "projects")
        self.assertEqual(h["path"], str(self.projects / "acme"))
        self.assertIsNone(rows["demo"]["forge"])

    def test_root(self):
        r = self.ok(self.tn("proj", "ls", "--root", "projects", "--json"))
        self.assertEqual(sorted(x["name"] for x in r.json), ["acme", "demo"])
        r = self.tn("proj", "ls", "--root", "nope", "--json")
        self.assertExit(r, 2)

    def test_text(self):
        r = self.ok(self.tn("proj", "ls"))
        lines = r.stdout.splitlines()
        self.assertTrue(lines[0].startswith("PROJECT"))
        self.assertIn("acme", r.stdout)
        row = [x for x in lines if x.startswith("acme")][0].split()
        self.assertEqual(row[:5], ["acme", "projects", "2", "02", "work"])

    def test_empty(self):
        self.config('[roots]\nprojects = "%s"\n' % (self.tmp / "none"))
        r = self.ok(self.tn("proj", "ls"))
        self.assertEqual(r.stdout, "")
        self.assertIn("No projects", r.stderr)
        self.assertEqual(self.ok(self.tn("proj", "ls", "--json")).json, [])

    def test_bad_toml_is_a_warning(self):
        self.project_toml("demo", "forge = [")
        r = self.ok(self.tn("proj", "ls", "--json"))
        self.assertIn("demo", [x["name"] for x in r.json])
        self.assertIn("warning", r.stderr)

    def test_show(self):
        r = self.ok(self.tn("proj", "show", "--json", cwd=self.projects / "acme" / "src"))
        self.assertEqual(r.json["name"], "acme")
        self.assertEqual([x["repo"] for x in r.json["repos"]], ["shop-all", "shop-app"])
        self.assertEqual(r.json["config"], {"forge": "work", "identity": "alex-work"})
        r = self.ok(self.tn("proj", "show", "demo"))
        self.assertIn("Project:", r.stdout)
        self.assertIn("app", r.stdout)

    def test_show_outside_a_project(self):
        self.assertExit(self.tn("proj", "show"), 2)
        r = self.tn("proj", "show", "nope", "--json")
        self.assertExit(r, 2)


class Hooks(ProjectsCase):
    def test_status_inside_a_project(self):
        p = self.make_project("acme", repos=["shop-app"], workspaces=["src-02"])
        r = self.ok(self.tn("status", "--json", cwd=p.repo("shop-app", "src-02")))
        self.assertEqual(r.json["plugins"]["projects"],
                         ["acme/shop-app@02, 1 repo, workspaces 00 02"])

    def test_status_outside(self):
        r = self.ok(self.tn("status", "--json"))
        self.assertNotIn("projects", r.json.get("plugins", {}))

    def test_doctor_warns_about_missing_roots(self):
        r = self.tn("doctor", "--json")
        rows = [x for x in r.json if x["plugin"] == "proj"]      # rows carry the first group
        warn = [x for x in rows if x["status"] == "warn"]
        self.assertEqual(len(warn), 1, rows)
        self.assertIn("does not exist", warn[0]["check"])
        self.assertIn("mkdir -p", warn[0]["fix"])
        by = {x["check"]: x for x in rows}
        self.assertEqual(by["git installed"]["status"], "ok")
        self.make_project("p")
        r = self.tn("doctor", "--json")
        by = {x["check"]: x for x in r.json if x["plugin"] == "proj"}
        self.assertEqual(by["project roots exist"]["status"], "ok")

    def test_completion(self):
        self.make_project("acme", repos=["shop-app"], workspaces=["src-02"])
        r = self.ok(self.tn("__complete", "2", "--", "tn", "cd", "acm"))
        words = [x.split("\t")[0] for x in r.stdout.splitlines()]
        self.assertIn("acme", words)
        self.assertIn("acme/shop-app@02", words)
        r = self.ok(self.tn("__complete", "3", "--", "tn", "repo", "ls", ""))
        self.assertIn("acme", r.stdout)
