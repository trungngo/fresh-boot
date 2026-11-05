"""The Context: where am I (spec §3)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from .config import Config, dot_local_env, dotenv_value
from .errors import Missing, UsageError
from .options import Options, state
from .output import out


def slugify(*parts) -> str:
    """Lowercase, non-empty parts joined with ``-``, every run outside ``[a-z0-9]`` one ``-``,
    no leading or trailing ``-``. Safe as a tmux session name."""
    text = "-".join(str(p) for p in parts if p is not None and str(p) != "")
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def pascal(name: str) -> str:
    """``shop`` -> ``Shop``: split on ``-``, ``_`` and space, first letters capitalised."""
    words = [w for w in re.split(r"[-_ ]+", name or "") if w]
    return " ".join(w[:1].upper() + w[1:] for w in words)


def ws_id_of(ws: str | None) -> str | None:
    """``src`` -> ``00``, ``src-02`` -> ``02``, anything else is literal."""
    if ws is None:
        return None
    if ws == "src":
        return "00"
    if ws.startswith("src-") and len(ws) > 4:
        return ws[4:]
    return ws


def machine_name() -> str | None:
    """``$MY_MACHINE``, else the last ``MY_MACHINE=`` of dot's local.env, else None (§3.4)."""
    v = (os.environ.get("MY_MACHINE") or "").strip()
    if v:
        return v
    v = dotenv_value(dot_local_env(), "MY_MACHINE")
    return v or None


MACHINE_FIX = "tn config set machine <name>"


def require_machine() -> str:
    m = machine_name()
    if not m:
        raise Missing("MY_MACHINE is not set (it names this machine in session names, e.g. U1)",
                      MACHINE_FIX)
    return m


def _is_under(path: str, root: str) -> bool:
    if os.name == "nt":
        path, root = os.path.normcase(path), os.path.normcase(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def locate(cwd: Path, roots: dict) -> tuple:
    """(root_key, root, parts below the root) for the longest matching root, or (None, None, []).

    Symlinks are not resolved: the logical path is tried first; if nothing matches, the
    resolved path against the resolved roots (macOS' /var -> /private/var and the like).
    """
    def best(path: str, rootmap: dict):
        found = None
        for key, r in rootmap.items():
            if _is_under(path, r) and (found is None or len(r) > len(found[1])):
                found = (key, r)
        return found

    logical = {k: os.path.normpath(str(v)) for k, v in roots.items()}
    path = os.path.normpath(str(cwd))
    hit = best(path, logical)
    if hit is None:
        try:
            real = {k: os.path.realpath(v) for k, v in logical.items()}
            rpath = os.path.realpath(path)
        except OSError:
            real, rpath = {}, path
        hit = best(rpath, real)
        if hit is not None:
            key, r = hit
            rel = rpath[len(r):].strip(os.sep)
            return key, Path(logical[key]), [p for p in rel.split(os.sep) if p]
        return None, None, []
    key, r = hit
    rel = path[len(r):].strip(os.sep)
    return key, Path(r), [p for p in rel.split(os.sep) if p]


def logical_cwd() -> Path:
    """The cwd as the shell sees it: ``$PWD`` when it names the same directory, else getcwd()."""
    real = os.getcwd()
    pwd = os.environ.get("PWD")
    if pwd and os.path.isabs(pwd):
        try:
            if os.path.samefile(pwd, real):
                return Path(os.path.normpath(pwd))
        except OSError:
            pass
    return Path(real)


@dataclass(frozen=True)
class Context:
    """Where tn runs: filled once by core before any command (spec §3.2)."""

    cwd: Path
    kind: str | None = None
    root_key: str | None = None
    root: Path | None = None
    project: str | None = None
    ws: str | None = None
    ws_id: str | None = None
    repo: str | None = None
    project_dir: Path | None = None
    ws_dir: Path | None = None
    repo_dir: Path | None = None
    path: Path = field(default=None)  # type: ignore[assignment]
    options: Options = field(default_factory=Options)
    config: Config = field(default=None, repr=False)  # type: ignore[assignment]

    # -- building ----------------------------------------------------------------------------
    @classmethod
    def build(cls, cwd: Path, options: Options, config: Config, *, lenient: bool = False
              ) -> "Context":
        """The Context for ``cwd``; ``config`` is the global config (the project's tn.toml is
        merged in here)."""
        cwd = Path(os.path.normpath(os.path.abspath(str(cwd))))
        key, root, parts = locate(cwd, config.roots)
        project = ws = repo = None
        project_dir = ws_dir = repo_dir = None
        if root is not None:
            if len(parts) >= 1:
                project, project_dir = parts[0], root / parts[0]
            if len(parts) >= 2:
                ws, ws_dir = parts[1], project_dir / parts[1]
            if len(parts) >= 3:
                repo, repo_dir = parts[2], ws_dir / parts[2]
        kind = None if root is None else "projects"
        path = repo_dir or ws_dir or project_dir or cwd
        cfg = config.with_project(project, project_dir, lenient=lenient)
        return cls(cwd=cwd, kind=kind, root_key=key, root=root, project=project, ws=ws,
                   ws_id=ws_id_of(ws), repo=repo, project_dir=project_dir, ws_dir=ws_dir,
                   repo_dir=repo_dir, path=path, options=options,
                   config=cfg)

    def for_path(self, path) -> "Context":
        """The Context of another directory, with the same options and config sources."""
        return Context.build(Path(os.path.expanduser(str(path))), self.options, self.config,
                             lenient=False)

    # -- lazy --------------------------------------------------------------------------------
    @cached_property
    def git_root(self) -> Path | None:
        """The nearest ancestor of cwd holding ``.git`` (a directory or a file); no subprocess."""
        p = self.cwd
        while True:
            if (p / ".git").exists():
                return p
            if p.parent == p:
                return None
            p = p.parent

    @cached_property
    def machine(self) -> str | None:
        return machine_name()

    # -- predicates --------------------------------------------------------------------------
    @property
    def in_project(self) -> bool:
        return self.project is not None

    def require(self, level: str = "project") -> "Context":
        """This Context, or the §3.5 usage error when it lacks ``level`` (project, ws, repo)."""
        if level not in ("project", "ws", "repo"):
            raise ValueError("level must be project, ws or repo")
        have = {"project": self.project, "ws": self.ws, "repo": self.repo}[level]
        if have is None:
            roots = self.config.roots if self.config else {}
            p = roots.get("projects")
            where = []
            if p:
                where.append(_tilde(p) + "/<project>/...")
            what = {"project": "a project", "ws": "a workspace", "repo": "a repo"}[level]
            if self.project is None:
                raise UsageError("not inside a project (expected %s); pass a target"
                                 % " or ".join(where))
            raise UsageError("not inside %s of %s; pass a target" % (what, self.project))
        return self

    # -- names (§3.3) ------------------------------------------------------------------------
    @property
    def short_repo(self) -> str | None:
        """``repo`` without a leading ``<project>-``; empty when repo == project."""
        if self.repo is None:
            return None
        if self.repo == self.project:
            return ""
        if self.project and self.repo.startswith(self.project + "-"):
            return self.repo[len(self.project) + 1:]
        return self.repo

    @property
    def name(self) -> str | None:
        """``acme/shop@02``; None outside the roots (and at a root itself)."""
        if self.project is None:
            return None
        s = self.project
        if self.repo:
            s += "/" + self.repo
        if self.ws is not None and self.ws != "src":
            s += "@" + str(self.ws_id)
        return s

    @property
    def slug(self) -> str:
        if self.project is None:
            return slugify(self.cwd.name) or "root"
        if self.ws is None:
            return slugify(self.project)
        return slugify(self.project, self.short_repo, self.ws_id)

    def session(self, kind: str) -> str:
        """``<kind>-<slug>``: ``claude-acme-shop-02``."""
        return "%s-%s" % (kind, self.slug)

    def tunnel_label(self, port) -> str:
        if self.project is None:
            return slugify(self.cwd.name, port)
        return slugify(self.project, self.short_repo,
                       None if self.ws in (None, "src") else self.ws_id, port)

    def label(self) -> str:
        """``Acme Shop #U1-02``. Needs the machine name (exit 3 without it)."""
        m = self.machine
        if not m:
            require_machine()
        if self.project is None:
            return "%s #%s" % (pascal(self.cwd.name), m)
        if not self.repo:
            return "%s #%s" % (pascal(self.project), m)
        words = " ".join(p for p in (pascal(self.project), pascal(self.short_repo or "")) if p)
        return "%s #%s-%s" % (words, m, self.ws_id)

    def to_json(self) -> dict:
        return {
            "kind": self.kind,
            "root": str(self.root) if self.root else None,
            "project": self.project, "ws": self.ws, "ws_id": self.ws_id, "repo": self.repo,
            "path": str(self.path), "name": self.name, "slug": self.slug,
            "git_root": str(self.git_root) if self.git_root else None,
            "machine": self.machine,
        }

    # -- cd (§6.7) ---------------------------------------------------------------------------
    def request_cd(self, path) -> None:
        """Ask the shell function to change directory; without it, print the path and a hint."""
        p = os.path.abspath(str(path))
        if state.options.dry_run:
            out.would("cd %s" % p)
            return
        f = os.environ.get("TN_CD_FILE")
        if f:
            try:
                with open(f, "w", encoding="utf-8", newline="") as fh:
                    fh.write(p)
                return
            except OSError:
                pass
        out.line(p)
        out.hint(cd_hint(os.name == "nt"))


def cd_hint(windows: bool) -> str:
    """What to add so tn can change directory: pwsh syntax in $PROFILE on Windows."""
    from .shell import init_fix
    return ("tn cannot change your shell's directory without its shell function; add %s%s"
            % (init_fix(windows), " to $PROFILE" if windows else ""))


def _tilde(p) -> str:
    s = str(p)
    home = str(Path.home())
    if s == home:
        return "~"
    if s.startswith(home + os.sep):
        return "~" + s[len(home):]
    return s
