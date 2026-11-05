"""Shared fixtures for the projects plugin tests (bundles/projects/tests)."""

from __future__ import annotations

import os
from pathlib import Path

from tn.testing import TEST_EMAIL, TEST_NAME, TnTestCase  # noqa: F401 - re-exported

FORGES = """
[forges.gh]
host  = "github.com"
cli   = "gh"
owner = "alex"

[forges.work]
host   = "gitlab.example.com"
cli    = "glab"
remote = "gitlab"

[forges.bb]
host  = "bitbucket.org"
cli   = "none"
path  = "alex/{project}-{repo}"

[people.alex-work]
name  = "Alex Work"
email = "alex@example.com"
aliases = ["alex"]
"""


class ProjectsCase(TnTestCase):
    """TnTestCase plus forges/people in conf.d and helpers for remotes."""

    def setUp(self) -> None:
        super().setUp()
        self.require_git()
        self.conf_d("git", FORGES)
        self.projects = Path(os.environ["MYPROJECTS_DIR"])
        self.remotes = self.tmp / "remotes"
        self.remotes.mkdir()

    def bare(self, name: str) -> Path:
        """An empty bare repository under <tmp>/remotes (a stand-in for a forge)."""
        path = self.remotes / (name + ".git")
        self.git(self.tmp, "init", "-q", "--bare", str(path))
        return path

    def published(self, repo: Path, name: str | None = None, remote: str = "origin") -> Path:
        """Give ``repo`` a bare remote, push main to it and track it."""
        bare = self.bare(name or repo.name)
        self.git(repo, "remote", "add", remote, str(bare))
        self.git(repo, "push", "-q", "-u", remote, "main")
        return bare

    def commit(self, repo: Path, name: str = "file.txt", text: str = "x\n") -> None:
        (Path(repo) / name).write_text(text, encoding="utf-8")
        self.git(repo, "add", name)
        self.git(repo, "commit", "-q", "-m", "change " + name)

    def local_config(self, repo: Path, key: str) -> str:
        return self.git(repo, "config", "--local", "--get", key).strip()

    def ok(self, r, code: int = 0):
        self.assertExit(r, code)
        return r
