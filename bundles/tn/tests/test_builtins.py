import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from tn.testing import TnTestCase

import demo_plugins as D


class Status(TnTestCase):
    def setUp(self):
        super().setUp()
        self.write_plugin("demo", D.DEMO)
        self.repo = self.root_dir() / "acme" / "src-02" / "shop-app"
        self.repo.mkdir(parents=True)

    def test_text(self):
        r = self.tn("status", cwd=self.repo)
        self.assertExit(r, 0)
        lines = r.stdout.splitlines()
        self.assertTrue(lines[0].startswith("context"))
        self.assertIn("acme/shop-app@02", lines[0])
        self.assertIn("~" + os.sep + os.path.join("myprojects", "acme", "src-02", "shop-app"),
                      lines[0])
        self.assertEqual(lines[1].split(), ["machine", "T1"])
        self.assertIn("demo", lines[2])
        self.assertIn("demo here: acme/shop-app@02", lines[2])
        self.assertIn("demo: error: RuntimeError: status exploded", r.stderr)

    def test_outside(self):
        r = self.tn("status", cwd=self.tmp)
        self.assertEqual(r.stdout.splitlines()[0].split(), ["context", "-", str(self.tmp)])

    def test_json(self):
        r = self.tn("status", "--json", cwd=self.repo)
        self.assertExit(r, 0)
        j = r.json
        self.assertEqual(j["context"]["name"], "acme/shop-app@02")
        self.assertEqual(j["context"]["ws_id"], "02")
        self.assertEqual(j["plugins"], {"demo": ["demo here: acme/shop-app@02"]})
        self.assertIn("status exploded", j["errors"]["demo"])

    def test_broken_plugin_is_an_error_row(self):
        self.write_plugin("bad", D.BROKEN_IMPORT)
        r = self.tn("status", "--json")
        self.assertExit(r, 0)
        self.assertIn("failed to load", r.json["errors"]["bad"])

    def test_bad_config_exits_1(self):
        self.config("nope = \n")
        r = self.tn("status")
        self.assertExit(r, 1)
        self.assertIn("config.toml", r.stderr)


class Doctor(TnTestCase):
    def test_rows_and_exit(self):
        self.write_plugin("demo", D.DEMO)
        r = self.tn("doctor", "--json")
        self.assertExit(r, 1)                 # widget installed fails
        rows = r.json
        by = {(x["plugin"], x["check"]): x for x in rows}
        self.assertEqual(by[("demo", "demo ok")]["status"], "ok")
        self.assertEqual(by[("demo", "demo ok")]["detail"], "all fine")
        self.assertEqual(by[("demo", "widget installed")]["status"], "fail")
        self.assertEqual(by[("demo", "widget installed")]["fix"], "dot apply widget")
        self.assertEqual(by[("demo", "something is odd")]["status"], "warn")
        self.assertEqual(by[("demo", "something is odd")]["fix"], "tn demo fix")
        core = [x for x in rows if x["plugin"] == "core"]
        self.assertTrue(core[0]["check"].startswith("Python 3."))
        self.assertTrue(any(x["check"] == "shell integration loaded" and x["status"] == "warn"
                            for x in core))
        for x in rows:
            self.assertEqual(set(x), {"plugin", "check", "status", "detail", "fix"})

    def test_ok_with_warnings_only(self):
        self.write_plugin("quiet", D.CHECK_ONLY)
        r = self.tn("doctor", env={"TN_SHELL": "1"})
        self.assertExit(r, 0)
        self.assertIn("quiet fine", r.stdout)
        self.assertTrue(any(line.startswith("ok    core") for line in r.stdout.splitlines()))
        self.assertIn("warn", r.stdout)           # ~/.local/bin not on PATH

    def test_text_fix_column(self):
        self.write_plugin("demo", D.DEMO)
        r = self.tn("doctor")
        line = [x for x in r.stdout.splitlines() if "widget installed" in x][0]
        self.assertTrue(line.startswith("FAIL  demo"))
        self.assertIn("run: dot apply widget", line)

    def test_machine_and_config_problems_are_rows(self):
        del os.environ["MY_MACHINE"]
        self.config("broken = = 1\n")
        r = self.tn("doctor", "--json")
        rows = r.json
        self.assertTrue(any(x["check"] == "MY_MACHINE set" and x["status"] == "warn"
                            and x["fix"] == "tn config set machine <name>" for x in rows))
        self.assertTrue(any(x["check"] == "config" and x["status"] == "fail"
                            and "config.toml" in x["detail"] for x in rows))
        self.assertExit(r, 1)

    def test_broken_and_clashing_plugins(self):
        self.write_plugin("bad", D.BROKEN_IMPORT)
        self.write_plugin("one", 'from tn import Plugin\nplugin = Plugin("one", groups=["g"])\n')
        self.write_plugin("two", 'from tn import Plugin\nplugin = Plugin("two", groups=["g"])\n')
        self.write_plugin("child", D.NEEDS_BASE)
        rows = self.tn("doctor", "--json").json
        checks = {x["check"]: x for x in rows}
        self.assertEqual(checks["plugin bad imports"]["status"], "fail")
        self.assertEqual(checks["group g has one owner"]["status"], "fail")
        self.assertEqual(checks["plugin child has its requires"]["fix"], "dot apply base")

    def test_local_bin_on_path(self):
        bindir = self.home / ".local" / "bin"
        bindir.mkdir(parents=True)
        tn = bindir / ("tn.cmd" if os.name == "nt" else "tn")
        tn.write_text("#!/bin/sh\n")
        tn.chmod(0o755)
        os.environ["PATH"] = str(bindir) + os.pathsep + os.environ["PATH"]
        rows = self.tn("doctor", "--json").json
        row = [x for x in rows if x["check"].endswith("on PATH")][0]
        self.assertEqual(row["status"], "ok")


SESS = '''
from tn import Plugin, Session
plugin = Plugin("agents")

@plugin.sessions
def s(ctx):
    return [Session(kind="claude", id="claude-acme-shop-02", name="Acme Shop #T1-02",
                    context="acme/shop@02", dir="/d", started=900.0, attached=False,
                    status="busy", attach=["tmux", "attach-session", "-t", "=claude-acme-shop-02"],
                    extra={"uuid": "0f3e-aaaa"}),
            Session(kind="codex", id="daemon", name="codex daemon", status="running",
                    attach=["codex", "resume", "--all"])]
'''


class Sessions(TnTestCase):
    def setUp(self):
        super().setUp()
        self.write_plugin("agents", SESS)
        self.freeze_time(1000.0 + 3 * 3600)

    def test_list(self):
        r = self.tn("sessions")
        self.assertExit(r, 0)
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0].split(), ["KIND", "ID", "NAME", "CONTEXT", "STATUS", "AGE", "ATTACHED"])
        self.assertIn("claude-acme-shop-02", lines[1])
        self.assertIn("3h", lines[1])
        self.assertTrue(lines[2].startswith("codex"))

    def test_json(self):
        r = self.tn("sessions", "--json")
        rows = r.json
        self.assertEqual(rows[0]["age_seconds"], 3 * 3600 + 100)
        self.assertEqual(rows[0]["extra"], {"uuid": "0f3e-aaaa"})
        self.assertIsNone(rows[1]["age_seconds"])

    def test_attach_by_match(self):
        r = self.tn("sessions", "attach", "shop")
        self.assertExit(r, 0)
        self.assertEqual(r.handoff, ["tmux", "attach-session", "-t", "=claude-acme-shop-02"])
        r = self.tn("sessions", "attach", "0F3E")      # uuid prefix, case-insensitive
        self.assertEqual(r.handoff[0], "tmux")
        r = self.tn("sessions", "attach", "daemon")
        self.assertEqual(r.handoff, ["codex", "resume", "--all"])

    def test_attach_needs_a_choice(self):
        r = self.tn("sessions", "attach", "--json")
        self.assertExit(r, 2)
        r = self.tn("sessions", "attach")
        self.assertExit(r, 2)
        self.assertIn("which session?", r.stderr)
        r = self.tn("sessions", "attach", tty=True, stdin="2\n")
        self.assertEqual(r.handoff, ["codex", "resume", "--all"])
        r = self.tn("sessions", "attach", "zzz")
        self.assertExit(r, 2)

    def test_attach_choices_are_ids_that_attach(self):
        r = self.tn("sessions", "attach", "--json")
        self.assertExit(r, 2)
        self.assertEqual(r.error["choices"], ["claude-acme-shop-02", "daemon"])
        handoffs = []
        for c in r.error["choices"]:
            again = self.tn("sessions", "attach", c)
            self.assertExit(again, 0)
            handoffs.append(again.handoff[0])
        self.assertEqual(handoffs, ["tmux", "codex"])

    def test_empty(self):
        os.environ["TN_PLUGIN_PATH"] = str(self.tmp / "none")
        r = self.tn("sessions")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "")
        self.assertIn("No agent sessions", r.stderr)
        r = self.tn("sessions", "attach")
        self.assertExit(r, 1)


class Plugins(TnTestCase):
    def test_list(self):
        self.write_plugin("demo", D.DEMO)
        self.write_plugin("child", D.NEEDS_BASE)
        r = self.tn("plugins")
        self.assertExit(r, 0)
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0].split(), ["PLUGIN", "GROUPS", "REQUIRES", "FILE", "STATE"])
        demo = [x for x in lines if x.startswith("demo")][0]
        self.assertIn("demo dd", demo)
        self.assertTrue(demo.rstrip().endswith("ok"))
        r = self.tn("plugins", "--json")
        rows = {x["name"]: x for x in r.json}
        self.assertEqual(rows["child"]["state"], "missing requires: base")
        self.assertEqual(rows["demo"]["groups"], ["demo", "dd"])
        self.assertEqual(set(rows["demo"]),
                         {"name", "groups", "requires", "file", "state", "help", "installed"})

    def test_repo(self):
        repo = self.tmp / "dots"
        for b, src in (("widget", 'from tn import Plugin\nplugin = Plugin("widget")\n'),
                       ("demo", D.DEMO.replace('Plugin("demo"', 'Plugin("demo"'))):
            (repo / "bundles" / b).mkdir(parents=True)
            (repo / "bundles" / b / "plugin.py").write_text(src)
        self.write_plugin("demo", D.DEMO)
        r = self.tn("plugins", "--repo", "--json", env={"DOT_REPO": str(repo)})
        self.assertExit(r, 0)
        rows = {x["name"]: x for x in r.json}
        self.assertTrue(rows["demo"]["installed"])
        self.assertFalse(rows["widget"]["installed"])
        self.assertEqual(rows["widget"]["state"], "not applied (dot apply widget)")
        r = self.tn("plugins", "--repo", env={"DOT_REPO": str(self.tmp / "nothing")})
        self.assertExit(r, 3)


class ConfigCmd(TnTestCase):
    def test_get(self):
        self.config('[alpha]\nname = "box"\n[forges.gh]\nhost = "github.com"\n')
        self.assertEqual(self.tn("config", "get", "alpha.name").stdout, "box\n")
        self.assertEqual(self.tn("config", "get", "proj.dirs").stdout,
                         '["src", "bin", "rel", "key", "tmp"]\n')
        self.assertEqual(self.tn("config", "get", "claude.trust").stdout, "true\n")
        r = self.tn("config", "get", "forges")
        self.assertEqual(tomllib.loads(r.stdout), {"gh": {"host": "github.com"}})
        r = self.tn("config", "get", "forges", "--json")
        self.assertEqual(r.json, {"gh": {"host": "github.com"}})
        r = self.tn("config", "get", "nope.x")
        self.assertExit(r, 1)

    def test_get_machine(self):
        self.assertEqual(self.tn("config", "get", "machine").stdout, "T1\n")
        del os.environ["MY_MACHINE"]
        r = self.tn("config", "get", "machine")
        self.assertExit(r, 1)

    def test_set_creates_and_edits(self):
        r = self.tn("config", "set", "alpha.name", "box")
        self.assertExit(r, 0)
        f = self.config_dir / "config.toml"
        self.assertEqual(tomllib.loads(f.read_text()), {"alpha": {"name": "box"}})
        f.write_text('# mine\n[alpha]\nname = "box"   # keep me?\n\n[claude]\ntrust = true\n')
        self.tn("config", "set", "claude.trust", "false")
        self.tn("config", "set", "tunnel_ports", "[1, 2]")
        text = f.read_text()
        self.assertTrue(text.startswith("# mine\ntunnel_ports = [1, 2]\n[alpha]\n"), text)
        d = tomllib.loads(text)
        self.assertEqual(d["claude"]["trust"], False)
        self.assertEqual(d["tunnel_ports"], [1, 2])
        r = self.tn("config", "set", "alpha.dir", "~/x", "--json")
        self.assertEqual(r.json["value"], "~/x")

    def test_set_dry_run(self):
        r = self.tn("-n", "config", "set", "alpha.name", "box")
        self.assertExit(r, 0)
        self.assertIn("would: write", r.stderr)
        self.assertFalse((self.config_dir / "config.toml").exists())

    def test_set_rolls_back_unparsable(self):
        f = self.config("[alpha]\nname = { a = 1 }\n")
        r = self.tn("config", "set", "alpha.name.a", "2")
        self.assertExit(r, 1)
        self.assertEqual(f.read_text(), "[alpha]\nname = { a = 1 }\n")

    def test_set_machine(self):
        le = self.home / ".config" / "dot" / "local.env"
        le.parent.mkdir(parents=True)
        le.write_text("DOT_PROFILE=mac\nMY_MACHINE=OLD\n")
        r = self.tn("config", "set", "machine", "U7")
        self.assertExit(r, 0)
        self.assertEqual(le.read_text(), "DOT_PROFILE=mac\nMY_MACHINE=U7\n")
        self.assertIn("open a new shell", r.stderr)
        self.assertFalse((self.config_dir / "config.toml").exists())
        r = self.tn("config", "set", "machine", "bad name")
        self.assertExit(r, 2)
        le.unlink()
        self.tn("config", "set", "machine", "M2")
        self.assertEqual(le.read_text(), "MY_MACHINE=M2\n")

    def test_project(self):
        pdir = self.root_dir() / "p" / "src" / "r"
        pdir.mkdir(parents=True)
        r = self.tn("config", "set", "forge", "gh", "--project", cwd=pdir)
        self.assertExit(r, 0)
        self.assertEqual(tomllib.loads((self.root_dir() / "p" / "tn.toml").read_text()),
                         {"forge": "gh"})
        self.assertEqual(self.tn("config", "get", "forge", "--project", cwd=pdir).stdout, "gh\n")
        r = self.tn("config", "set", "forge", "gh", "--project", cwd=self.tmp)
        self.assertExit(r, 2)
        r = self.tn("config", "set", "odd", "1", "--project", cwd=pdir)
        self.assertIn("not a project key", r.stderr)

    def test_edit(self):
        script = ("import sys\np = argv[-1]\n"
                  "open(p, 'a').write('\\n[alpha]\\nname = \"edited\"\\n')\n")
        self.fake("myeditor", script=script)
        r = self.tn("config", "edit", env={"EDITOR": "myeditor --wait"})
        self.assertExit(r, 0)
        f = self.config_dir / "config.toml"
        self.assertEqual(tomllib.loads(f.read_text())["alpha"]["name"], "edited")
        self.assertIn("# tn configuration", f.read_text())
        self.assertEqual(self.calls("myeditor")[0][:1], ["--wait"])
        self.fake("myeditor", script="open(argv[-1], 'a').write('bad = = \\n')\n")
        r = self.tn("config", "edit", env={"VISUAL": "myeditor"})
        self.assertExit(r, 1)
        self.assertIn("config.toml", r.stderr)
        self.assertIn("bad = =", f.read_text())      # the edit is kept

    def test_show(self):
        self.conf_d("git", '[forges.gh]\nhost = "github.com"\n')
        r = self.tn("config", "show")
        self.assertExit(r, 0)
        self.assertIn("# sources, in merge order:", r.stdout)
        self.assertIn("built-in defaults", r.stdout)
        self.assertIn("git.toml", r.stdout)
        body = "\n".join(x for x in r.stdout.splitlines() if not x.startswith("#"))
        self.assertEqual(tomllib.loads(body)["forges"]["gh"]["host"], "github.com")
        r = self.tn("config", "show", "--json")
        self.assertEqual(r.json["sources"][0], "built-in defaults")

    def test_no_verb(self):
        self.assertExit(self.tn("config"), 2)


class Shell(TnTestCase):
    def test_scripts(self):
        r = self.tn("shell", "init", "zsh")
        self.assertExit(r, 0)
        self.assertIn('TN_CD_FILE="$__tn_f" TN_SHELL=1 command tn "$@"', r.stdout)
        self.assertIn("compdef _tn tn", r.stdout)
        self.assertIn("__complete $((CURRENT-1)) --", r.stdout)
        r = self.tn("shell", "init", "bash")
        self.assertIn("complete -o default -F _tn tn", r.stdout)
        r = self.tn("shell", "init", "pwsh")
        self.assertIn("Register-ArgumentCompleter -Native -CommandName tn,tn.cmd", r.stdout)
        self.assertIn("function tn {", r.stdout)
        r = self.tn("shell", "init", "fish")
        self.assertExit(r, 2)
        self.assertIn("choices: zsh, bash, pwsh", r.stderr)

    def _shell_ok(self, sh):
        exe = shutil.which(sh, path=os.environ.get("TN_TEST_REAL_PATH", "/bin:/usr/bin"))
        if not exe:
            self.skipTest("%s not available" % sh)
        return exe

    def test_bash_syntax(self):
        exe = self._shell_ok("bash")
        script = self.tn("shell", "init", "bash").stdout
        p = subprocess.run([exe, "-n"], input=script, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_zsh_syntax(self):
        exe = self._shell_ok("zsh")
        script = self.tn("shell", "init", "zsh").stdout
        p = subprocess.run([exe, "-n"], input=script, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_cd_wrapper_end_to_end(self):
        """The bash function really changes directory through TN_CD_FILE."""
        if os.name == "nt":
            self.skipTest("POSIX shells")
        exe = self._shell_ok("bash")
        from tn.testing import BIN_TN, LIB_DIR
        target = self.tmp / "target dir"
        target.mkdir()
        self.write_plugin("demo", D.DEMO)
        wrapper = self.bin / "tn"
        wrapper.write_text("#!/bin/sh\nexec '%s' '%s' \"$@\"\n" % (os.sys.executable, BIN_TN))
        wrapper.chmod(0o755)
        script = self.tn("shell", "init", "bash").stdout
        env = dict(os.environ, PYTHONPATH=str(LIB_DIR),
                   PATH=os.environ["PATH"] + os.pathsep + "/bin:/usr/bin")
        env.pop("TN_CD_FILE", None)
        p = subprocess.run([exe, "--norc", "-c", script + '\ntn demo jump "$1"; rc=$?; pwd; exit $rc',
                            "bash", str(target)], capture_output=True, text=True, env=env,
                           cwd=str(self.home))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(os.path.realpath(p.stdout.strip()), os.path.realpath(str(target)))


class Complete(TnTestCase):
    def setUp(self):
        super().setUp()
        self.write_plugin("demo", D.DEMO)

    def comp(self, *words, cword=None, cwd=None):
        words = ["tn"] + list(words)
        cword = len(words) - 1 if cword is None else cword
        r = self.tn("__complete", str(cword), "--", *words, cwd=cwd)
        self.assertExit(r, 0)
        return r.stdout.splitlines()

    def values(self, lines):
        return [x.split("\t")[0] for x in lines]

    def test_groups_and_builtins(self):
        vals = self.values(self.comp(""))
        for w in ("demo", "dd", "status", "doctor", "config", "shell", "sessions", "plugins"):
            self.assertIn(w, vals)
        self.assertEqual(self.values(self.comp("de")), ["demo"])
        self.assertIn("demo\tdemo commands", self.comp("de"))
        self.assertIn("--json", self.values(self.comp("--j")))

    def test_verbs(self):
        vals = self.values(self.comp("demo", ""))
        for w in ("ls", "show", "remote", "say", "choose"):
            self.assertIn(w, vals)
        self.assertEqual(vals.count("remote"), 1)
        self.assertEqual(self.values(self.comp("demo", "remote", "")), ["add", "ls"])

    def test_named_and_callable_completers(self):
        self.assertEqual(self.comp("demo", "show", "ap"), ["apple\ta fruit", "apricot"])
        self.assertEqual(self.values(self.comp("demo", "show", "--level", "")), ["low", "high"])
        self.assertIn("--loud", self.values(self.comp("demo", "show", "--l")))
        self.assertEqual(self.comp("demo", "show", "x", ""), [])   # only one positional

    def test_choices_and_globals_skipped(self):
        self.assertEqual(self.values(self.comp("-q", "demo", "--json", "err", "m")), ["missing"])
        self.assertEqual(self.comp("-C", ""), ["__tn_dirs__"])

    def test_core_completers(self):
        self.conf_d("git", '[forges.gh]\nhost = "github.com"\n[people.x]\nname = "X"\nemail = "x@e"\n')
        self.assertEqual(self.comp("demo", "remote", "add", ""), ["gh\tgithub.com"])

    def test_builtin_args(self):
        self.assertEqual(self.values(self.comp("shell", "init", "")), ["zsh", "bash", "pwsh"])
        self.assertEqual(self.values(self.comp("config", "")), ["get", "set", "edit", "show"])
        self.assertIn("machine", self.values(self.comp("config", "get", "")))
        self.assertIn("claude.trust", self.values(self.comp("config", "get", "claude.")))
        self.assertEqual(self.values(self.comp("sessions", "attach", "demo-")),
                         ["demo-one", "demo-two"])

    def test_default_command_group(self):
        vals = self.values(self.comp("dd", ""))
        self.assertIn("verb", vals)

    def test_never_fails(self):
        self.assertEqual(self.comp("nosuchgroup", ""), [])
        self.write_plugin("bad", D.BROKEN_IMPORT.replace('"bad"', '"bad"'))
        self.assertEqual(self.comp("bad", ""), [])
        r = self.tn("__complete", "notanumber")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "")
        self.config("broken = = \n")
        self.assertEqual(self.comp("demo", "show", "ap"), ["apple\ta fruit", "apricot"])
