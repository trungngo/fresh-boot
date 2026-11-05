import io
import os
import sys
import time
from pathlib import Path

from tn import clock, fs, proc, term
from tn.errors import Fail, Missing, UsageError
from tn.match import match, subsequence
from tn.options import Options, state
from tn.output import fmt_value, home_short, out, table
from tn.testing import TnTestCase


class Captured(TnTestCase):
    """Run a helper with options set and stdio captured (outside tn.cli.main)."""

    def run_with(self, fn, **opts):
        saved = (sys.stdout, sys.stderr, state.options)
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        state.options = Options(**opts)
        try:
            value = fn()
            return value, sys.stdout.getvalue(), sys.stderr.getvalue()
        finally:
            o, e = sys.stdout, sys.stderr
            sys.stdout, sys.stderr, state.options = saved


class Output(Captured):
    def test_table(self):
        self.assertEqual(table([["a", "bb"], ["ccc", "d"]], ["X", "Y"]), "X    Y\na    bb\nccc  d")

    def test_fmt_value(self):
        self.assertEqual(fmt_value(None), "-")
        self.assertEqual(fmt_value(True), "yes")
        self.assertEqual(fmt_value(["a", "b"]), "a,b")
        self.assertEqual(fmt_value([]), "-")
        self.assertEqual(fmt_value(""), "-")

    def test_records_formatter(self):
        rows = [{"repos": ["a", "b"], "age": 7200, "n": None}]
        cols = [("repos", "REPOS", len), ("age", "AGE", clock.fmt_age), ("n", "N")]
        _, so, se = self.run_with(lambda: out.records(rows, cols, empty="none"))
        self.assertEqual(so, "REPOS  AGE  N\n2      2h   -\n")
        _, so, _ = self.run_with(lambda: out.records(rows, cols, empty="none"), json=True)
        self.assertIn('"repos": [', so)

    def test_record_and_result(self):
        obj = {"name": "x", "path": "/p", "n": None}
        _, so, _ = self.run_with(lambda: out.record(obj, [("name", "Name"), ("n", "Count")]))
        self.assertEqual(so, "Name:  x\nCount: -\n")
        _, so, _ = self.run_with(lambda: out.result(obj, lambda o: o["path"]))
        self.assertEqual(so, "/p\n")
        _, so, _ = self.run_with(lambda: out.result(obj))
        self.assertEqual(so, "")
        _, so, _ = self.run_with(lambda: out.result({"p": Path("/x")}), json=True)
        self.assertIn('"p": "%s"' % str(Path("/x")).replace("\\", "\\\\"), so)

    def test_stderr_levels(self):
        def emit():
            out.info("i")
            out.warn("w")
            out.hint("h")
            out.debug("d")
            out.would("x")
        _, _, se = self.run_with(emit)
        self.assertEqual(se, "i\nwarning: w\n  hint: h\nwould: x\n")
        _, _, se = self.run_with(emit, quiet=True)
        self.assertEqual(se, "would: x\n")
        _, _, se = self.run_with(emit, verbose=1)
        self.assertIn("d\n", se)

    def test_colour_only_on_tty(self):
        from tn.output import paint
        _, so, _ = self.run_with(lambda: out.line(paint("x", "red")), color=True)
        self.assertEqual(so, "x\n")
        term._override = {"stdout": True}
        try:
            _, so, _ = self.run_with(lambda: out.line(paint("x", "red")), color=True)
            self.assertIn("\033[31m", so)
            _, so, _ = self.run_with(lambda: out.line(paint("x", "red")), color=True, json=True)
            self.assertEqual(so, "x\n")
        finally:
            term._override = None
        self.assertFalse(term.color_allowed(False))       # NO_COLOR=1 in tests
        del os.environ["NO_COLOR"]
        self.assertTrue(term.color_allowed(False))
        self.assertFalse(term.color_allowed(True))
        os.environ["TERM"] = "dumb"
        self.assertFalse(term.color_allowed(False))

    def test_home_short(self):
        self.assertEqual(home_short(self.home / "a" / "b"), "~" + os.sep + os.path.join("a", "b"))
        self.assertEqual(home_short(self.home), "~")
        self.assertEqual(home_short("/elsewhere"), "/elsewhere")


class Clock(TnTestCase):
    def test_ages(self):
        self.assertEqual([clock.fmt_age(s) for s in (0, 45, 60, 719, 3 * 3600, 2 * 86400 + 5)],
                         ["0s", "45s", "1m", "11m", "3h", "2d"])
        self.assertEqual(clock.fmt_age(None), "-")
        self.assertEqual(clock.fmt_duration(3600 + 12 * 60 + 5), "1h12m")
        self.assertEqual(clock.fmt_duration(45), "45s")

    def test_freeze_and_iso(self):
        self.freeze_time(1790000000.0)
        self.assertEqual(clock.now(), 1790000000.0)
        self.assertEqual(clock.age_seconds(1790000000.0 - 90), 90)
        self.assertEqual(clock.age_seconds(1790000000.0 + 90), 0)
        iso = clock.iso(1790000000.0)
        self.assertTrue(iso.endswith("Z"))
        self.assertEqual(clock.parse_iso(iso), 1790000000.0)
        self.assertIsNone(clock.parse_iso("garbage"))


class Proc(Captured):
    def test_need(self):
        self.fake("widget")
        self.assertTrue(proc.need("widget", "dot apply widget").startswith(str(self.bin)))
        with self.assertRaises(Missing) as cm:
            proc.need("nothing-like-this", "dot apply x")
        self.assertEqual(cm.exception.message, "nothing-like-this is not installed")
        self.assertEqual(cm.exception.fix, "dot apply x")

    def test_capture(self):
        self.fake("tool", stdout="out\n", stderr="err\n", exit=3)
        r = proc.capture(["tool", "a b"], input="in")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (3, "out\n", "err\n"))
        self.assertEqual(self.call_records("tool")[0]["stdin"], "in")
        self.assertEqual(self.calls("tool"), [["a b"]])
        with self.assertRaises(Fail):
            proc.capture(["tool"], check=True)
        r = proc.capture(["nothing-like-this"])
        self.assertEqual(r.returncode, 127)
        with self.assertRaises(Missing):
            proc.capture(["nothing-like-this"], check=True)

    def test_capture_runs_under_dry_run(self):
        self.fake("tool", stdout="x")
        r, _, se = self.run_with(lambda: proc.capture(["tool"]), dry_run=True)
        self.assertEqual(r.stdout, "x")
        self.assertEqual(len(self.calls("tool")), 1)

    def test_capture_timeout(self):
        self.fake("slow", script="import time\ntime.sleep(5)\n")
        r = proc.capture(["slow"], timeout=0.5)
        self.assertEqual(r.returncode, 124)

    def test_run(self):
        self.fake("tool", stdout="to stdout\n", stderr="to stderr\n")
        rc, so, se = self.run_with(lambda: proc.run(["tool", "x"], env={"FOO": "1"}))
        self.assertEqual((rc, so, se), (0, "to stdout\n", "to stderr\n"))
        rc, so, se = self.run_with(lambda: proc.run(["tool"], quiet=True))
        self.assertEqual(so, "")
        self.assertIn("to stdout", se)
        rc, so, se = self.run_with(lambda: proc.run(["tool", "a b"], cwd="/somewhere"),
                                   dry_run=True)
        self.assertEqual(se, "would: run tool 'a b' in /somewhere\n")
        self.assertEqual(len(self.calls("tool")), 2)
        self.fake("tool", exit=2)
        with self.assertRaises(Fail) as cm:
            self.run_with(lambda: proc.run(["tool"]))
        self.assertEqual(cm.exception.message, "tool exited 2")
        rc, _, _ = self.run_with(lambda: proc.run(["tool"], check=False))
        self.assertEqual(rc, 2)

    def test_run_env_and_cwd(self):
        self.fake("tool", script="print(os.environ.get('FOO'), os.getcwd())\n")
        _, so, _ = self.run_with(lambda: proc.run(["tool"], env={"FOO": "bar"}, cwd=self.tmp))
        self.assertEqual(so.split()[0], "bar")
        self.assertEqual(os.path.realpath(so.split()[1]), os.path.realpath(str(self.tmp)))

    def test_argv_must_be_a_list(self):
        with self.assertRaises(TypeError):
            proc.capture("ls -l")

    def test_git(self):
        self.require_git()
        repo = self.make_repo(self.tmp / "r")
        r = proc.git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        self.assertEqual(r.stdout.strip(), "main")
        os.environ["PATH"] = str(self.bin)
        with self.assertRaises(Missing) as cm:
            proc.git(repo, "status")
        self.assertEqual(cm.exception.fix, "dot apply git")

    def test_spawn_detached(self):
        marker = self.tmp / "marker"
        self.fake("bg", script="Path(%r).write_text('ran')\nprint('logged')\n" % str(marker))
        log = self.tmp / "logs" / "bg.log"
        pid, _, se = self.run_with(lambda: proc.spawn_detached(["bg"], log=log), dry_run=True)
        self.assertEqual(pid, 0)
        self.assertIn("would: run bg", se)
        pid = proc.spawn_detached(["bg"], log=log)
        self.assertGreater(pid, 0)
        for _ in range(100):
            if marker.exists() and log.exists() and "logged" in log.read_text():
                break
            time.sleep(0.05)
        self.assertEqual(marker.read_text(), "ran")
        self.assertIn("logged", log.read_text())

    def test_pid_alive(self):
        self.assertTrue(proc.pid_alive(os.getpid()))
        self.assertFalse(proc.pid_alive(0))
        self.assertFalse(proc.pid_alive(None))


class Fs(Captured):
    def test_dry_run_changes_nothing(self):
        f = self.tmp / "d" / "f.txt"

        def all_ops():
            fs.mkdir(self.tmp / "d")
            fs.write_text(f, "x")
            fs.append_text(f, "y")
            fs.replace_line(f, "a=", "a=1")
        _, _, se = self.run_with(all_ops, dry_run=True)
        self.assertFalse((self.tmp / "d").exists())
        self.assertIn("would: mkdir", se)
        self.assertIn("would: write", se)

    def test_ops(self):
        d = self.tmp / "a" / "b"
        self.assertTrue(fs.mkdir(d, mode=0o700))
        self.assertFalse(fs.mkdir(d))
        f = d / "f"
        fs.write_text(f, "one\n", mode=0o600)
        if os.name != "nt":
            self.assertEqual(f.stat().st_mode & 0o777, 0o600)
        fs.write_text(f, "two\n")
        if os.name != "nt":
            self.assertEqual(f.stat().st_mode & 0o777, 0o600)     # mode kept
        fs.append_text(f, "three\n")
        self.assertEqual(f.read_text(), "two\nthree\n")
        self.assertTrue(fs.replace_line(f, "two", "TWO"))
        self.assertFalse(fs.replace_line(f, "TWO", "TWO"))
        self.assertTrue(fs.replace_line(f, "four", "four=4"))
        self.assertEqual(f.read_text(), "TWO\nthree\nfour=4\n")
        self.assertEqual([p.name for p in d.iterdir()], ["f"])       # no temp files left
        self.assertTrue(fs.remove(f))
        self.assertFalse(fs.remove(f))
        (d / "ro").write_text("x")
        os.chmod(d / "ro", 0o400)
        self.assertTrue(fs.rmtree(self.tmp / "a"))
        self.assertFalse((self.tmp / "a").exists())


class Match(TnTestCase):
    def test_tiers(self):
        items = ["claude-hatch", "claude-hat", "other-hat"]
        k = lambda s: [s]  # noqa: E731
        self.assertEqual(match("claude-hat", items, k), ["claude-hat"])
        self.assertEqual(match("CLAUDE", items, k), ["claude-hatch", "claude-hat"])
        self.assertEqual(match("hat", items, k), ["claude-hatch", "claude-hat", "other-hat"])
        self.assertEqual(match("zzz", items, k), [])
        self.assertEqual(match(None, items, k), items)
        self.assertTrue(subsequence("asv", "acme/sv-app"))
        self.assertFalse(subsequence("vsh", "shop"))


class TestingHelpers(TnTestCase):
    def test_environment_is_sandboxed(self):
        import pathlib
        self.assertEqual(pathlib.Path.home(), self.home)
        self.assertEqual(os.environ["MY_MACHINE"], "T1")
        self.assertNotIn("TMUX", os.environ)
        self.assertTrue(os.environ["PATH"].split(os.pathsep)[0] == str(self.bin))
        if os.name != "nt":
            import shutil
            for tool in ("tmux", "fzf", "claude", "brew"):
                self.assertIsNone(shutil.which(tool), tool)

    def test_make_project(self):
        self.require_git()
        p = self.make_project("acme", repos=["shop"], workspaces=["src-02"],
                              remotes={"shop": {"origin": "git@example.com:h/shop.git"}},
                              toml='forge = "gh"\n')
        self.assertTrue((p.repo("shop") / ".git").is_dir())
        self.assertTrue((p.repo("shop", ws="src-02") / ".git").is_dir())
        self.assertEqual(self.git(p.repo("shop"), "remote", "get-url", "origin").strip(),
                         "git@example.com:h/shop.git")
        self.assertEqual(self.git(p.repo("shop"), "log", "--format=%ae").strip(), "test@example.com")
        self.assertTrue((p.dir / "tn.toml").is_file())

    def test_fake_script_state(self):
        self.fake("counter", script=(
            "f = state_dir / 'count'\n"
            "n = int(f.read_text()) + 1 if f.exists() else 1\n"
            "f.write_text(str(n))\nprint(n)\nsys.exit(0 if n < 3 else 9)\n"))
        outs = [proc.capture(["counter"]) for _ in range(3)]
        self.assertEqual([o.stdout.strip() for o in outs], ["1", "2", "3"])
        self.assertEqual(outs[2].returncode, 9)
        self.assertEqual(len(self.calls("counter")), 3)

    def test_use_plugin(self):
        src = self.tmp / "bundles" / "my-thing" / "plugin.py"
        src.parent.mkdir(parents=True)
        src.write_text('from tn import Plugin, out\nplugin = Plugin("my_thing", groups=["mt"])\n'
                       '@plugin.command()\ndef ls(ctx, a):\n    out.line("mine")\n')
        dest = self.use_plugin(src)
        self.assertEqual(dest.name, "my_thing.py")
        self.assertEqual(self.tn("mt", "ls").stdout, "mine\n")
        p = self.load_plugin("my_thing")
        self.assertEqual(p.groups, ["mt"])


class Namespace(TnTestCase):
    def test_plugins_namespace_follows_plugin_path(self):
        import importlib
        import sys as _sys
        self.write_plugin("nsdemo", 'from tn import Plugin\nplugin = Plugin("nsdemo")\nVALUE = 42\n')
        _sys.modules.pop("tn.plugins", None)
        ns = importlib.import_module("tn.plugins")
        self.assertEqual(list(ns.__path__), os.environ["TN_PLUGIN_PATH"].split(os.pathsep))
        from tn.plugins import nsdemo
        self.assertEqual(nsdemo.VALUE, 42)
        # tn itself reuses the already-imported module (mock.patch on it keeps working)
        self.assertIs(self.load_plugin("nsdemo"), nsdemo.plugin)

    def test_result_marks_dry_run(self):
        from tn.output import out as _out
        saved = (sys.stdout, state.options)
        sys.stdout = io.StringIO()
        state.options = Options(json=True, dry_run=True)
        try:
            _out.result({"a": 1})
            text = sys.stdout.getvalue()
        finally:
            sys.stdout, state.options = saved
        self.assertIn('"dry_run": true', text)
