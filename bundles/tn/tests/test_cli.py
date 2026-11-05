import json
import os
import sys
from pathlib import Path

from tn.cli import parse_globals
from tn.errors import UsageError
from tn.testing import TnTestCase

import demo_plugins as D


class Globals(TnTestCase):
    def test_parse(self):
        g = parse_globals(["-C", "a", "--json", "demo", "-nyq", "show", "-vv", "x", "--", "-v"])
        self.assertEqual(g.cdirs, ["a"])
        self.assertTrue(g.json and g.dry_run and g.yes and g.quiet)
        self.assertEqual(g.verbose, 2)
        self.assertEqual(g.rest, ["demo", "show", "x", "--", "-v"])
        self.assertEqual(parse_globals(["-Cb", "--verbose", "--no-color"]).cdirs, ["b"])
        with self.assertRaises(UsageError):
            parse_globals(["-C"])
        # a cluster with other letters is not global
        self.assertEqual(parse_globals(["-nx"]).rest, ["-nx"])


class Dispatch(TnTestCase):
    def setUp(self):
        super().setUp()
        self.write_plugin("demo", D.DEMO)

    def test_ls_text_and_json(self):
        r = self.tn("demo", "ls")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "NAME  N\na     1\nb     -\n")
        r = self.tn("demo", "ls", "--json")
        self.assertEqual(r.json, [{"name": "a", "n": 1}, {"name": "b", "n": None}])
        r = self.tn("--json", "demo", "ls")
        self.assertEqual(len(r.json), 2)

    def test_empty_list(self):
        r = self.tn("demo", "empty")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "")
        self.assertIn("Nothing here", r.stderr)
        r = self.tn("demo", "empty", "--json")
        self.assertEqual(r.json, [])
        self.assertEqual(r.stderr, "")

    def test_second_group_of_plugin(self):
        r = self.tn("dd", "verb")
        self.assertEqual(r.stdout, "dd verb\n")

    def test_args_and_completion_kw_are_stripped(self):
        r = self.tn("demo", "show", "thing", "--loud", "--level", "low", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, {"target": "thing", "loud": True, "level": "low", "context": None})
        r = self.tn("demo", "show", "x")
        self.assertEqual(r.stdout, "target=x\n")

    def test_bad_flag_is_usage(self):
        r = self.tn("demo", "show", "--nope")
        self.assertExit(r, 2)
        self.assertIn("tn: unrecognized arguments: --nope", r.stderr)
        self.assertIn("hint: tn demo show --help", r.stderr)
        r = self.tn("demo", "show", "--nope", "--json")
        self.assertExit(r, 2)
        self.assertEqual(r.error["code"], 2)
        self.assertEqual(r.stdout, "")

    def test_two_word_verbs(self):
        self.assertEqual(self.tn("demo", "remote", "add", "gh").stdout, "add gh\n")
        self.assertEqual(self.tn("demo", "remote", "ls").stdout, "remote list\n")
        r = self.tn("demo", "remote")
        self.assertExit(r, 2)
        self.assertIn("remote add, remote ls", r.stderr)

    def test_unknown_verb(self):
        r = self.tn("demo", "frobnicate", "--json")
        self.assertExit(r, 2)
        self.assertIn("ls", r.error["choices"])
        self.assertEqual(r.error["message"], 'unknown command "demo frobnicate"')
        r = self.tn("demo")
        self.assertExit(r, 2)
        self.assertIn("which demo command?", r.stderr)

    def test_default_command_and_passthrough(self):
        r = self.tn("dd", "migrate", "app", "--fake", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, {"opt": None, "rest": ["migrate", "app", "--fake"]})
        r = self.tn("dd", "--opt", "1", "--json", "--", "verb", "-v", "--json")
        self.assertEqual(r.json, {"opt": "1", "rest": ["verb", "-v", "--json"]})
        # a leading -- forces passthrough of a word that is also a verb
        r = self.tn("--json", "dd", "--", "verb")
        self.assertEqual(r.json, {"opt": None, "rest": ["verb"]})
        r = self.tn("dd", "--json")
        self.assertEqual(r.json, {"opt": None, "rest": []})

    def test_group_help(self):
        r = self.tn("demo", "--help")
        self.assertExit(r, 0)
        self.assertIn("usage: tn demo <verb>", r.stdout)
        self.assertIn("remote add", r.stdout)
        self.assertIn("show one thing", r.stdout)
        r = self.tn("dd", "-h")
        self.assertIn("default command:", r.stdout)
        r = self.tn("demo", "show", "--help")
        self.assertExit(r, 0)
        self.assertIn("usage: tn demo show", r.stdout)
        self.assertIn("--loud", r.stdout)

    def test_top_help(self):
        for argv in ([], ["--help"], ["-h"]):
            r = self.tn(*argv)
            self.assertExit(r, 0)
            self.assertIn("usage: tn", r.stdout)
            self.assertIn("demo", r.stdout)
            self.assertIn("demo commands", r.stdout)
            self.assertIn("doctor", r.stdout)
            self.assertTrue(r.stdout.rstrip().endswith("tn <group> --help for its commands"))

    def test_exit_codes(self):
        r = self.tn("demo", "err", "fail")
        self.assertExit(r, 1)
        self.assertEqual(r.stderr, "tn: it broke\n  hint: try again\n")
        r = self.tn("demo", "err", "usage")
        self.assertExit(r, 2)
        self.assertEqual(r.stderr, "tn: which one?\n  choices: x, y\n")
        r = self.tn("demo", "err", "missing")
        self.assertExit(r, 3)
        self.assertEqual(r.stderr, "tn: widget is not installed\n  run: dot apply widget\n")
        r = self.tn("demo", "err", "missing", "--json")
        self.assertEqual(r.error, {"code": 3, "message": "widget is not installed",
                                   "fix": "dot apply widget", "hint": None, "choices": None})
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)
        self.assertExit(self.tn("demo", "err", "code"), 7)
        r = self.tn("demo", "err", "interrupt")
        self.assertExit(r, 130)
        self.assertNotIn("Traceback", r.stderr)

    def test_internal_error(self):
        r = self.tn("demo", "err", "boom")
        self.assertExit(r, 1)
        self.assertIn("tn: internal error in demo: RuntimeError: kaboom (TN_DEBUG=1 for the traceback)",
                      r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        r = self.tn("demo", "err", "boom", env={"TN_DEBUG": "1"})
        self.assertIn("Traceback", r.stderr)
        r = self.tn("-vv", "demo", "err", "boom")
        self.assertIn("Traceback", r.stderr)

    def test_dash_c(self):
        proj = self.root_dir() / "p" / "src" / "r"
        proj.mkdir(parents=True)
        r = self.tn("-C", str(self.root_dir() / "p"), "-C", "src/r", "demo", "where")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "p/r\n")
        r = self.tn("demo", "where", "-C", str(proj))
        self.assertEqual(r.stdout, "p/r\n")
        r = self.tn("-C", "does-not-exist", "demo", "where")
        self.assertExit(r, 2)
        self.assertIn("no such directory", r.stderr)

    def test_context_from_cwd(self):
        proj = self.root_dir() / "acme" / "src-02" / "shop"
        proj.mkdir(parents=True)
        r = self.tn("demo", "where", "--json", cwd=proj)
        self.assertEqual(r.json["name"], "acme/shop@02")
        self.assertEqual(r.json["slug"], "acme-shop-02")

    def test_run_and_dry_run(self):
        self.fake("echo", stdout="said\n")
        r = self.tn("demo", "say", "hi", "there")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "said\n")
        self.assertEqual(self.calls("echo"), [["hi", "there"]])
        r = self.tn("-n", "demo", "say", "again")
        self.assertExit(r, 0)
        self.assertEqual(r.stderr, "would: run echo again\n")
        self.assertEqual(len(self.calls("echo")), 1)
        r = self.tn("-vv", "demo", "say", "x")
        self.assertIn("+ echo x", r.stderr)

    def test_run_failure(self):
        self.fake("echo", exit=4)
        r = self.tn("demo", "say", "x")
        self.assertExit(r, 1)
        self.assertIn("tn: echo exited 4", r.stderr)

    def test_handoff(self):
        r = self.tn("demo", "go", "vim", handoff_exit=5)
        self.assertExit(r, 5)
        self.assertEqual(r.handoff, ["vim", "--flag"])
        r = self.tn("demo", "go", "vim", "--json")
        self.assertExit(r, 2)
        self.assertIsNone(r.handoff)
        self.assertIn("--json is not supported", r.error["message"])
        r = self.tn("demo", "go", "vim", "--dry-run")
        self.assertExit(r, 0)
        self.assertIsNone(r.handoff)
        self.assertIn("would: run vim --flag", r.stderr)

    def test_request_cd(self):
        r = self.tn("demo", "jump", str(self.tmp))
        self.assertExit(r, 0)
        self.assertEqual(r.cd, str(self.tmp))
        self.assertEqual(r.stdout, "")
        r = self.tn("demo", "jump", str(self.tmp), env={"TN_CD_FILE": None})
        self.assertEqual(r.stdout, str(self.tmp) + "\n")
        self.assertIn("tn shell init", r.stderr)
        r = self.tn("demo", "jump", str(self.tmp), "-n")
        self.assertIsNone(r.cd)
        self.assertIn("would: cd", r.stderr)

    def test_quiet_hides_progress_not_errors(self):
        r = self.tn("-q", "demo", "empty")
        self.assertEqual(r.stderr, "")
        r = self.tn("-q", "demo", "err", "fail")
        self.assertIn("tn: it broke", r.stderr)


class Pickers(TnTestCase):
    def setUp(self):
        super().setUp()
        self.write_plugin("demo", D.DEMO)

    def test_no_tty_exits_2_with_choices(self):
        r = self.tn("demo", "choose", "--json")
        self.assertExit(r, 2)
        self.assertEqual(r.error["message"], "which thing?")
        self.assertEqual(r.error["choices"], ["alpha", "beta", "gamma"])
        r = self.tn("demo", "choose")
        self.assertIn("choices: alpha, beta, gamma", r.stderr)

    def test_choices_are_values_a_caller_can_pass_back(self):
        r = self.tn("demo", "labelled", "--json")
        self.assertExit(r, 2)
        self.assertEqual(r.error["choices"], ["alpha", "beta"])
        for c in r.error["choices"]:
            again = self.tn("demo", "labelled", c, "--json")
            self.assertExit(again, 0)
            self.assertEqual(again.stdout, c + "\n")
        r = self.tn("demo", "labelled", tty=True, stdin="2\n")
        self.assertIn("2) beta  the second letter", r.stderr)
        self.assertEqual(r.stdout, "beta\n")
        r = self.tn("demo", "valued", "--json")
        self.assertEqual(r.error["choices"], ["1", "2"])
        self.assertEqual(self.tn("demo", "valued", r.error["choices"][0]).stdout, "1\n")

    def test_first_column(self):
        from tn.prompt import first_column
        self.assertEqual(first_column("claude-acme-shop-00  Acme Shop #U1-00"),
                         "claude-acme-shop-00")
        self.assertEqual(first_column("3000  private  https://x.example.com"), "3000")
        self.assertEqual(first_column("web  (1 window, claude)"), "web")
        self.assertEqual(first_column("a\tb"), "a")
        self.assertEqual(first_column("plain"), "plain")

    def test_numbered_list(self):
        r = self.tn("demo", "choose", tty=True, stdin="2\n")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "beta\n")
        self.assertIn("1) alpha", r.stderr)
        self.assertIn("[1-3, or blank to cancel]", r.stderr)

    def test_cancel(self):
        r = self.tn("demo", "choose", tty=True, stdin="\n")
        self.assertExit(r, 1)
        self.assertIn("tn: cancelled", r.stderr)
        r = self.tn("demo", "choose", tty=True, stdin="")
        self.assertExit(r, 1)

    def test_json_never_prompts(self):
        r = self.tn("demo", "choose", "--json", tty=True, stdin="1\n")
        self.assertExit(r, 2)

    def test_fzf(self):
        self.fake("fzf", stdout="2\tgamma\n")
        r = self.tn("demo", "choose", tty=True, env={"TN_PICKER": None})
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "gamma\n")
        rec = self.call_records("fzf")[0]
        self.assertIn("--with-nth=2..", rec["argv"])
        self.assertEqual(rec["stdin"], "0\talpha\n1\tbeta\n2\tgamma\n")
        self.fake("fzf", exit=130)
        r = self.tn("demo", "choose", tty=True, env={"TN_PICKER": None})
        self.assertExit(r, 1)
        self.assertIn("cancelled", r.stderr)
        # TN_PICKER=list wins over fzf
        r = self.tn("demo", "choose", tty=True, stdin="1\n")
        self.assertEqual(r.stdout, "alpha\n")

    def test_confirm(self):
        r = self.tn("demo", "sure")
        self.assertExit(r, 2)
        self.assertIn("really do it? — pass --yes to confirm", r.stderr)
        self.assertEqual(self.tn("demo", "sure", "--yes").stdout, "yes\n")
        self.assertEqual(self.tn("demo", "sure", "-y").stdout, "yes\n")
        self.assertEqual(self.tn("demo", "sure", tty=True, stdin="y\n").stdout, "yes\n")
        self.assertEqual(self.tn("demo", "sure", tty=True, stdin="\n").stdout, "no\n")


class Discovery(TnTestCase):
    def test_missing_group_from_repo(self):
        repo = self.tmp / "dotfiles"
        (repo / "bundles" / "widget").mkdir(parents=True)
        (repo / "bundles" / "widget" / "plugin.py").write_text(
            'from tn import Plugin\nplugin = Plugin("widget", help="a widget")\n')
        r = self.tn("widget", "up", env={"DOT_REPO": str(repo)})
        self.assertExit(r, 3)
        self.assertEqual(r.stderr, 'tn: "widget" comes from the widget bundle, which is not applied '
                                   'on this machine\n  run: dot apply widget\n')
        r = self.tn("widgett", env={"DOT_REPO": str(repo)})
        self.assertExit(r, 2)
        self.assertIn('tn: unknown command "widgett"', r.stderr)
        self.assertIn('did you mean "widget"?', r.stderr)

    def test_dot_repo_from_local_env(self):
        repo = self.tmp / "checkout"
        (repo / "bundles" / "my-tool").mkdir(parents=True)
        (repo / "bundles" / "my-tool" / "plugin.py").write_text(
            'from tn import Plugin\nplugin = Plugin("my_tool", groups=["mt"])\n')
        le = self.home / ".config" / "dot" / "local.env"
        le.parent.mkdir(parents=True)
        le.write_text("DOT_REPO=%s\n" % repo)
        r = self.tn("mt")
        self.assertExit(r, 3)
        self.assertIn("run: dot apply my-tool", r.stderr)

    def test_dot_repo_defaults_to_dot_never_the_old_dotfiles(self):
        def bundle(root):
            (root / "bundles" / "my-tool").mkdir(parents=True)
            (root / "bundles" / "my-tool" / "plugin.py").write_text(
                'from tn import Plugin\nplugin = Plugin("my_tool", groups=["mt"])\n')
        # ~/.dotfiles is the old dotbot checkout: never looked at.
        bundle(self.home / ".dotfiles")
        r = self.tn("mt")
        self.assertExit(r, 2)
        self.assertIn('tn: unknown command "mt"', r.stderr)
        bundle(self.home / ".dot")
        r = self.tn("mt")
        self.assertExit(r, 3)
        self.assertIn("run: dot apply my-tool", r.stderr)

    def test_unknown_without_repo(self):
        r = self.tn("zzz")
        self.assertExit(r, 2)
        self.assertIn("tn --help lists the groups", r.stderr)
        r = self.tn("statsu")
        self.assertIn('did you mean "status"?', r.stderr)

    def test_clash_refuses_only_that_group(self):
        self.write_plugin("one", 'from tn import Plugin, out\nplugin = Plugin("one", groups=["tunnel", "x1"])\n'
                                 '@plugin.command()\ndef ls(ctx, a):\n    out.line("one")\n'
                                 '@plugin.command(group="x1")\ndef ls_x(ctx, a):\n    out.line("x1")\n')
        self.write_plugin("two", 'from tn import Plugin\nplugin = Plugin("two", groups=["tunnel"])\n')
        r = self.tn("tunnel", "ls")
        self.assertExit(r, 1)
        self.assertEqual(r.stderr, 'tn: group "tunnel" is claimed by both one.py and two.py; '
                                   'remove one (dot remove <bundle>)\n')
        r = self.tn("x1", "ls-x")
        self.assertExit(r, 0)
        r = self.tn("plugins", "--json")
        states = {p["name"]: p["state"] for p in r.json}
        self.assertEqual(states["one"], "clash: tunnel also in two")

    def test_builtin_name_is_refused(self):
        self.write_plugin("st", 'from tn import Plugin\nplugin = Plugin("st", groups=["status", "st"])\n')
        r = self.tn("status")
        self.assertExit(r, 0)          # the built-in still works
        r = self.tn("plugins", "--json")
        self.assertIn("clash: status", r.json[0]["state"])

    def test_broken_plugin_isolated(self):
        self.write_plugin("demo", D.DEMO)
        self.write_plugin("bad", D.BROKEN_IMPORT)
        self.write_plugin("nl", D.NOT_LITERAL)
        r = self.tn("demo", "ls")
        self.assertExit(r, 0)
        r = self.tn("bad", "x")
        self.assertExit(r, 1)
        self.assertIn("the bad plugin failed to load: ImportError: no such thing", r.stderr)
        r = self.tn("nl")
        self.assertExit(r, 1)
        self.assertIn("broken", r.stderr)
        self.assertIn("not a literal", r.stderr)

    def test_requires(self):
        self.write_plugin("child", D.NEEDS_BASE)
        r = self.tn("child", "hi")
        self.assertExit(r, 3)
        self.assertEqual(r.stderr, "tn: the child plugin needs the base plugin\n"
                                   "  run: dot apply base\n")
        self.write_plugin("base", D.BASE)
        r = self.tn("child", "hi")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "hello from base\n")

    def test_package_plugin_and_first_dir_wins(self):
        d = self.plugin_dir()
        pkg = d / "pk"
        pkg.mkdir()
        (pkg / "__init__.py").write_text(
            'from tn import Plugin, out\nfrom .helper import word\nplugin = Plugin("pk")\n'
            '@plugin.command()\ndef ls(ctx, a):\n    out.line(word())\n')
        (pkg / "helper.py").write_text('def word():\n    return "from package"\n')
        second = self.tmp / "second"
        second.mkdir()
        (second / "pk.py").write_text('from tn import Plugin\nplugin = Plugin("pk")\n')
        os.environ["TN_PLUGIN_PATH"] = os.pathsep.join([str(d), str(second)])
        r = self.tn("pk", "ls")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "from package\n")
        r = self.tn("-v", "pk", "ls")
        self.assertIn("ignoring", r.stderr)

    def test_file_and_package_same_name(self):
        d = self.plugin_dir()
        (d / "dup").mkdir()
        (d / "dup" / "__init__.py").write_text('from tn import Plugin\nplugin = Plugin("dup")\n')
        (d / "dup.py").write_text('from tn import Plugin\nplugin = Plugin("dup")\n')
        r = self.tn("plugins", "--json")
        st = [p for p in r.json if p["name"] == "dup"][0]["state"]
        self.assertIn("broken", st)

    def test_name_must_match_file(self):
        self.write_plugin("wrong", 'from tn import Plugin\nplugin = Plugin("other")\n')
        r = self.tn("plugins", "--json")
        self.assertIn("does not match its file name", r.json[0]["state"])

    def test_lazy_loading(self):
        # a plugin that would fail at import is never imported for another group
        self.write_plugin("demo", D.DEMO)
        self.write_plugin("bad", D.BROKEN_IMPORT)
        r = self.tn("demo", "ls")
        self.assertExit(r, 0)
        self.assertNotIn("tn.plugins.bad", sys.modules)

    def test_index_cache(self):
        self.write_plugin("demo", D.DEMO)
        self.tn("demo", "ls")
        cache = self.home / ".cache" / "tn" / "index.json"
        self.assertTrue(cache.is_file())
        data = json.loads(cache.read_text())
        self.assertEqual(data["version"], 1)
        # a changed file is re-indexed
        p = self.plugin_dir() / "demo.py"
        p.write_text(D.DEMO.replace('help="demo commands"', 'help="changed help"'))
        os.utime(p, ns=(1, 1))
        r = self.tn("--help")
        self.assertIn("changed help", r.stdout)

    def test_reserved_flag(self):
        self.write_plugin("rf", 'from tn import Plugin, arg\nplugin = Plugin("rf")\n'
                                '@plugin.command()\n@arg("-n", type=int)\ndef log(ctx, a):\n    pass\n')
        r = self.tn("rf", "log")
        self.assertExit(r, 1)
        self.assertIn("reserved flag -n", r.stderr)


class Version(TnTestCase):
    def test_version(self):
        import tn
        r = self.tn("--version")
        self.assertExit(r, 0)
        self.assertTrue(r.stdout.startswith("tn %s (python " % tn.__version__))
        self.write_plugin("demo", D.DEMO)
        r = self.tn("--version", "--json")
        self.assertEqual(r.json["tn"], tn.__version__)
        self.assertIn("demo", r.json["plugins"])

    def test_entry_point(self):
        r = self.tn_proc("--version")
        self.assertExit(r, 0)
        self.assertIn("tn ", r.stdout)
        r = self.tn_proc("nothing-here")
        self.assertExit(r, 2)

    def _run_as_old_python(self, env, *argv):
        # Run bin/tn under a fake old interpreter version by patching sys.version_info.
        from tn.testing import BIN_TN
        code = ("import sys\nsys.version_info = (3, 9, 0, 'final', 0)\n"
                "sys.argv = %r\nexec(compile(open(%r).read(), %r, 'exec'))\n"
                % ([str(BIN_TN), *argv], str(BIN_TN), str(BIN_TN)))
        import subprocess
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)

    def test_version_gate(self):
        # No newer interpreter to hand over to (TN_REEXEC is set): the gate explains and exits 3.
        p = self._run_as_old_python(dict(os.environ, TN_REEXEC="1"))
        self.assertEqual(p.returncode, 3)
        self.assertIn("tn: needs Python 3.11 or later (this is 3.9)", p.stderr)
        self.assertIn("run: dot apply common", p.stderr)

    def test_old_python_hands_over_to_a_newer_one(self):
        # An old `python3` first on PATH: tn finds this (3.11+) interpreter and re-runs with it.
        env = dict(os.environ, PATH=os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""))
        env.pop("TN_REEXEC", None)
        p = self._run_as_old_python(env, "--version")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("tn ", p.stdout)

    def test_python_dash_m(self):
        import subprocess
        from tn.testing import LIB_DIR
        env = dict(os.environ, PYTHONPATH=str(LIB_DIR))
        p = subprocess.run([sys.executable, "-m", "tn", "--version"], capture_output=True,
                           text=True, env=env, cwd=str(self.home))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("tn ", p.stdout)
