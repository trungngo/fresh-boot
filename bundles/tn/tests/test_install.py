"""How the bundle installs tn: no bytecode in the copied tree, no cwd on sys.path (tn.cmd)."""

import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tn.testing import BIN_TN, LIB_DIR, TnTestCase

BUNDLE = BIN_TN.parent.parent
TN_CMD = BUNDLE / "bin" / "tn.cmd"
BUNDLE_YML = BUNDLE / "bundle.yml"


def _pycache_dirs(root: Path) -> list:
    return sorted(str(p.relative_to(root)) for p in root.rglob("__pycache__"))


class NoBytecodeNextToTheCopy(TnTestCase):
    """dot copies lib/tn as a directory; a __pycache__ Python writes there is drift dot copies
    over on every apply and a leftover `dot remove tn` cannot see."""

    def _install(self) -> Path:
        tn_home = self.tmp / "installed"
        shutil.copytree(LIB_DIR, tn_home / "lib", ignore=shutil.ignore_patterns("__pycache__"))
        return tn_home

    def test_bin_tn_writes_bytecode_to_the_cache(self):
        tn_home = self._install()
        env = {"TN_HOME": str(tn_home), "PYTHONPATH": None, "PYTHONDONTWRITEBYTECODE": None,
               "PYTHONPYCACHEPREFIX": None}
        r = self.tn_proc("--help", env=env)
        self.assertExit(r, 0)
        self.assertEqual(_pycache_dirs(tn_home), [])
        cache = Path(os.environ["XDG_CACHE_HOME"]) / "tn" / "pycache"
        # (Under the prefix the path repeats the source's absolute path.)
        mine = [q for q in cache.rglob("*.pyc") if "installed" in q.parts]
        self.assertTrue(mine, "no tn bytecode under %s" % cache)
        # A second run reads that bytecode and still leaves the install tree alone.
        self.assertExit(self.tn_proc("--version", env=env), 0)
        self.assertEqual(_pycache_dirs(tn_home), [])

    def test_bin_tn_keeps_a_prefix_the_user_set(self):
        tn_home = self._install()
        mine = self.tmp / "my-prefix"
        r = self.tn_proc("--version", env={"TN_HOME": str(tn_home), "PYTHONPATH": None,
                                           "PYTHONDONTWRITEBYTECODE": None,
                                           "PYTHONPYCACHEPREFIX": str(mine)})
        self.assertExit(r, 0)
        self.assertEqual(_pycache_dirs(tn_home), [])
        self.assertTrue(any(mine.rglob("*.pyc")))

    def test_tn_cmd_sets_a_pycache_prefix(self):
        text = TN_CMD.read_text(encoding="utf-8")
        self.assertIn(r'set "PYTHONPYCACHEPREFIX=%USERPROFILE%\.cache\tn\pycache"', text)
        self.assertIn("if not defined PYTHONPYCACHEPREFIX", text)


class TnCmdIgnoresTheCurrentDirectory(TnTestCase):
    """`py -3 -m tn` puts the current directory first on sys.path; tn.cmd passes -P."""

    def test_tn_cmd_passes_dash_p(self):
        runs = [ln.strip() for ln in TN_CMD.read_text(encoding="utf-8").splitlines()
                if ln.strip().startswith("py ")]
        self.assertEqual(runs, ["py -3 -P -m tn %*"])

    def test_dash_p_skips_a_project_tn_module(self):
        project = self.tmp / "project"
        (project / "tn").mkdir(parents=True)
        (project / "tn" / "__init__.py").write_text("raise SystemExit('project tn imported')\n")
        (project / "tn.py").write_text("raise SystemExit('project tn.py imported')\n")
        env = dict(os.environ, PYTHONPATH=str(LIB_DIR))
        p = subprocess.run([sys.executable, "-P", "-m", "tn", "--version"], cwd=str(project),
                           env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("tn ", p.stdout)
        # Without -P the project's package wins: what tn.cmd used to do.
        p = subprocess.run([sys.executable, "-m", "tn", "--version"], cwd=str(project),
                           env=env, capture_output=True, text=True)
        self.assertIn("project tn", p.stderr)


def _steps(text: str) -> list:
    """(label, body) of each step in bundle.yml, in order (stdlib only: no YAML parser)."""
    parts = re.split(r"^  - label: ", text, flags=re.M)[1:]
    return [(p.splitlines()[0].strip(), p) for p in parts]


class BundleDropsSourceBytecode(TnTestCase):
    """The bundle removes lib/tn/**/__pycache__ from the checkout before copying lib/tn."""

    def test_drop_step_comes_before_the_library_copy(self):
        labels = [label for label, _ in _steps(BUNDLE_YML.read_text(encoding="utf-8"))]
        copy = labels.index("Copy the tn library")
        self.assertLess(labels.index("Drop Python bytecode from the tn library source"), copy)
        self.assertLess(labels.index("Drop Python bytecode from the tn library source (Windows)"),
                        copy)

    @unittest.skipIf(os.name == "nt", "the Unix step runs under sh")
    def test_unix_step_removes_pycache_and_then_is_satisfied(self):
        body = dict(_steps(BUNDLE_YML.read_text(encoding="utf-8")))[
            "Drop Python bytecode from the tn library source"]
        cmd = re.search(r"^      cmd: (.*)$", body, re.M).group(1)
        unless = re.search(r"^      unless: (.*)$", body, re.M).group(1)
        src = self.tmp / "bundle"
        for d in ("lib/tn/__pycache__", "lib/tn/plugins/__pycache__"):
            (src / d).mkdir(parents=True)
            (src / d / "x.cpython-311.pyc").write_bytes(b"\0")
        (src / "lib/tn/cli.py").write_text("")

        def sh(c):
            # The test PATH holds only fakes; find and rm come from the system.
            env = dict(os.environ, PATH="/usr/bin:/bin")
            return subprocess.run(["/bin/sh", "-c", c], cwd=str(src), env=env).returncode

        self.assertNotEqual(sh(unless), 0)
        self.assertEqual(sh(cmd), 0)
        self.assertEqual(_pycache_dirs(src), [])
        self.assertTrue((src / "lib/tn/cli.py").is_file())
        self.assertEqual(sh(unless), 0)


if __name__ == "__main__":
    unittest.main()
