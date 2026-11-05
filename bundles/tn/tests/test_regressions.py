"""Regression tests for reviewed defects: Windows behaviour exercised through its seams (the
PATH search, kernel32 liveness, creation flags, stdio encoding, the pwsh wrapper), the `me`
identity fallback, the cd hint and `tn config set` validation."""

import io
import os
import subprocess
import sys
import tomllib
from unittest import mock

from tn import cli, proc
from tn.builtins import _editor_argv
from tn.config import Config, ConfigError
from tn.context import cd_hint
from tn.options import Options, state
from tn.shell import script
from tn.testing import TnTestCase


class WindowsPathSearch(TnTestCase):
    """tn never runs a git.cmd from the current directory (a cloned repository)."""

    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "evil"
        self.real = self.tmp / "gitbin"
        for d in (self.repo, self.real):
            d.mkdir()
        (self.repo / "git.cmd").write_text("@echo pwned\n")
        (self.real / "git.exe").write_text("")

    def test_skips_cwd_dot_and_relative_entries(self):
        path = os.pathsep.join([".", "evil", str(self.repo), str(self.real)])
        found = proc._search_path("git", path, str(self.repo), ".com;.exe;.bat;.cmd")
        self.assertEqual(found, str(self.real / "git.exe"))

    def test_pathext_and_explicit_extension(self):
        (self.real / "tn.cmd").write_text("")
        pe = ".com;.exe;.bat;.cmd"
        self.assertEqual(proc._search_path("tn", str(self.real), str(self.tmp), pe),
                         str(self.real / "tn.cmd"))
        self.assertEqual(proc._search_path("tn.cmd", str(self.real), str(self.tmp), pe),
                         str(self.real / "tn.cmd"))
        self.assertIsNone(proc._search_path("ssh", str(self.real), str(self.tmp), pe))

    def test_resolve_refuses_a_bare_name_it_cannot_find(self):
        os.chdir(str(self.repo))
        os.environ["PATHEXT"] = ".com;.exe;.bat;.cmd"
        with mock.patch.object(proc, "IS_WINDOWS", True):
            with self.assertRaises(FileNotFoundError):
                proc._resolve(["git", "status"], {"PATH": str(self.repo)})
            self.assertEqual(proc._resolve(["git", "status"], {"PATH": str(self.real)}),
                             [str(self.real / "git.exe"), "status"])


class _FakeKernel32:
    def __init__(self, handle=7, err=0, code=259):
        self.handle, self.err, self.code, self.closed = handle, err, code, []

    def open(self, pid):
        return (self.handle, 0) if self.handle else (0, self.err)

    def exit_code(self, h):
        return self.code

    def close(self, h):
        self.closed.append(h)


class WindowsLiveness(TnTestCase):
    """pid_alive on Windows starts no process (tasklist flashed a console from the watcher)."""

    def test_states(self):
        k = _FakeKernel32()
        self.assertTrue(proc._win_pid_alive(42, k))
        self.assertEqual(k.closed, [7])
        self.assertFalse(proc._win_pid_alive(42, _FakeKernel32(code=0)))
        self.assertFalse(proc._win_pid_alive(42, _FakeKernel32(handle=0, err=87)))
        self.assertTrue(proc._win_pid_alive(42, _FakeKernel32(handle=0, err=5)))

    def test_no_child_process(self):
        with mock.patch.object(proc, "IS_WINDOWS", True), \
                mock.patch.object(proc, "_Kernel32", lambda: _FakeKernel32()), \
                mock.patch.object(proc.subprocess, "run") as run:
            self.assertTrue(proc.pid_alive(1234))
        run.assert_not_called()

    def test_capture_starts_no_window(self):
        seen = {}

        def fake_run(argv, **kw):
            seen.update(kw)
            return subprocess.CompletedProcess(argv, 0, "", "")
        with mock.patch.object(proc, "IS_WINDOWS", True), \
                mock.patch.object(proc, "_resolve", lambda a, e: a), \
                mock.patch.object(proc.subprocess, "run", fake_run):
            proc.capture(["devtunnel", "list"])
        self.assertEqual(seen.get("creationflags"), 0x08000000)


class Utf8Stdio(TnTestCase):
    """A piped stdout in cp1252 printed "ễ ✓ 名" as an internal error."""

    def test_reconfigures_to_utf8(self):
        saved = sys.stdout, sys.stderr
        buf = io.BytesIO()
        sys.stdout = io.TextIOWrapper(buf, encoding="cp1252", errors="strict")
        sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
        try:
            cli.utf8_stdio()
            sys.stdout.write("ễ ✓ 名\n")
            sys.stdout.flush()
            got = buf.getvalue()
        finally:
            sys.stdout, sys.stderr = saved
        self.assertEqual(got.decode("utf-8"), "ễ ✓ 名\n")

    def test_string_streams_are_left_alone(self):
        saved = sys.stdout
        sys.stdout = io.StringIO()
        try:
            cli.utf8_stdio()
        finally:
            sys.stdout = saved


class PwshWrapper(TnTestCase):
    def test_restores_double_dash_and_sets_utf8(self):
        s = script("pwsh")
        self.assertIn("function __tn_args($inv, $a)", s)
        self.assertIn("$tnArgs = __tn_args $MyInvocation $args", s)
        self.assertIn("& $exe @tnArgs", s)
        self.assertIn("[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)", s)
        self.assertEqual(s.count("[Console]::OutputEncoding = $enc"), 2)


class EditorArgv(TnTestCase):
    def test_windows_quoted_path(self):
        self.assertEqual(
            _editor_argv(r'"C:\Program Files\Notepad++\notepad++.exe" -multiInst', True),
            [r"C:\Program Files\Notepad++\notepad++.exe", "-multiInst"])
        self.assertEqual(_editor_argv("notepad", True), ["notepad"])
        self.assertEqual(_editor_argv("code --wait", False), ["code", "--wait"])


class CdHint(TnTestCase):
    def test_pwsh_syntax_on_windows(self):
        h = cd_hint(True)
        self.assertIn("tn shell init pwsh | Out-String | Invoke-Expression", h)
        self.assertIn("$PROFILE", h)
        self.assertNotIn("eval", h)
        self.assertIn('eval "$(tn shell init zsh)"', cd_hint(False))


class MeFromLocalEnv(TnTestCase):
    """MY_NAME / MY_EMAIL persisted by dot in local.env count when the shell did not load them."""

    def test_fallback(self):
        del os.environ["MY_NAME"]
        del os.environ["MY_EMAIL"]
        self.assertIsNone(Config.load().person("me"))
        le = self.home / ".config" / "dot" / "local.env"
        le.parent.mkdir(parents=True)
        le.write_text('MY_MACHINE=T1\nMY_NAME="Local Name"\nMY_EMAIL=local@example.com\n')
        me = Config.load().person("me")
        self.assertEqual((me.name, me.email), ("Local Name", "local@example.com"))
        os.environ["MY_NAME"] = "Env Name"
        self.assertEqual(Config.load().person("me").name, "Env Name")


class ConfigSetValidates(TnTestCase):
    def test_refuses_an_invalid_merged_config(self):
        for key, value in (("roots.x.y", "1"), ("forges.gh.cli", "github")):
            r = self.tn("config", "set", key, value)
            self.assertExit(r, 1)
            self.assertIn("nothing was written", r.stderr)
            self.assertIn("run: tn config edit", r.stderr)
            self.assertFalse((self.config_dir / "config.toml").exists())
        self.assertExit(self.tn("config", "set", "vm.name", "box"), 0)

    def test_still_fixes_a_broken_config(self):
        f = self.config('[roots]\nx = 1\n')
        r = self.tn("config", "set", "vm.name", "box")
        self.assertExit(r, 0)
        r = self.tn("config", "set", "roots.x", "~/x")
        self.assertExit(r, 0)
        self.assertEqual(tomllib.loads(f.read_text())["roots"]["x"], "~/x")

    def test_project_key_checked(self):
        pdir = self.root_dir() / "p" / "src" / "r"
        pdir.mkdir(parents=True)
        r = self.tn("config", "set", "tunnel", "3", "--project", cwd=pdir)
        self.assertExit(r, 1)
        self.assertIn("nothing was written", r.stderr)
        self.assertFalse((self.root_dir() / "p" / "tn.toml").exists())

    def test_load_error_names_the_fix_and_files(self):
        f = self.config('[roots]\nx = 1\n')
        with self.assertRaises(ConfigError) as cm:
            Config.load()
        e = cm.exception
        self.assertEqual(e.fix, "tn config edit")
        self.assertIn("roots.x must be a path string", e.message)
        self.assertIn(f.name, e.hint)
