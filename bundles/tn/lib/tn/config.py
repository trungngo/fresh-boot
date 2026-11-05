"""Configuration (spec §4): built-in defaults, ``conf.d/*.toml``, ``config.toml``, and the
project's ``tn.toml``, merged table by table."""

from __future__ import annotations

import copy
import os
import re
import string
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import Fail, UsageError

# -- locations -------------------------------------------------------------------------------


def tn_home() -> Path:
    v = os.environ.get("TN_HOME")
    return Path(v) if v else Path.home() / ".local" / "share" / "tn"


def config_dir() -> Path:
    v = os.environ.get("TN_CONFIG_DIR")
    return Path(v) if v else Path.home() / ".config" / "tn"


def state_dir() -> Path:
    v = os.environ.get("TN_STATE_DIR")
    if v:
        return Path(v)
    x = os.environ.get("XDG_STATE_HOME")
    return Path(x) / "tn" if x else Path.home() / ".local" / "state" / "tn"


def cache_dir() -> Path:
    x = os.environ.get("XDG_CACHE_HOME")
    return Path(x) / "tn" if x else Path.home() / ".cache" / "tn"


def dot_local_env() -> Path:
    """``~/.config/dot/local.env`` (``$XDG_CONFIG_HOME/dot`` when set, as dot does)."""
    x = os.environ.get("XDG_CONFIG_HOME")
    base = Path(x) if x else Path.home() / ".config"
    return base / "dot" / "local.env"


def dotenv_value(path: Path, key: str) -> str | None:
    """The last ``KEY=value`` line of a dotenv file (optional ``export ``, quotes stripped)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    found = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("export "):
            s = s[len("export "):].lstrip()
        if not s.startswith(key + "="):
            continue
        v = s[len(key) + 1:].strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        found = v.strip()
    return found


def _home(p: Path) -> str:
    """``~/...`` for a path under the home directory (error text)."""
    s, home = str(p), str(Path.home())
    if home and s.startswith(home.rstrip(os.sep) + os.sep):
        return "~" + os.sep + s[len(home.rstrip(os.sep)) + 1:]
    return s


def expand_path(value: str) -> Path:
    """``~`` and ``$VAR`` expanded, made absolute and normalised; symlinks are NOT resolved."""
    p = os.path.expandvars(os.path.expanduser(str(value)))
    return Path(os.path.normpath(os.path.abspath(p)))


# -- errors ----------------------------------------------------------------------------------


class ConfigError(Fail):
    """An unreadable or invalid config file: exit 1, naming the file (and line)."""

    def __init__(self, message: str, file: Path | None = None, *, fix: str | None = None,
                 hint: str | None = None) -> None:
        super().__init__("%s: %s" % (file, message) if file else message, hint=hint, fix=fix)
        self.file = file
        self.detail = message


# -- data types ------------------------------------------------------------------------------

PLACEHOLDERS = {"host", "path", "project", "repo", "group", "owner"}
_TEMPLATE_KEYS = ("path", "ssh_url", "https_url", "web")


def _placeholders(template: str) -> set[str]:
    names = set()
    for _, name, spec, conv in string.Formatter().parse(template):
        if name is not None:
            names.add(name)
    return names


def render(template: str, **values: Any) -> str:
    """Fill ``{host}``, ``{path}``, ``{project}``, ``{repo}``, ``{group}``, ``{owner}``."""
    unknown = _placeholders(template) - PLACEHOLDERS
    if unknown:
        raise ConfigError("unknown placeholder {%s} in %r" % (sorted(unknown)[0], template))
    missing = [n for n in _placeholders(template) if values.get(n) in (None, "")]
    if missing:
        raise UsageError("%r needs {%s}, which is not known here" % (template, missing[0]))
    return template.format(**{k: ("" if v is None else v) for k, v in values.items()})


@dataclass(frozen=True)
class Forge:
    key: str
    host: str
    cli: str = "none"
    kind: str = "gitlab"
    owner: str | None = None
    remote: str = ""
    path: str = "{group}/{repo}"
    ssh_url: str = "git@{host}:{path}.git"
    https_url: str = "https://{host}/{path}.git"
    clone: str = "ssh"
    web: str = "https://{host}"

    def repo_path(self, *, project: str | None = None, repo: str | None = None,
                  group: str | None = None) -> str:
        """The ``path`` template filled in: ``{group}`` defaults to the owner, else the project."""
        g = group or self.owner or project
        return render(self.path, host=self.host, project=project, repo=repo, group=g,
                      owner=self.owner)

    def ssh(self, path: str) -> str:
        return render(self.ssh_url, host=self.host, path=path, owner=self.owner)

    def https(self, path: str) -> str:
        return render(self.https_url, host=self.host, path=path, owner=self.owner)

    def url(self, path: str) -> str:
        """The remote URL tn uses: https when ``clone = "https"``, else ssh."""
        return self.https(path) if self.clone == "https" else self.ssh(path)

    def web_url(self, path: str | None = None) -> str:
        base = render(self.web, host=self.host, owner=self.owner).rstrip("/")
        return base + "/" + path.strip("/") if path else base


@dataclass(frozen=True)
class Person:
    key: str
    name: str
    email: str
    aliases: tuple = ()

    def to_json(self) -> dict:
        return {"key": self.key, "name": self.name, "email": self.email,
                "aliases": list(self.aliases)}


PROJECT_KEYS = {"forge", "group", "identity", "tunnel"}


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    dir: Path
    file: Path
    exists: bool
    forge: str | None
    group: str
    identity: str | None
    tunnel_ports: list = field(default_factory=list)  # list[int]
    raw: dict = field(default_factory=dict)
    unknown_keys: list = field(default_factory=list)


def split_url(url: str) -> tuple[str | None, str | None]:
    """(host, path) of a git remote URL: ``https://h/p.git``, ``ssh://git@h:22/p``, ``git@h:p``.
    The path has no leading ``/`` and no ``.git``."""
    url = (url or "").strip()
    m = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://(?:[^@/]*@)?([^/:]+)(?::\d*)?(?:/(.*))?$", url)
    if not m:
        m = re.match(r"^(?:[^@/:]+@)?([^/:]{2,}):(?!//)(.+)$", url)
    if not m:
        return None, None
    host = m.group(1).lower()
    path = (m.group(2) or "").strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return host, path or None


# -- the config ------------------------------------------------------------------------------


def _merge(base: dict, over: dict) -> dict:
    """Tables merge key by key, recursively; scalars and arrays are replaced whole."""
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def defaults() -> dict:
    """Built-in defaults (spec §4.2, minus what bundles ship: forges, people)."""
    return {
        "roots": {
            "projects": os.environ.get("MYPROJECTS_DIR") or "~/myprojects",
        },
        "proj": {"dirs": ["src", "bin", "rel", "key", "tmp"]},
        "claude": {"trust": True},
    }


def read_toml(path: Path) -> dict:
    """One file through tomllib; ``ConfigError`` names the file and tomllib's line."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(str(e), path)
    except OSError as e:
        raise ConfigError("cannot read: %s" % (e.strerror or e), path)


def _secretish(key: str) -> bool:
    k = key.lower()
    return "token" in k or "password" in k or "secret" in k or k.endswith("_key")


def _secret_keys(data: Any, prefix: str = "") -> list[str]:
    found = []
    if isinstance(data, dict):
        for k, v in data.items():
            name = prefix + k
            if _secretish(k):
                found.append(name)
            found.extend(_secret_keys(v, name + "."))
    return found


@dataclass
class Issue:
    """A config problem kept (instead of raised) when loading leniently, for ``tn doctor``."""
    file: Path | None
    message: str
    level: str = "fail"      # "fail" | "warn"


class Config:
    """The merged configuration. See spec §4.5 for the access API."""

    def __init__(self, data: dict, sources: list[Path], *, issues: list[Issue] | None = None,
                 project: ProjectConfig | None = None, base: "Config | None" = None) -> None:
        self.data = data
        self.sources = list(sources)
        self.issues: list[Issue] = list(issues or [])
        self._project = project
        self._base = base

    # -- loading -----------------------------------------------------------------------------
    @staticmethod
    def files() -> list[Path]:
        """The files ``load`` merges, in order: ``conf.d/*.toml`` (lexical), ``config.toml``."""
        cdir = config_dir()
        files: list[Path] = []
        confd = cdir / "conf.d"
        if confd.is_dir():
            files.extend(sorted((p for p in confd.iterdir()
                                 if p.suffix == ".toml" and p.is_file()), key=lambda p: p.name))
        user = cdir / "config.toml"
        if user.is_file():
            files.append(user)
        return files

    @classmethod
    def problems_with(cls, replaced: Path, layer: dict) -> list[str]:
        """What validation says of the merged config when ``replaced`` holds ``layer``
        (``tn config set`` asks before writing). Unreadable other files are skipped."""
        data = defaults()
        files = cls.files()
        if replaced not in files:
            files.append(replaced)
        for f in files:
            if f == replaced:
                data = _merge(data, layer)
                continue
            try:
                data = _merge(data, read_toml(f))
            except ConfigError:
                continue
        return cls(data, [])._validate()

    @classmethod
    def load(cls, *, lenient: bool = False) -> "Config":
        """Defaults, then ``conf.d/*.toml`` (lexical order), then ``config.toml``."""
        files = cls.files()
        data = defaults()
        sources: list[Path] = []
        issues: list[Issue] = []
        for f in files:
            try:
                layer = read_toml(f)
            except ConfigError as e:
                if not lenient:
                    raise
                issues.append(Issue(f, e.detail))
                continue
            for k in _secret_keys(layer):
                issues.append(Issue(f, "key %s looks like a secret; secrets never go in tn "
                                       "config (they come from dot's secrets.yml)" % k, "warn"))
            data = _merge(data, layer)
            sources.append(f)
        cfg = cls(data, sources, issues=issues)
        for problem in cfg._validate():
            if not lenient:
                where = ", ".join(_home(f) for f in sources) or "built-in defaults"
                raise ConfigError("config: " + problem, fix="tn config edit",
                                  hint="in the config merged from %s" % where)
            cfg.issues.append(Issue(None, problem))
        return cfg

    def with_project(self, name: str | None, project_dir: Path | None, *,
                     lenient: bool = False) -> "Config":
        """This config plus the project's ``tn.toml`` (only the §4.4 keys are read)."""
        base = self._base or self
        if not name or project_dir is None:
            return Config(base.data, base.sources, issues=base.issues, base=base)
        f = Path(project_dir) / "tn.toml"
        raw: dict = {}
        issues = list(base.issues)
        sources = list(base.sources)
        exists = f.is_file()
        if exists:
            try:
                raw = read_toml(f)
                sources.append(f)
            except ConfigError as e:
                if not lenient:
                    raise
                issues.append(Issue(f, e.detail))
        try:
            project = _project_config(name, Path(project_dir), f, exists, raw)
        except ConfigError as e:
            if not lenient:
                raise
            issues.append(Issue(f, e.detail))
            project = _project_config(name, Path(project_dir), f, exists, {})
        for k in project.unknown_keys:
            issues.append(Issue(f, "unknown project key %r (read: %s)"
                                % (k, ", ".join(sorted(PROJECT_KEYS))), "warn"))
        for k in _secret_keys(raw):
            issues.append(Issue(f, "key %s looks like a secret; secrets never go in tn config" % k,
                                "warn"))
        return Config(base.data, sources, issues=issues, project=project, base=base)

    def _validate(self) -> list[str]:
        problems = []
        roots = self.data.get("roots")
        if not isinstance(roots, dict):
            problems.append("[roots] must be a table")
        else:
            for k, v in roots.items():
                if not isinstance(v, str) or not v:
                    problems.append("roots.%s must be a path string" % k)
        forges = self.data.get("forges", {})
        if not isinstance(forges, dict):
            problems.append("[forges] must be a table")
        else:
            for k in forges:
                try:
                    self._make_forge(k)
                except ConfigError as e:
                    problems.append(e.detail)
        people = self.data.get("people", {})
        if not isinstance(people, dict):
            problems.append("[people] must be a table")
        else:
            for k, v in people.items():
                if not isinstance(v, dict) or not isinstance(v.get("name"), str) \
                        or not isinstance(v.get("email"), str):
                    problems.append("people.%s needs name and email" % k)
        return problems

    # -- generic access ----------------------------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        """Dotted lookup in the merged config; ``default`` (None) when absent."""
        cur: Any = self.data
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    @property
    def roots(self) -> dict:
        """dict[str, Path]: root key -> expanded directory."""
        roots = self.data.get("roots") or {}
        return {k: expand_path(v) for k, v in roots.items() if isinstance(v, str) and v}

    # -- forges ------------------------------------------------------------------------------
    def _make_forge(self, key: str) -> Forge:
        raw = (self.data.get("forges") or {}).get(key)
        if not isinstance(raw, dict):
            raise ConfigError("forges.%s must be a table" % key)
        host = raw.get("host")
        if not isinstance(host, str) or not host:
            raise ConfigError("forges.%s needs a host" % key)
        cli = raw.get("cli", "none")
        if cli not in ("gh", "glab", "none"):
            raise ConfigError("forges.%s.cli must be gh, glab or none" % key)
        kind = raw.get("kind")
        if kind is None:
            if cli == "gh":
                kind = "github"
            elif cli == "glab":
                kind = "gitlab"
            elif "github" in host:
                kind = "github"
            elif "bitbucket" in host:
                kind = "bitbucket"
            else:
                kind = "gitlab"
        if kind not in ("github", "gitlab", "bitbucket"):
            raise ConfigError("forges.%s.kind must be github, gitlab or bitbucket" % key)
        clone = raw.get("clone", "cli" if cli != "none" else "ssh")
        if clone not in ("cli", "ssh", "https"):
            raise ConfigError("forges.%s.clone must be cli, ssh or https" % key)
        values = {}
        for name in _TEMPLATE_KEYS:
            if name in raw:
                v = raw[name]
                if not isinstance(v, str):
                    raise ConfigError("forges.%s.%s must be a string" % (key, name))
                bad = _placeholders(v) - PLACEHOLDERS
                if bad:
                    raise ConfigError("forges.%s.%s: unknown placeholder {%s}"
                                      % (key, name, sorted(bad)[0]))
                values[name] = v
        owner = raw.get("owner")
        return Forge(key=key, host=host.lower(), cli=cli, kind=kind,
                     owner=owner if isinstance(owner, str) and owner else None,
                     remote=raw.get("remote") or key, clone=clone, **values)

    def forge(self, key: str) -> Forge:
        """The forge ``key``; an unknown key is a ``UsageError`` with the choices."""
        if key not in (self.data.get("forges") or {}):
            keys = sorted(self.data.get("forges") or {})
            raise UsageError("unknown forge %r" % key, choices=keys,
                             hint=None if keys else "forges come from ~/.config/tn/conf.d "
                                                    "(dot apply git)")
        return self._make_forge(key)

    def forges(self) -> list[Forge]:
        return [self._make_forge(k) for k in (self.data.get("forges") or {})]

    def forge_for_url(self, url: str) -> Forge | None:
        host, _ = split_url(url)
        if not host:
            return None
        for f in self.forges():
            if f.host == host:
                return f
        return None

    def forge_spec(self, url: str) -> str | None:
        """``work:acme/shop-app`` for a remote URL on a known forge."""
        f = self.forge_for_url(url)
        _, path = split_url(url)
        if f is None or not path:
            return None
        return "%s:%s" % (f.key, path)

    # -- people ------------------------------------------------------------------------------
    def _me(self) -> Person | None:
        raw = (self.data.get("people") or {}).get("me")
        if isinstance(raw, dict) and raw.get("name") and raw.get("email"):
            return Person("me", raw["name"], raw["email"], tuple(raw.get("aliases") or ()))
        # The environment (zsh sources `dot env`), else dot's local.env, where dot.yml persists
        # the MY_NAME / MY_EMAIL answers: Windows shells and non-zsh contexts never load it.
        name = (os.environ.get("MY_NAME") or "").strip() \
            or dotenv_value(dot_local_env(), "MY_NAME")
        email = (os.environ.get("MY_EMAIL") or "").strip() \
            or dotenv_value(dot_local_env(), "MY_EMAIL")
        if name and email:
            return Person("me", name, email)
        return None

    def person(self, key: str) -> Person | None:
        if key == "me":
            return self._me()
        raw = (self.data.get("people") or {}).get(key)
        if not isinstance(raw, dict) or not raw.get("name") or not raw.get("email"):
            return None
        return Person(key, raw["name"], raw["email"], tuple(raw.get("aliases") or ()))

    def people(self) -> list[Person]:
        """Every person, ``me`` included when it exists."""
        out = []
        for k in (self.data.get("people") or {}):
            if k == "me":
                continue
            p = self.person(k)
            if p:
                out.append(p)
        me = self._me()
        if me:
            out.append(me)
        return out

    # -- project -----------------------------------------------------------------------------
    @property
    def project(self) -> ProjectConfig | None:
        """The project's tn.toml values with defaults filled in; None outside a project."""
        return self._project

    def project_config(self, name: str, project_dir: Path) -> ProjectConfig:
        """Another project's config (strict), e.g. for ``tn doctor`` or ``tn proj ls``."""
        f = Path(project_dir) / "tn.toml"
        exists = f.is_file()
        return _project_config(name, Path(project_dir), f, exists, read_toml(f) if exists else {})


def _project_config(name: str, pdir: Path, f: Path, exists: bool, raw: dict) -> ProjectConfig:
    def opt_str(key: str) -> str | None:
        v = raw.get(key)
        if v is None:
            return None
        if not isinstance(v, str):
            raise ConfigError("%s must be a string" % key, f)
        return v or None

    tunnel = raw.get("tunnel", {})
    if not isinstance(tunnel, dict):
        raise ConfigError("[tunnel] must be a table", f)
    ports = tunnel.get("ports", [])
    if not isinstance(ports, list) or not all(isinstance(p, int) and not isinstance(p, bool)
                                              for p in ports):
        raise ConfigError("tunnel.ports must be a list of port numbers", f)
    return ProjectConfig(
        name=name, dir=pdir, file=f, exists=exists, forge=opt_str("forge"),
        group=opt_str("group") or name, identity=opt_str("identity"),
        tunnel_ports=list(ports), raw=raw,
        unknown_keys=sorted(k for k in raw if k not in PROJECT_KEYS))


# Commented templates `tn config edit` starts a missing file from.
USER_TEMPLATE = """\
# tn configuration (see docs/tn.md §4 in the dotfiles repository).
# Bundles ship their part in ~/.config/tn/conf.d/*.toml; this file wins over them.
# No secret goes in here.

# [roots]                       # key -> directory
# projects = "~/myprojects"

# [proj]
# dirs = ["src", "bin", "rel", "key", "tmp"]

# [forges.gh]
# host  = "github.com"
# cli   = "gh"
# owner = "alex"

# [people.someone]
# name  = "Some One"
# email = "some.one@example.com"

# [claude]
# trust = true
"""

PROJECT_TEMPLATE = """\
# Project settings for tn (see docs/tn.md §4.4 in the dotfiles repository).

# forge    = "gh"           # forge key: repo new/clone, git remote add, git open
# group    = "owner/group"  # namespace on that forge; default: the project name
# identity = "me"           # people key set on every repo tn creates or clones here

# [tunnel]
# ports = [3000]            # `tn tunnel open` with no port
"""
