"""Plugin discovery, the ast index, group clashes and lazy imports (spec §5.8, §5.9)."""

from __future__ import annotations

import ast
import importlib
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config as _config
from .errors import Fail, Missing
from .output import out
from .plugin import Plugin

BUILTINS = ("status", "doctor", "sessions", "plugins", "config", "shell")


def plugin_dirs() -> list[Path]:
    """``TN_PLUGIN_PATH`` (``os.pathsep``-separated) or ``$TN_HOME/plugins``."""
    v = os.environ.get("TN_PLUGIN_PATH")
    if v:
        return [Path(p) for p in v.split(os.pathsep) if p]
    return [_config.tn_home() / "plugins"]


@dataclass
class Info:
    """What the index knows about one plugin, without importing it."""

    name: str
    file: str                       # the .py file parsed (a package's __init__.py)
    path: str                       # the plugin file or package directory
    help: str = ""
    requires: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    broken: str | None = None


def _literal(node: ast.AST, what: str):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        raise ValueError("%s is not a literal" % what)


def _str_list(v, what: str) -> list:
    if isinstance(v, str) or not isinstance(v, (list, tuple)) \
            or not all(isinstance(x, str) for x in v):
        raise ValueError("%s must be a list of strings" % what)
    return list(v)


def index_source(source: str, filename: str, expected: str | None) -> Info:
    """Read ``plugin = Plugin(...)`` from source text. Broken when it is missing, not all
    literals, or names another plugin than ``expected``."""
    info = Info(name=expected or "", file=filename, path=filename)
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        info.broken = "syntax error at line %s: %s" % (e.lineno, e.msg)
        return info
    call = None
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        if any(isinstance(t, ast.Name) and t.id == "plugin" for t in targets):
            v = node.value
            if isinstance(v, ast.Call) and (
                    (isinstance(v.func, ast.Name) and v.func.id == "Plugin")
                    or (isinstance(v.func, ast.Attribute) and v.func.attr == "Plugin")):
                call = v
    if call is None:
        info.broken = "no module-level plugin = Plugin(...)"
        return info
    try:
        name = None
        if call.args:
            name = _literal(call.args[0], "the plugin name")
        if len(call.args) > 1:
            raise ValueError("Plugin() takes the name as its only positional argument")
        kw = {}
        for k in call.keywords:
            if k.arg is None:
                raise ValueError("Plugin(**...) is not a literal")
            kw[k.arg] = _literal(k.value, k.arg)
        if name is None:
            name = kw.pop("name", None)
        if not isinstance(name, str) or not name:
            raise ValueError("the plugin name must be a string literal")
        info.name = name
        h = kw.get("help", "")
        if not isinstance(h, str):
            raise ValueError("help must be a string")
        info.help = h
        info.requires = _str_list(kw.get("requires", []), "requires")
        groups = kw.get("groups")
        info.groups = _str_list(groups, "groups") if groups else [name]
        unknown = set(kw) - {"help", "requires", "groups"}
        if unknown:
            raise ValueError("unknown Plugin() argument %s" % sorted(unknown)[0])
    except ValueError as e:
        info.broken = str(e)
        return info
    if expected is not None and info.name != expected:
        info.broken = "Plugin(%r) does not match its file name %r" % (info.name, expected)
        info.name = expected
    return info


def index_file(path: Path, expected: str | None) -> Info:
    try:
        source = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return Info(name=expected or "", file=str(path), path=str(path),
                    broken="cannot read: %s" % e)
    return index_source(source, str(path), expected)


class _Cache:
    """``~/.cache/tn/index.json``: path -> (mtime_ns, size, info)."""

    def __init__(self) -> None:
        self.file = _config.cache_dir() / "index.json"
        self.data: dict = {}
        self.dirty = False
        try:
            raw = json.loads(self.file.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw.get("version") == 1:
                self.data = raw.get("entries") or {}
        except (OSError, ValueError):
            pass

    def get(self, path: Path, expected: str | None) -> Info:
        key = str(path)
        try:
            st = path.stat()
            stamp = [st.st_mtime_ns, st.st_size, expected]
        except OSError:
            return index_file(path, expected)
        hit = self.data.get(key)
        if hit and hit.get("stamp") == stamp:
            try:
                return Info(**hit["info"])
            except TypeError:
                pass
        info = index_file(path, expected)
        self.data[key] = {"stamp": stamp, "info": asdict(info)}
        self.dirty = True
        return info

    def save(self) -> None:
        if not self.dirty:
            return
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_name(self.file.name + ".%d.tmp" % os.getpid())
            tmp.write_text(json.dumps({"version": 1, "entries": self.data}), encoding="utf-8")
            os.replace(tmp, self.file)
        except OSError:
            pass


@dataclass
class Registry:
    """Everything discovery found: plugins by name, groups by owner, clashes, problems."""

    dirs: list
    plugins: dict = field(default_factory=dict)       # name -> Info
    groups: dict = field(default_factory=dict)        # group -> plugin name (clashes removed)
    clashes: dict = field(default_factory=dict)       # group -> [plugin names]
    notes: list = field(default_factory=list)         # -v notes (duplicates)
    unreadable: list = field(default_factory=list)    # (dir, reason)

    def owner(self, group: str) -> Info | None:
        name = self.groups.get(group)
        return self.plugins.get(name) if name else None

    def sorted_plugins(self) -> list:
        return [self.plugins[k] for k in sorted(self.plugins)]


def _entries(d: Path) -> list:
    """(name, path, file to parse) for each plugin in one directory, sorted by name."""
    found: dict = {}
    errors = []
    for p in sorted(d.iterdir(), key=lambda x: x.name):
        n = p.name
        if n.startswith("_") or n.startswith("."):
            continue
        if p.is_file() and n.endswith(".py"):
            name, parse = n[:-3], p
        elif p.is_dir() and (p / "__init__.py").is_file():
            name, parse = n, p / "__init__.py"
        else:
            continue
        if name in found:
            errors.append(name)
            continue
        found[name] = (p, parse)
    return [(n, found[n][0], found[n][1], n in errors) for n in sorted(found)]


def discover() -> Registry:
    reg = Registry(dirs=plugin_dirs())
    cache = _Cache()
    for d in reg.dirs:
        if not d.is_dir():
            continue
        try:
            entries = _entries(d)
        except OSError as e:
            reg.unreadable.append((d, e.strerror or str(e)))
            continue
        for name, path, parse, both in entries:
            if name in reg.plugins:
                reg.notes.append("ignoring %s: %s is already provided by %s"
                                 % (path, name, reg.plugins[name].path))
                continue
            info = cache.get(parse, name)
            info.path = str(path)
            if both:
                info.broken = "both %s.py and a %s/ package in %s" % (name, name, d)
            reg.plugins[name] = info
    cache.save()
    claims: dict = {}
    for info in reg.sorted_plugins():
        if info.broken:
            continue
        for g in info.groups:
            claims.setdefault(g, []).append(info.name)
    for g, names in claims.items():
        if len(names) > 1 or g in BUILTINS:
            reg.clashes[g] = names + (["tn (built-in)"] if g in BUILTINS else [])
        else:
            reg.groups[g] = names[0]
    return reg


def clash_message(reg: Registry, group: str) -> str:
    names = reg.clashes[group]
    files = [os.path.basename(reg.plugins[n].path) if n in reg.plugins else n for n in names]
    return ('group "%s" is claimed by both %s; remove one (dot remove <bundle>)'
            % (group, " and ".join(files)))


# -- imports ---------------------------------------------------------------------------------


def bundle_of(plugin_name: str) -> str:
    return plugin_name.replace("_", "-")


def setup_namespace(reg: Registry) -> None:
    """Point ``tn.plugins.__path__`` at the plugin directories, dropping modules imported
    from elsewhere (another TN_PLUGIN_PATH in the same process: tests)."""
    import tn.plugins as ns
    paths = [str(d) for d in reg.dirs]
    ns.__path__[:] = paths
    for modname in [m for m in list(sys.modules) if m.startswith("tn.plugins.")]:
        mod = sys.modules.get(modname)
        f = getattr(mod, "__file__", None) or ""
        top = modname.split(".")[2]
        info = reg.plugins.get(top)
        stale = True
        if info is not None and f:
            fa, pa = os.path.abspath(f), os.path.abspath(info.path)
            stale = not (fa == pa or fa.startswith(pa + os.sep))
        if not stale and modname.count(".") == 2:
            try:
                mtime = os.stat(info.file).st_mtime_ns
                seen = getattr(mod, "__tn_mtime__", None)
                if seen is None:        # imported directly (a test module): adopt it
                    mod.__tn_mtime__ = mtime
                stale = seen is not None and seen != mtime
            except OSError:
                stale = True
        if stale:
            del sys.modules[modname]
            if modname.count(".") == 2 and hasattr(ns, top):
                try:
                    delattr(ns, top)
                except AttributeError:
                    pass
    importlib.invalidate_caches()


class PluginLoadError(Fail):
    pass


def load(reg: Registry, name: str, _chain: tuple = ()) -> Plugin:
    """Import plugin ``name`` (its ``requires`` first) and return its ``Plugin``."""
    info = reg.plugins.get(name)
    if info is None:
        if _chain:
            raise Missing("the %s plugin needs the %s plugin" % (_chain[-1], name),
                          "dot apply %s" % bundle_of(name))
        raise Missing("the %s plugin is not installed" % name, "dot apply %s" % bundle_of(name))
    if info.broken:
        raise PluginLoadError("the %s plugin is broken: %s" % (name, info.broken),
                              hint="file: %s" % info.path)
    if name in _chain:
        raise PluginLoadError("plugins require each other in a cycle: %s"
                              % " -> ".join(_chain + (name,)))
    for req in info.requires:
        if req not in reg.plugins:
            raise Missing("the %s plugin needs the %s plugin" % (name, req),
                          "dot apply %s" % bundle_of(req))
        load(reg, req, _chain + (name,))
    modname = "tn.plugins." + name
    mod = sys.modules.get(modname)
    if mod is None:
        try:
            mod = importlib.import_module(modname)
        except Missing:
            raise
        except BaseException as e:  # noqa: BLE001 - a plugin's import error is its own row
            if isinstance(e, KeyboardInterrupt):
                raise
            sys.modules.pop(modname, None)
            raise PluginLoadError("the %s plugin failed to load: %s: %s"
                                  % (name, type(e).__name__, e), hint="file: %s" % info.path)
        try:
            mod.__tn_mtime__ = os.stat(info.file).st_mtime_ns
        except OSError:
            pass
    p = getattr(mod, "plugin", None)
    if not isinstance(p, Plugin):
        raise PluginLoadError("the %s plugin has no plugin = Plugin(...) object" % name)
    if p.name != name:
        raise PluginLoadError("the %s plugin names itself %r" % (name, p.name))
    p.file = info.path
    return p


def load_all(reg: Registry) -> tuple:
    """([Plugin], {name: error message}) for every installed plugin."""
    loaded, errors = [], {}
    for info in reg.sorted_plugins():
        try:
            loaded.append(load(reg, info.name))
        except (Fail, Missing) as e:
            errors[info.name] = e.message
    return loaded, errors


# -- the dotfiles checkout (§5.9) ------------------------------------------------------------


def dot_repo() -> Path:
    v = os.environ.get("DOT_REPO")
    if not v:
        v = _config.dotenv_value(_config.dot_local_env(), "DOT_REPO")
    return _config.expand_path(v) if v else Path.home() / ".dot"


def repo_plugins(repo: Path | None = None) -> list:
    """Info for every ``bundles/*/plugin.py`` (or ``plugin/__init__.py``) in the checkout;
    ``Info.path`` is the bundle directory and ``Info.name`` the plugin name."""
    repo = repo or dot_repo()
    bundles = repo / "bundles"
    found = []
    if not bundles.is_dir():
        return found
    try:
        dirs = sorted(p for p in bundles.iterdir() if p.is_dir())
    except OSError:
        return found
    for b in dirs:
        expected = b.name.replace("-", "_")
        for f in (b / "plugin.py", b / "plugin" / "__init__.py"):
            if f.is_file():
                info = index_file(f, expected)
                info.path = str(b)
                found.append(info)
                break
    return found


def debug_notes(reg: Registry) -> None:
    for n in reg.notes:
        out.debug("note: " + n)
