"""Regression: the codex bundle takes over a machine the official install.sh set up.

The installer leaves ~/.local/bin/codex as a link into ~/.codex/packages/standalone/releases/.
The bundle's github_release step used to refuse it ("exists and was not installed by dot"), so
the first apply of every upgraded machine failed. This runs the real bundle through
test/sandbox.sh (throwaway HOME, fake package managers) against test/fixtures.py, never the
network or the real $HOME. Skipped when no `dot` binary is found ($DOT, else `dot` on PATH).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DOT = os.environ.get("DOT") or shutil.which("dot")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(DOT and os.access(DOT, os.X_OK), "no dot binary (set DOT)")
class MigrateFromInstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = Path(tempfile.mkdtemp(prefix="codex-migrate."))
        self.addCleanup(shutil.rmtree, self.sandbox, True)
        port = _free_port()
        server = subprocess.Popen(
            [sys.executable, str(REPO / "test" / "fixtures.py"), str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(server.wait)
        self.addCleanup(server.kill)
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/go/VERSION", timeout=1).close()
                break
            except OSError:
                time.sleep(0.05)
        else:
            self.fail("fixture server did not start")
        self.env = dict(
            os.environ, DOT=DOT, SANDBOX=str(self.sandbox),
            DOT_GITHUB_API=f"http://127.0.0.1:{port}/gh",
            DOT_URL_REWRITE=f"https://github.com/=http://127.0.0.1:{port}/ghdl/")
        self.env.pop("GITHUB_TOKEN", None)
        # What install.sh leaves behind.
        home = self.sandbox / "home"
        target = home / ".codex/packages/standalone/releases/0.1.0/bin/codex"
        target.parent.mkdir(parents=True)
        target.write_text("#!/bin/sh\necho installer codex\n")
        target.chmod(0o755)
        self.bin = home / ".local/bin"
        self.bin.mkdir(parents=True)
        (self.bin / "codex").symlink_to(target)

    def sb(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(REPO / "test" / "sandbox.sh"), "desk", *args], env=self.env,
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)

    def test_plan_has_no_conflict(self) -> None:
        r = self.sb("plan", "codex")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("[conflict]", r.stdout)
        self.assertIn("remove ~/.local/bin/codex", r.stdout)

    def test_apply_replaces_the_link_without_backup(self) -> None:
        r = self.sb("apply", "--yes", "--plain", "codex")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        codex = self.bin / "codex"
        self.assertFalse(codex.is_symlink(), "installer link still there")
        self.assertTrue(codex.is_file())
        self.assertEqual([p.name for p in self.bin.glob("codex*")], ["codex"])
        # The installer's tree is left for the user to delete.
        self.assertTrue((self.sandbox / "home/.codex/packages").is_dir())
        r = self.sb("apply", "--yes", "--plain", "codex")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(" 0 changed", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
