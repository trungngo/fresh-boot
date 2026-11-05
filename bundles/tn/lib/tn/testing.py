"""Test helpers for tn core and plugins (spec §9.2).

    from tn.testing import TnTestCase

    class ClaudeStart(TnTestCase):
        def test_names_session_after_workspace(self):
            proj = self.make_project("acme", repos=["shop"], workspaces=["src-02"])
            self.fake("tmux", script=TMUX_FAKE)
            r = self.tn("claude", "start", "--json", cwd=proj.repo("shop", ws="src-02"))
            self.assertExit(r, 0)

Everything runs in a temporary directory: HOME, the config, state and cache directories, and a
PATH holding only the fakes plus git and the running Python. Nothing touches the real $HOME.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import clock, term
from .options import state

IS_WINDOWS = os.name == "nt"
LIB_DIR = Path(__file__).resolve().parent.parent          # .../lib (holds the tn package)
BIN_TN = LIB_DIR.parent / "bin" / "tn"                    # bundles/tn/bin/tn in the repo
REPO_BUNDLES = LIB_DIR.parent.parent                       # bundles/ when run from the repo

TEST_NAME = "Test User"
TEST_EMAIL = "test@example.com"

_UNSET = ("TN_CD_FILE", "TN_SHELL", "TN_DEBUG", "TN_PICKER", "TMUX", "TMUX_PANE",
          "SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY", "DISPLAY", "WAYLAND_DISPLAY", "GH_TOKEN",
          "GITHUB_TOKEN", "GITLAB_TOKEN", "VISUAL", "EDITOR", "DOT", "DOT_REPO", "PWD",
          "GIT_DIR", "GIT_WORK_TREE", "PYTHONSTARTUP",
          "TERM")


@dataclass
class Result:
    """What one ``tn`` run produced."""

    code: int
    stdout: str
    stderr: str
    handoff: list | None = None
    handoff_cwd: str | None = None
    cd: str | None = None
    argv: list = field(default_factory=list)

    @property
    def json(self) -> Any:
        """stdout parsed as JSON, or None."""
        try:
            return json.loads(self.stdout) if self.stdout.strip() else None
        except ValueError:
            return None

    @property
    def error(self) -> dict | None:
        """The ``{"code", "message", ...}`` of a --json error line on stderr, or None."""
        for line in reversed(self.stderr.strip().splitlines()):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict) and "error" in obj:
                return obj["error"]
        return None

    def __str__(self) -> str:
        return "tn %s -> exit %s\n--- stdout ---\n%s--- stderr ---\n%s" % (
            " ".join(self.argv), self.code, self.stdout, self.stderr)


@dataclass
class ProjectPaths:
    dir: Path

    def ws(self, name: str = "src") -> Path:
        return self.dir / name

    def repo(self, name: str, ws: str = "src") -> Path:
        return self.dir / ws / name


def _fake_source(name: str, calls: Path, state_dir: Path, stdout: str, stderr: str, code: int,
                 script: str | None) -> str:
    return "\n".join([
        "#!%s" % sys.executable,
        "import json, os, sys",
        "from pathlib import Path",
        "argv = sys.argv[1:]",
        "try:",
        "    stdin = '' if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()",
        "except (OSError, ValueError):",
        "    stdin = ''",
        "log = Path(%r)" % str(calls),
        "state_dir = Path(%r)" % str(state_dir),
        "state_dir.mkdir(parents=True, exist_ok=True)",
        "with open(log, 'a', encoding='utf-8') as _f:",
        "    _f.write(json.dumps({'argv': argv, 'cwd': os.getcwd(), 'stdin': stdin}) + '\\n')",
        "_script = %r" % script,
        "if _script is not None:",
        "    exec(compile(_script, %r, 'exec'), {'argv': argv, 'stdin': stdin, "
        "'state_dir': state_dir, 'log': log, 'sys': sys, 'os': os, 'json': json, 'Path': Path, "
        "'__name__': '__fake__'})" % ("<fake %s>" % name),
        "    sys.exit(0)",
        "sys.stdout.write(%r)" % stdout,
        "sys.stderr.write(%r)" % stderr,
        "sys.exit(%d)" % code,
        "",
    ])


class TnTestCase(unittest.TestCase):
    """A temp HOME and PATH per test; ``self.tn(...)`` runs tn in process."""

    maxDiff = None

    def setUp(self) -> None:
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="tn-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.bin = self.tmp / "bin"
        self.sysbin = self.tmp / "sysbin"
        self.state_dir = self.tmp / "state"
        self.calls_dir = self.tmp / "calls"
        for d in (self.home, self.bin, self.sysbin, self.state_dir, self.calls_dir):
            d.mkdir(parents=True, exist_ok=True)

        saved_env = dict(os.environ)
        saved_cwd = os.getcwd()
        self._stdin_to_devnull()

        def restore() -> None:
            os.environ.clear()
            os.environ.update(saved_env)
            try:
                os.chdir(saved_cwd)
            except OSError:
                pass
        self.addCleanup(restore)
        saved_frozen = clock._frozen
        self.addCleanup(setattr, clock, "_frozen", saved_frozen)

        runner_plugins = os.environ.get("TN_PLUGIN_PATH")
        real_git = shutil.which("git")
        self.git_path = real_git

        env = os.environ
        for k in _UNSET:
            env.pop(k, None)
        for k in list(env):
            if k.startswith("GIT_") or k.startswith("XDG_"):
                env.pop(k, None)
        h = self.home
        env.update({
            "HOME": str(h), "USERPROFILE": str(h),
            "XDG_CONFIG_HOME": str(h / ".config"), "XDG_STATE_HOME": str(h / ".local" / "state"),
            "XDG_CACHE_HOME": str(h / ".cache"), "XDG_DATA_HOME": str(h / ".local" / "share"),
            "TN_HOME": str(self.tmp / "tn-home"), "TN_CONFIG_DIR": str(h / ".config" / "tn"),
            "TN_STATE_DIR": str(h / ".local" / "state" / "tn"),
            "MYPROJECTS_DIR": str(h / "myprojects"),
            "MY_MACHINE": "T1", "MY_NAME": TEST_NAME, "MY_EMAIL": TEST_EMAIL, "NO_COLOR": "1",
            "TN_PICKER": "list", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(h / ".gitconfig"), "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": env.get("LANG", "C.UTF-8") or "C.UTF-8",
        })
        env["PATH"] = os.pathsep.join(self._system_path(real_git))
        if runner_plugins:
            env["TN_PLUGIN_PATH"] = runner_plugins
        else:
            env["TN_PLUGIN_PATH"] = str(self._repo_plugins())
        self.plugin_path = env["TN_PLUGIN_PATH"]
        self._cd_count = 0

    def _stdin_to_devnull(self) -> None:
        """fd 0 is /dev/null for the whole test, so a child that reads stdin (a fake, a tool
        run through ``run``) gets EOF instead of waiting on the runner's terminal or pipe."""
        try:
            saved = os.dup(0)
        except OSError:
            return
        devnull = os.open(os.devnull, os.O_RDONLY)
        os.dup2(devnull, 0)
        os.close(devnull)

        def restore() -> None:
            os.dup2(saved, 0)
            os.close(saved)
        self.addCleanup(restore)

    # -- PATH --------------------------------------------------------------------------------
    def _system_path(self, real_git: str | None) -> list:
        """The fakes' bin, then git and the running Python only. On Unix they are linked into
        a private directory, so nothing else from their directories (tmux, fzf, ...) leaks in."""
        dirs = [str(self.bin)]
        py = Path(sys.executable)
        if IS_WINDOWS:
            for p in (real_git, str(py)):
                if p:
                    d = os.path.dirname(p)
                    if d not in dirs:
                        dirs.append(d)
            sysroot = os.environ.get("SystemRoot")
            if sysroot:
                dirs.append(os.path.join(sysroot, "System32"))
            return dirs
        for name, target in (("git", real_git), ("python3", str(py)), ("python", str(py))):
            if target:
                try:
                    os.symlink(target, self.sysbin / name)
                except OSError:
                    dirs.append(os.path.dirname(target))
        dirs.append(str(self.sysbin))
        return dirs

    def _repo_plugins(self) -> Path:
        """Without the runner's TN_PLUGIN_PATH: a copy of every bundles/*/plugin.py."""
        dest = self.tmp / "plugins"
        dest.mkdir(exist_ok=True)
        if REPO_BUNDLES.is_dir() and (REPO_BUNDLES / "tn").is_dir():
            for b in sorted(REPO_BUNDLES.iterdir()):
                name = b.name.replace("-", "_")
                if (b / "plugin.py").is_file():
                    shutil.copy2(b / "plugin.py", dest / (name + ".py"))
                elif (b / "plugin" / "__init__.py").is_file():
                    shutil.copytree(b / "plugin", dest / name,
                                    ignore=shutil.ignore_patterns("__pycache__"))
        return dest

    # -- fakes -------------------------------------------------------------------------------
    def fake(self, name: str, *, stdout: str = "", stderr: str = "", exit: int = 0,
             script: str | None = None) -> Path:
        """An executable ``name`` on PATH that logs its argv/cwd/stdin to
        ``<tmp>/calls/<name>.jsonl`` and prints the canned output, or runs ``script`` (Python
        with ``argv``, ``stdin``, ``state_dir`` (a Path) and ``log`` (the calls file) in scope).
        """
        calls = self.calls_dir / (name + ".jsonl")
        path = self.bin / name
        path.write_text(_fake_source(name, calls, self.state_dir, stdout, stderr, exit, script),
                        encoding="utf-8")
        os.chmod(path, 0o755)
        if IS_WINDOWS:
            (self.bin / (name + ".cmd")).write_text(
                '@"%s" "%%~dp0%s" %%*\r\n@exit /b %%ERRORLEVEL%%\r\n' % (sys.executable, name),
                encoding="utf-8")
        return path

    def unfake(self, name: str) -> None:
        for p in (self.bin / name, self.bin / (name + ".cmd")):
            if p.exists():
                p.unlink()

    def call_records(self, name: str) -> list:
        f = self.calls_dir / (name + ".jsonl")
        if not f.exists():
            return []
        return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line]

    def calls(self, name: str) -> list:
        """argv lists (without the program) of every call to fake ``name``, in order."""
        return [r["argv"] for r in self.call_records(name)]

    # -- config ------------------------------------------------------------------------------
    @property
    def config_dir(self) -> Path:
        return Path(os.environ["TN_CONFIG_DIR"])

    def config(self, text: str) -> Path:
        p = self.config_dir / "config.toml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def conf_d(self, name: str, text: str) -> Path:
        if not name.endswith(".toml"):
            name += ".toml"
        p = self.config_dir / "conf.d" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def root_dir(self, root: str = "projects") -> Path:
        return Path(os.environ["MYPROJECTS_DIR"])

    def project_toml(self, project: str, text: str, root: str = "projects") -> Path:
        p = self.root_dir(root) / project / "tn.toml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    # -- git projects ------------------------------------------------------------------------
    def require_git(self) -> None:
        if not self.git_path:
            self.skipTest("git is not installed")

    def git(self, repo, *args: str) -> str:
        """Run real git in ``repo`` (with the test identity); returns stdout."""
        self.require_git()
        p = subprocess.run([self.git_path, "-c", "user.name=" + TEST_NAME,
                            "-c", "user.email=" + TEST_EMAIL, "-c", "init.defaultBranch=main",
                            "-c", "commit.gpgsign=false", "-C", str(repo), *args],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                           stdin=subprocess.DEVNULL)
        if p.returncode != 0:
            raise AssertionError("git %s failed: %s" % (" ".join(args), p.stderr))
        return p.stdout

    def make_repo(self, path, remotes: dict | None = None) -> Path:
        """``git init`` plus one commit at ``path``; ``remotes`` maps name -> url."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        self.git(path, "init", "-q")
        (path / "README.md").write_text("# %s\n" % path.name, encoding="utf-8")
        self.git(path, "add", "README.md")
        self.git(path, "commit", "-q", "-m", "initial")
        for name, url in (remotes or {}).items():
            self.git(path, "remote", "add", name, url)
        return path

    def make_project(self, name: str, *, root: str = "projects", repos=(), workspaces=(),
                     remotes: dict | None = None, toml: str | None = None,
                     dirs=("src",)) -> ProjectPaths:
        """``<root>/<name>`` with ``dirs``, each repo (git init + one commit) in ``src`` and in
        every workspace (``src-02``, ...); ``remotes`` maps repo -> {name: url}."""
        pdir = self.root_dir(root) / name
        for d in dirs:
            (pdir / d).mkdir(parents=True, exist_ok=True)
        for ws in ["src"] + list(workspaces):
            (pdir / ws).mkdir(parents=True, exist_ok=True)
            for r in repos:
                self.make_repo(pdir / ws / r, (remotes or {}).get(r))
        if toml is not None:
            (pdir / "tn.toml").write_text(toml, encoding="utf-8")
        return ProjectPaths(pdir)

    # -- plugins -----------------------------------------------------------------------------
    def plugin_dir(self) -> Path:
        """A private plugin directory put first on TN_PLUGIN_PATH (created on first use)."""
        d = self.tmp / "test-plugins"
        if not d.is_dir():
            d.mkdir()
            os.environ["TN_PLUGIN_PATH"] = os.pathsep.join([str(d), os.environ["TN_PLUGIN_PATH"]])
        return d

    def write_plugin(self, name: str, source: str) -> Path:
        """A plugin file ``<name>.py`` from source text, in :meth:`plugin_dir`."""
        p = self.plugin_dir() / (name + ".py")
        p.write_text(source, encoding="utf-8")
        return p

    def use_plugin(self, path, name: str | None = None) -> Path:
        """Copy a plugin file (``bundles/<b>/plugin.py``) or package dir into
        :meth:`plugin_dir` as ``<name>.py`` (default: the bundle directory's name)."""
        src = Path(path)
        if name is None:
            base = src.parent if src.name in ("plugin.py", "plugin") else src
            name = (base.name if base.name != "plugin" else base.parent.name).replace("-", "_")
            if src.name.endswith(".py") and src.name != "plugin.py":
                name = src.stem
        d = self.plugin_dir()
        if src.is_dir():
            dest = d / name
            shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            dest = d / (name + ".py")
            shutil.copy2(src, dest)
        return dest

    def load_plugin(self, name: str):
        """Import installed plugin ``name`` the way tn does; returns its ``Plugin``."""
        from . import loader
        reg = loader.discover()
        loader.setup_namespace(reg)
        return loader.load(reg, name)

    # -- running tn --------------------------------------------------------------------------
    def tn(self, *argv: str, cwd=None, stdin: str | None = None, tty: bool = False,
           env: dict | None = None, handoff_exit: int = 0) -> Result:
        """Run ``tn.cli.main(argv)`` in process with captured stdio (see spec §9.2)."""
        from . import cli
        self._cd_count += 1
        cd_file = self.tmp / ("cd-%d" % self._cd_count)
        cd_file.write_text("", encoding="utf-8")
        cwd = Path(cwd) if cwd is not None else self.home
        extra = {"TN_CD_FILE": str(cd_file)}
        extra.update(env or {})
        saved = {k: os.environ.get(k) for k in list(extra) + ["PWD"]}
        for k, v in extra.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        os.environ["PWD"] = str(cwd)
        old_cwd = os.getcwd()
        os.chdir(str(cwd))
        old_streams = (sys.stdin, sys.stdout, sys.stderr)
        sys.stdin = io.StringIO(stdin or "")
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        old_override = term._override
        term._override = {"stdin": tty, "stderr": tty, "stdout": False}
        handoff: dict = {}

        def hook(args, hcwd, henv):
            handoff["argv"] = list(args)
            handoff["cwd"] = None if hcwd is None else str(hcwd)
            return handoff_exit
        old_hook = state.handoff_hook
        state.handoff_hook = hook
        try:
            try:
                code = cli.main(list(argv))
            except SystemExit as e:  # pragma: no cover - main() catches it
                code = e.code if isinstance(e.code, int) else 1
            stdout, stderr = sys.stdout.getvalue(), sys.stderr.getvalue()
        finally:
            sys.stdin, sys.stdout, sys.stderr = old_streams
            term._override = old_override
            state.handoff_hook = old_hook
            os.chdir(old_cwd)
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        cd = cd_file.read_text(encoding="utf-8") if cd_file.exists() else ""
        return Result(code=code, stdout=stdout, stderr=stderr, handoff=handoff.get("argv"),
                      handoff_cwd=handoff.get("cwd"), cd=cd or None, argv=list(argv))

    def tn_proc(self, *argv: str, cwd=None, stdin: str | None = None, env: dict | None = None,
                python: str | None = None) -> Result:
        """Run ``bundles/tn/bin/tn`` as a subprocess (the entry point and its version gate)."""
        if not BIN_TN.is_file():
            self.skipTest("bundles/tn/bin/tn is not next to this library")
        full = dict(os.environ)
        full["PYTHONPATH"] = str(LIB_DIR)
        cwd = Path(cwd) if cwd is not None else self.home
        full["PWD"] = str(cwd)
        for k, v in (env or {}).items():
            if v is None:
                full.pop(k, None)
            else:
                full[k] = str(v)
        p = subprocess.run([python or sys.executable, str(BIN_TN), *argv], cwd=str(cwd),
                           env=full, input=stdin or "", stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True, encoding="utf-8")
        return Result(code=p.returncode, stdout=p.stdout, stderr=p.stderr, argv=list(argv))

    # -- assertions and time -----------------------------------------------------------------
    def assertExit(self, result: Result, code: int) -> None:
        if result.code != code:
            self.fail("expected exit %d, got %d\n%s" % (code, result.code, result))

    def freeze_time(self, ts: float) -> None:
        """Pin ``tn.clock.now()`` to ``ts`` for the rest of the test."""
        clock._frozen = float(ts)
