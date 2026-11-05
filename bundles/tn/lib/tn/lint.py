"""Repository lint for tn plugins (spec §9.1 step 3): ``python3 -m tn.lint <repo>``.

Fails (exit 1) when a plugin does not index with literal ``Plugin(...)`` arguments, two plugins
(or a plugin and a built-in) claim a group, a plugin's ``requires`` is not a subset of its
bundle's ``requires``, a bundle with a plugin lacks the copy step, a plugin declares a reserved
global flag, or a plugin does not compile under the running Python (run it with the oldest
Python you support: python3.11).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from .loader import BUILTINS, repo_plugins
from .plugin import RESERVED_FLAGS


def bundle_requires(bundle_yml: Path) -> list:
    """The ``requires:`` list of a bundle.yml (flow ``[a, b]`` or block ``- a`` form)."""
    try:
        lines = bundle_yml.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for i, line in enumerate(lines):
        m = re.match(r"^requires:\s*(.*?)\s*(#.*)?$", line)
        if not m:
            continue
        rest = m.group(1)
        if rest.startswith("["):
            inner = rest.strip("[]")
            return [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
        out = []
        for nxt in lines[i + 1:]:
            mm = re.match(r"^\s+-\s*([^#\s]+)", nxt)
            if not mm:
                break
            out.append(mm.group(1).strip("'\""))
        return out
    return []


def _reserved_flags(source: str) -> list:
    found = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return found
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (
                (isinstance(node.func, ast.Name) and node.func.id == "arg")
                or (isinstance(node.func, ast.Attribute) and node.func.attr == "arg")):
            for a in node.args:
                if isinstance(a, ast.Constant) and a.value in RESERVED_FLAGS:
                    found.append((a.value, node.lineno))
    return found


def _py_files(path: Path) -> list:
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)


def lint(repo: Path) -> list:
    problems = []
    infos = repo_plugins(repo)
    claims: dict = {}
    for info in infos:
        bundle = Path(info.path)
        rel = bundle.relative_to(repo)
        if info.broken:
            problems.append("%s: plugin does not index: %s" % (rel, info.broken))
            continue
        for g in info.groups:
            claims.setdefault(g, []).append(info.name)
        req = set(bundle_requires(bundle / "bundle.yml"))
        extra = [r for r in info.requires if r.replace("_", "-") not in req]
        if extra:
            problems.append("%s: plugin requires %s, which bundle.yml does not require"
                            % (rel, ", ".join(extra)))
        yml = (bundle / "bundle.yml").read_text(encoding="utf-8") \
            if (bundle / "bundle.yml").is_file() else ""
        name = bundle.name.replace("-", "_")
        is_pkg = (bundle / "plugin").is_dir()
        dest = "~/.local/share/tn/plugins/%s%s" % (name, "" if is_pkg else ".py")
        if dest not in yml:
            problems.append("%s: bundle.yml has no copy step to %s" % (rel, dest))
        src = bundle / ("plugin" if is_pkg else "plugin.py")
        for f in _py_files(src):
            text = f.read_text(encoding="utf-8")
            try:
                compile(text, str(f), "exec", dont_inherit=True)
                ast.parse(text, filename=str(f), feature_version=(3, 11))
            except SyntaxError as e:
                problems.append("%s:%s: does not compile under Python %d.%d / 3.11 grammar: %s"
                                % (f.relative_to(repo), e.lineno, sys.version_info[0],
                                   sys.version_info[1], e.msg))
            for flag, line in _reserved_flags(text):
                problems.append("%s:%d: declares the reserved global flag %s"
                                % (f.relative_to(repo), line, flag))
    for g, names in sorted(claims.items()):
        if len(names) > 1:
            problems.append('group "%s" is claimed by %s' % (g, ", ".join(names)))
        if g in BUILTINS:
            problems.append('group "%s" (plugin %s) shadows a built-in' % (g, names[0]))
    return problems


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    repo = Path(argv[0]) if argv else Path.cwd()
    problems = lint(repo)
    for p in problems:
        sys.stderr.write("lint: %s\n" % p)
    n = len(repo_plugins(repo))
    sys.stderr.write("lint: %d plugin%s checked, %d problem%s\n"
                     % (n, "" if n == 1 else "s", len(problems), "" if len(problems) == 1 else "s"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
