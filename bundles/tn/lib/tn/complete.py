"""``tn __complete <cword> [--] <word0> <word1> ...`` (spec §5.7).

Prints one candidate per line (``value`` or ``value<TAB>description``). Never prompts, never
fails loudly: any error prints nothing. ``__tn_files__`` / ``__tn_dirs__`` ask the shell for
its own file or directory completion.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

from . import loader
from .cli import BUILTIN_HELP, GLOBAL_HELP, Globals, load_context, parse_globals
from .context import Context
from .options import Options, state
from .plugin import ArgSpec, Command, Plugin

FILES, DIRS = "__tn_files__", "__tn_dirs__"
GLOBAL_FLAGS = ["-C", "--json", "--dry-run", "--yes", "--quiet", "--verbose", "--no-color",
                "--help", "--version"]
_NO_VALUE_GLOBALS = {"--json", "-n", "--dry-run", "-y", "--yes", "-q", "--quiet", "-v", "-vv",
                     "--verbose", "--no-color"}


def main(args: list, g: Globals) -> int:
    saved_stderr = sys.stderr
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
        lines = candidates(args)
    except BaseException:  # noqa: BLE001 - completion never fails loudly
        lines = []
    finally:
        if sys.stderr is not saved_stderr:
            try:
                sys.stderr.close()
            except OSError:
                pass
        sys.stderr = saved_stderr
    seen = set()
    for line in lines:
        if line not in seen:
            seen.add(line)
            sys.stdout.write(line + "\n")
    return 0


def _fmt(items: list, prefix: str) -> list:
    res = []
    for it in items or []:
        if isinstance(it, (tuple, list)):
            v, d = str(it[0]), (str(it[1]) if len(it) > 1 and it[1] else "")
        else:
            v, d = str(it), ""
        if v in (FILES, DIRS):
            res.append(v)
            continue
        if not v.startswith(prefix):
            continue
        d = d.replace("\t", " ").replace("\n", " ")
        res.append(v + ("\t" + d if d else ""))
    return res


def candidates(args: list) -> list:
    if not args:
        return []
    cword = int(args[0])
    words = list(args[1:])
    if words and words[0] == "--":
        words = words[1:]
    while len(words) <= cword:
        words.append("")
    prefix = words[cword]
    before = words[1:cword]

    # Global flags (and -C's value) out of the words before the cursor.
    cdirs, toks = [], []
    i = 0
    while i < len(before):
        t = before[i]
        if t == "--":
            toks.extend(before[i:])
            break
        if t == "-C":
            if i + 1 >= len(before):
                return [DIRS]
            cdirs.append(before[i + 1])
            i += 2
            continue
        if t.startswith("-C") and len(t) > 2:
            cdirs.append(t[2:])
        elif t in _NO_VALUE_GLOBALS or (len(t) > 1 and t[0] == "-" and t[1] != "-"
                                        and all(c in "nyqv" for c in t[1:])):
            pass
        else:
            toks.append(t)
        i += 1
    if before and before[-1] == "-C":
        return [DIRS]

    cwd = Path(os.getcwd())
    for d in cdirs:
        nxt = Path(os.path.normpath(os.path.join(str(cwd), os.path.expanduser(d))))
        if nxt.is_dir():
            cwd = nxt
    state.options = Options(json=False, quiet=True)
    reg = loader.discover()
    loader.setup_namespace(reg)

    if not toks:
        if prefix.startswith("-"):
            return _fmt([(f, "") for f in GLOBAL_FLAGS], prefix)
        items = list(BUILTIN_HELP)
        for info in reg.sorted_plugins():
            if info.broken:
                continue
            for grp in info.groups:
                if grp in reg.groups:
                    items.append((grp, info.help))
        return _fmt(sorted(items), prefix)

    ctx = load_context(cwd, state.options, lenient=True)
    group, rest = toks[0], toks[1:]
    if group in loader.BUILTINS:
        return _builtin(group, rest, prefix, ctx, reg)
    info = reg.owner(group)
    if info is None:
        return []
    plugin = loader.load(reg, info.name)
    return _plugin(plugin, group, rest, prefix, ctx, reg)


def _builtin(group: str, rest: list, prefix: str, ctx: Context, reg) -> list:
    if group == "config":
        if not rest:
            return _fmt(["get", "set", "edit", "show"], prefix)
        if prefix.startswith("-"):
            return _fmt(["--project"], prefix)
        if rest[0] in ("get", "set") and len(rest) == 1:
            keys = ["machine"] + _dotted_keys(ctx.config.data)
            return _fmt(keys, prefix)
        return []
    if group == "shell":
        if not rest:
            return _fmt(["init"], prefix)
        if rest == ["init"]:
            return _fmt(["zsh", "bash", "pwsh"], prefix)
        return []
    if group == "sessions":
        if not rest:
            return _fmt(["attach"], prefix)
        if rest == ["attach"]:
            return _fmt(_session_ids(ctx, reg), prefix)
        return []
    if group == "plugins" and prefix.startswith("-"):
        return _fmt(["--repo"], prefix)
    return []


def _dotted_keys(data: dict, pre: str = "") -> list:
    keys = []
    for k, v in data.items():
        keys.append(pre + k)
        if isinstance(v, dict):
            keys.extend(_dotted_keys(v, pre + k + "."))
    return keys


def _session_ids(ctx: Context, reg) -> list:
    from .builtins import all_sessions
    sessions, _ = all_sessions(ctx, reg)
    return [(s.id, s.name) for s in sessions]


def _plugin(plugin: Plugin, group: str, rest: list, prefix: str, ctx: Context, reg) -> list:
    cmds = plugin.group_commands(group)
    default = plugin.default_command(group)
    verbs = {c.name: c for c in cmds if c.name}
    if not rest:
        items = []
        for name, c in sorted(verbs.items()):
            first = name.split()[0]
            items.append((first, "" if " " in name else (c.help or "")))
        res = _fmt(items, prefix)
        if default is not None and not prefix.startswith("-"):
            res += _command(default, [], prefix, ctx, plugin, reg)
        return res
    cmd, tokens = None, rest
    if len(rest) >= 2 and "%s %s" % (rest[0], rest[1]) in verbs:
        cmd, tokens = verbs["%s %s" % (rest[0], rest[1])], rest[2:]
    elif rest[0] in verbs:
        cmd, tokens = verbs[rest[0]], rest[1:]
    else:
        subs = [v.split()[1] for v in verbs if " " in v and v.split()[0] == rest[0]]
        if subs and len(rest) == 1:
            return _fmt([(s, verbs["%s %s" % (rest[0], s)].help or "") for s in subs], prefix)
        if default is not None:
            cmd, tokens = default, rest
    if cmd is None:
        return []
    return _command(cmd, tokens, prefix, ctx, plugin, reg)


def _command(cmd: Command, tokens: list, prefix: str, ctx: Context, plugin: Plugin,
             reg) -> list:
    specs = cmd.args
    options = {n: a for a in specs if not a.positional for n in a.names}
    if "--" in tokens:
        return []
    if prefix.startswith("-"):
        items = []
        for a in specs:
            if a.positional or a.kwargs.get("help") == "==SUPPRESS==":
                continue
            longs = [n for n in a.names if n.startswith("--")] or list(a.names)
            items.append((longs[0], a.kwargs.get("help") or ""))
        return _fmt(items, prefix)
    if tokens and tokens[-1] in options and options[tokens[-1]].takes_value:
        return _run_completer(options[tokens[-1]], ctx, prefix, plugin, reg)
    positionals = [a for a in specs if a.positional]
    n = 0
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in options:
            if options[t].takes_value:
                i += 1
        elif not t.startswith("-"):
            n += 1
        i += 1
    if not positionals:
        return []
    idx = min(n, len(positionals) - 1)
    a = positionals[idx]
    if n >= len(positionals) and a.kwargs.get("nargs") not in ("*", "+", "..."):
        return []
    return _run_completer(a, ctx, prefix, plugin, reg)


def core_completers() -> dict:
    def forge(ctx, prefix):
        return [(f.key, f.host) for f in ctx.config.forges()]

    def person(ctx, prefix):
        return [(p.key, "%s <%s>" % (p.name, p.email)) for p in ctx.config.people()]

    def session(ctx, prefix):
        return _session_ids(ctx, loader.discover())

    return {"forge": forge, "person": person, "session": session}


def find_completer(name: str, plugin: Plugin, reg) -> Callable | None:
    if name in plugin.completers:
        return plugin.completers[name]
    for req in plugin.requires:
        try:
            p = loader.load(reg, req)
        except Exception:  # noqa: BLE001
            continue
        if name in p.completers:
            return p.completers[name]
    plugins, _ = loader.load_all(reg)
    for p in plugins:
        if name in p.completers:
            return p.completers[name]
    return core_completers().get(name)


def _run_completer(a: ArgSpec, ctx: Context, prefix: str, plugin: Plugin, reg) -> list:
    comp: Any = a.complete
    if comp is None:
        choices = a.kwargs.get("choices")
        return _fmt(list(choices), prefix) if choices else []
    if comp == "file":
        return [FILES]
    if comp == "dir":
        return [DIRS]
    fn = comp if callable(comp) else find_completer(str(comp), plugin, reg)
    if fn is None:
        return []
    return _fmt(list(fn(ctx, prefix) or []), prefix)
