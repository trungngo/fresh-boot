"""Shared fixtures for the git plugin tests (bundles/git/tests)."""

from __future__ import annotations

import os
from pathlib import Path

from tn.testing import TEST_EMAIL, TEST_NAME, TnTestCase  # noqa: F401 - re-exported

BUNDLE = Path(__file__).resolve().parent.parent

FORGES = """
[forges.gh]
host  = "github.com"
cli   = "gh"
owner = "alex"
remote = "github"

[forges.work]
host   = "gitlab.example.com"
cli    = "glab"
remote = "gitlab"

[forges.bitbucket]
host  = "bitbucket.org"
cli   = "none"
path  = "alex/{project}-{repo}"
"""

PEOPLE = """
[people.jane_roe]
name  = "Jane Roe"
email = "jane.roe@example.com"

[people.bobsmith]
name  = "Bob Smith"
email = "bobsmith@example.com"

[people.carolw]
name  = "Carol White"
email = "carolw@example.com"

[people.alex-work]
name  = "Alex Work"
email = "alex@example.com"
aliases = ["alex"]

[people.dan_brown]
name  = "Dan Brown"
email = "dan.brown@example.com"
"""

# A stateless gh: `gh api gitignore/templates[/<Name>]`, `gh auth status`.
GH_FAKE = r'''
templates = {"Python": "__pycache__/\n*.py[cod]\n", "Node": "node_modules/\n", "Go": "*.test\n",
             "C++": "*.o\n"}
if os.environ.get("FAKE_GH_401"):
    sys.stderr.write("HTTP 401: Bad credentials (https://api.github.com/gitignore/templates)\n")
    sys.exit(1)
if argv[:2] == ["api", "gitignore/templates"]:
    print(json.dumps(sorted(templates)))
elif argv[:1] == ["api"] and argv[1].startswith("gitignore/templates/"):
    name = argv[1].split("/", 2)[2]
    if name not in templates:
        sys.stderr.write("HTTP 404: Not Found\n")
        sys.exit(1)
    print(json.dumps({"name": name, "source": templates[name]}))
elif argv[:2] == ["auth", "status"]:
    sys.exit(int(os.environ.get("FAKE_GH_AUTH", "0")))
else:
    sys.exit(2)
'''


class GitCase(TnTestCase):
    """TnTestCase plus forges and people in conf.d, bare remotes and commit helpers."""

    def setUp(self) -> None:
        super().setUp()
        self.require_git()
        self.conf_d("git-forges", FORGES)
        self.conf_d("git-people", PEOPLE)
        self.projects = Path(os.environ["MYPROJECTS_DIR"])
        self.remotes = self.tmp / "remotes"
        self.remotes.mkdir()

    def bare(self, name: str) -> Path:
        path = self.remotes / (name + ".git")
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", str(path))
        return path

    def published(self, repo: Path, name: str | None = None, remote: str = "origin",
                  track: bool = True) -> Path:
        """Give ``repo`` a bare remote and push main to it (tracked unless ``track=False``)."""
        bare = self.bare(name or repo.name)
        self.git(repo, "remote", "add", remote, str(bare))
        self.git(repo, "push", "-q", *(["-u"] if track else []), remote, "main")
        return bare

    def other_clone(self, bare: Path, name: str = "other") -> Path:
        dest = self.tmp / name
        self.git(self.tmp, "clone", "-q", str(bare), str(dest))
        return dest

    def commit(self, repo: Path, name: str = "file.txt", text: str = "x\n",
               msg: str | None = None) -> str:
        (Path(repo) / name).write_text(text, encoding="utf-8")
        self.git(repo, "add", name)
        self.git(repo, "commit", "-q", "-m", msg or ("change " + name))
        return self.git(repo, "rev-parse", "HEAD").strip()

    def head(self, repo: Path, ref: str = "HEAD") -> str:
        return self.git(repo, "rev-parse", ref).strip()

    def local_config(self, repo: Path, key: str) -> str:
        return self.git(repo, "config", "--local", "--get", key).strip()

    def ok(self, r, code: int = 0):
        self.assertExit(r, code)
        return r

    def repo(self, name: str = "app", project: str = "acme", **kw) -> Path:
        return self.make_project(project, repos=[name], **kw).repo(name)
