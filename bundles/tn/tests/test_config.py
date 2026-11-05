import os
import tomllib
from pathlib import Path

from tn import tomlw
from tn.config import Config, ConfigError, render, split_url
from tn.context import Context
from tn.errors import UsageError
from tn.options import Options
from tn.testing import TnTestCase

GIT_TOML = '''
[forges.gh]
host = "github.com"
cli = "gh"
owner = "alex"
remote = "github"

[forges.work]
host = "gitlab.example.com"
cli = "glab"
remote = "gitlab"

[forges.bitbucket]
host = "bitbucket.org"
path = "alex/{project}-{repo}"

[people.alex-work]
name = "Alex Doe"
email = "alex@example.com"
aliases = ["alex"]
'''


class Merge(TnTestCase):
    def test_defaults(self):
        cfg = Config.load()
        self.assertEqual(cfg.get("proj.dirs"), ["src", "bin", "rel", "key", "tmp"])
        self.assertEqual(cfg.roots["projects"], self.home / "myprojects")
        self.assertEqual(list(cfg.roots), ["projects"])
        self.assertIsNone(cfg.get("nope.nothing"))
        self.assertEqual(cfg.sources, [])

    def test_order_and_table_merge(self):
        self.conf_d("20-b", '[alpha]\nname = "b"\n[beta]\ndefault = "lab"\n')
        self.conf_d("10-a", '[alpha]\nname = "a"\ndir = "~/a"\n[claude]\nlist = [1, 2]\n')
        self.config('[alpha]\nname = "user"\n[claude]\nlist = [3]\n')
        cfg = Config.load()
        self.assertEqual(cfg.get("alpha.name"), "user")
        self.assertEqual(cfg.get("alpha.dir"), "~/a")
        self.assertEqual(cfg.get("beta.default"), "lab")
        self.assertEqual(cfg.get("claude.list"), [3])          # arrays replaced whole
        self.assertEqual([p.name for p in cfg.sources], ["10-a.toml", "20-b.toml", "config.toml"])

    def test_invalid_file_names_file_and_line(self):
        self.config('[vm]\nname = "x"\nbroken = \n')
        with self.assertRaises(ConfigError) as cm:
            Config.load()
        self.assertIn("config.toml", cm.exception.message)
        self.assertIn("line 3", cm.exception.message)
        self.assertEqual(cm.exception.code, 1)
        cfg = Config.load(lenient=True)
        self.assertEqual(len([i for i in cfg.issues if i.level == "fail"]), 1)

    def test_secretish_keys_warn(self):
        self.config('[forges.gh]\nhost = "github.com"\ntoken = "x"\n')
        cfg = Config.load()
        warns = [i.message for i in cfg.issues if i.level == "warn"]
        self.assertTrue(any("forges.gh.token" in w for w in warns), warns)

    def test_project_file(self):
        self.conf_d("git", GIT_TOML)
        self.project_toml("acme", 'forge = "work"\ngroup = "acme/web"\n'
                                     'identity = "alex-work"\nweird = 1\n'
                                     '[tunnel]\nports = [3000, 8080]\n')
        ctx = Context.build(self.root_dir() / "acme" / "src" / "r", Options(), Config.load())
        pc = ctx.config.project
        self.assertEqual(pc.forge, "work")
        self.assertEqual(pc.group, "acme/web")
        self.assertEqual(pc.identity, "alex-work")
        self.assertEqual(pc.tunnel_ports, [3000, 8080])
        self.assertEqual(pc.unknown_keys, ["weird"])
        self.assertTrue(any("weird" in i.message for i in ctx.config.issues))
        self.assertIn(self.root_dir() / "acme" / "tn.toml", ctx.config.sources)
        # project keys never leak into the global namespace
        self.assertIsNone(ctx.config.get("forge"))

    def test_project_defaults_without_file(self):
        ctx = Context.build(self.root_dir() / "p", Options(), Config.load())
        pc = ctx.config.project
        self.assertFalse(pc.exists)
        self.assertEqual(pc.group, "p")
        self.assertIsNone(pc.forge)
        outside = Context.build(self.tmp, Options(), Config.load())
        self.assertIsNone(outside.config.project)

    def test_bad_project_types(self):
        self.project_toml("p", '[tunnel]\nports = ["x"]\n')
        with self.assertRaises(ConfigError):
            Context.build(self.root_dir() / "p", Options(), Config.load())


class Forges(TnTestCase):
    def setUp(self):
        super().setUp()
        self.conf_d("git", GIT_TOML)
        self.cfg = Config.load()

    def test_defaults_filled(self):
        gh = self.cfg.forge("gh")
        self.assertEqual((gh.kind, gh.clone, gh.remote, gh.owner), ("github", "cli", "github", "alex"))
        bb = self.cfg.forge("bitbucket")
        self.assertEqual((bb.cli, bb.kind, bb.clone, bb.remote), ("none", "bitbucket", "ssh", "bitbucket"))
        self.assertEqual(bb.web_url("a/b"), "https://bitbucket.org/a/b")

    def test_paths_and_urls(self):
        gh = self.cfg.forge("gh")
        self.assertEqual(gh.repo_path(project="p", repo="r"), "alex/r")
        self.assertEqual(gh.repo_path(project="p", repo="r", group="grp"), "grp/r")
        self.assertEqual(gh.ssh("o/r"), "git@github.com:o/r.git")
        self.assertEqual(gh.https("o/r"), "https://github.com/o/r.git")
        bb = self.cfg.forge("bitbucket")
        self.assertEqual(bb.repo_path(project="p", repo="r"), "alex/p-r")
        work = self.cfg.forge("work")
        self.assertEqual(work.repo_path(project="p", repo="r"), "p/r")
        self.assertEqual(work.url("team/x"), "git@gitlab.example.com:team/x.git")

    def test_unknown_forge_is_usage_error(self):
        with self.assertRaises(UsageError) as cm:
            self.cfg.forge("nope")
        self.assertEqual(cm.exception.choices, ["bitbucket", "gh", "work"])

    def test_unknown_placeholder(self):
        self.conf_d("zz", '[forges.x]\nhost = "x.example"\npath = "{nope}/{repo}"\n')
        with self.assertRaises(ConfigError) as cm:
            Config.load()
        self.assertIn("{nope}", cm.exception.message)
        with self.assertRaises(ConfigError):
            render("{bad}")

    def test_split_url(self):
        self.assertEqual(split_url("git@github.com:owner/repo.git"), ("github.com", "owner/repo"))
        self.assertEqual(split_url("https://gitlab.example.com/team/a/b-app.git"),
                         ("gitlab.example.com", "team/a/b-app"))
        self.assertEqual(split_url("ssh://git@Host.example:2222/a/b"), ("host.example", "a/b"))
        self.assertEqual(split_url("https://user@github.com/o/r/"), ("github.com", "o/r"))
        self.assertEqual(split_url("/local/path"), (None, None))
        self.assertEqual(split_url("C:\\x\\y"), (None, None))

    def test_forge_for_url_and_spec(self):
        self.assertEqual(self.cfg.forge_for_url("git@gitlab.example.com:acme/shop-app.git").key,
                         "work")
        self.assertEqual(self.cfg.forge_spec("https://github.com/o/r.git"), "gh:o/r")
        self.assertIsNone(self.cfg.forge_spec("git@unknown.example:o/r.git"))

    def test_people_and_me(self):
        p = self.cfg.person("alex-work")
        self.assertEqual((p.name, p.email, p.aliases), ("Alex Doe", "alex@example.com", ("alex",)))
        me = self.cfg.person("me")
        self.assertEqual((me.name, me.email), ("Test User", "test@example.com"))
        self.assertEqual([x.key for x in self.cfg.people()], ["alex-work", "me"])
        del os.environ["MY_EMAIL"]
        self.assertIsNone(Config.load().person("me"))
        self.config('[people.me]\nname = "Override"\nemail = "o@example.com"\n')
        self.assertEqual(Config.load().person("me").name, "Override")

    def test_person_needs_name_and_email(self):
        self.conf_d("zz", '[people.x]\nname = "No Email"\n')
        with self.assertRaises(ConfigError):
            Config.load()


class TomlEdit(TnTestCase):
    def test_parse_value(self):
        self.assertEqual(tomlw.parse_value("3000"), 3000)
        self.assertEqual(tomlw.parse_value("true"), True)
        self.assertEqual(tomlw.parse_value('["a", "b"]'), ["a", "b"])
        self.assertEqual(tomlw.parse_value("word"), "word")
        self.assertEqual(tomlw.parse_value("two words"), "two words")

    def test_set_existing_line_keeps_the_rest(self):
        text = '# top comment\n[vm]\nname = "old"  # c\ndir = "~/vms"\n\n[claude]\ntrust = true\n'
        new = tomlw.set_key(text, "vm.name", "new")
        self.assertEqual(new, '# top comment\n[vm]\nname = "new"\ndir = "~/vms"\n\n'
                              '[claude]\ntrust = true\n')

    def test_append_to_table_and_new_table(self):
        text = '[vm]\nname = "x"\n\n[claude]\ntrust = true\n'
        new = tomlw.set_key(text, "vm.dir", "~/v")
        self.assertEqual(tomllib.loads(new)["vm"], {"name": "x", "dir": "~/v"})
        self.assertIn('name = "x"\ndir = "~/v"\n\n[claude]', new)
        new2 = tomlw.set_key(text, "forges.gh.host", "github.com")
        self.assertTrue(new2.endswith('[forges.gh]\nhost = "github.com"\n'))
        self.assertEqual(tomllib.loads(new2)["forges"]["gh"]["host"], "github.com")

    def test_top_level_key(self):
        text = '# hi\nforge = "gh"\n\n[tunnel]\nports = [1]\n'
        new = tomlw.set_key(text, "identity", "me")
        d = tomllib.loads(new)
        self.assertEqual(d["identity"], "me")
        self.assertEqual(d["tunnel"]["ports"], [1])
        self.assertEqual(tomlw.set_key("", "forge", "gh"), 'forge = "gh"\n')

    def test_bad_key(self):
        with self.assertRaises(ValueError):
            tomlw.set_key("", "a..b", 1)

    def test_dumps_round_trip(self):
        data = {"a": 1, "roots": {"projects": "~/p"}, "forges": {"gh": {"host": "h", "x": [1, 2]}},
                "flag": False}
        self.assertEqual(tomllib.loads(tomlw.dumps(data)), data)
