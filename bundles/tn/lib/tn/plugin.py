"""The plugin API (spec §5.1 - §5.3): ``Plugin``, ``arg``, ``Session``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Session:
    """One agent-like session a sessions hook reports (spec §5.3)."""

    kind: str
    id: str
    name: str
    context: str | None = None
    dir: str | None = None
    started: float | None = None
    attached: bool | None = None
    status: str | None = None
    attach: list | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class ArgSpec:
    names: tuple
    kwargs: dict
    complete: Any = None     # a completer name or a callable (ctx, prefix) -> list

    @property
    def positional(self) -> bool:
        return not self.names[0].startswith("-")

    @property
    def dest(self) -> str:
        if "dest" in self.kwargs:
            return self.kwargs["dest"]
        if self.positional:
            return self.names[0]
        longs = [n for n in self.names if n.startswith("--")]
        return (longs[0] if longs else self.names[0]).lstrip("-").replace("-", "_")

    @property
    def takes_value(self) -> bool:
        action = self.kwargs.get("action", "store")
        if action in ("store_true", "store_false", "store_const", "count", "help", "version",
                      "append_const"):
            return False
        return self.kwargs.get("nargs") != 0


@dataclass
class Command:
    plugin: "Plugin"
    name: str                 # "" for the group's default command; "remote add" for two words
    group: str
    fn: Callable
    help: str | None = None
    passthrough: bool = False

    @property
    def args(self) -> list:
        """ArgSpecs in reading order (decorators apply bottom-up; core reverses them)."""
        return list(reversed(getattr(self.fn, "__tn_args__", [])))

    @property
    def words(self) -> list:
        return self.name.split() if self.name else []


def arg(*names: str, complete: Any = None, **kwargs: Any) -> Callable:
    """Declare one argparse argument of a command (``add_argument`` arguments unchanged).

    ``complete=`` names a completer (``"project"``, ``"repo"``, ``"file"``, ...) or is a
    callable ``(ctx, prefix) -> list[str | (value, description)]``.
    """
    if not names:
        raise TypeError("arg() needs a name or flags")

    def deco(fn: Callable) -> Callable:
        specs = fn.__dict__.setdefault("__tn_args__", [])
        specs.append(ArgSpec(tuple(names), dict(kwargs), complete))
        return fn

    return deco


RESERVED_FLAGS = {"-C", "-n", "-y", "-q", "-v", "-h", "--json", "--dry-run", "--yes",
                  "--quiet", "--verbose", "--no-color", "--help", "--version"}


class Plugin:
    """One per plugin module, bound to the module-level name ``plugin``.

    Every argument must be a literal: the index reads them with ``ast`` without importing.
    """

    def __init__(self, name: str, *, help: str = "", requires=(), groups=()) -> None:
        self.name = name
        self.help = help
        self.requires = list(requires)
        self.groups = list(groups) if groups else [name]
        self.commands: list[Command] = []
        self.status_hooks: list[Callable] = []
        self.check_hooks: list[Callable] = []
        self.session_hooks: list[Callable] = []
        self.completers: dict[str, Callable] = {}
        self.file: str | None = None      # set by the loader

    def __repr__(self) -> str:
        return "<tn Plugin %s groups=%s>" % (self.name, self.groups)

    # -- commands ----------------------------------------------------------------------------
    def command(self, name: str | None = None, *, group: str | None = None,
                help: str | None = None, passthrough: bool = False) -> Callable:
        """Register a command. ``name`` defaults to the function name (``_`` -> ``-``, a
        trailing ``_`` dropped); ``name=""`` is the group's default command; a name with a
        space is a two-word verb (``"remote add"``)."""
        if callable(name):
            raise TypeError("use @plugin.command() with parentheses")

        def deco(fn: Callable) -> Callable:
            n = name
            if n is None:
                n = fn.__name__.rstrip("_").replace("_", "-")
            n = " ".join(n.split())
            g = group or self.groups[0]
            if g not in self.groups:
                raise ValueError("plugin %s: group %r is not in its groups %s"
                                 % (self.name, g, self.groups))
            for c in self.commands:
                if c.group == g and c.name == n:
                    raise ValueError("plugin %s: command %r defined twice in group %s"
                                     % (self.name, n, g))
            doc = (fn.__doc__ or "").strip().splitlines()
            self.commands.append(Command(self, n, g, fn, help or (doc[0] if doc else None),
                                         passthrough))
            return fn

        return deco

    def group_commands(self, group: str) -> list[Command]:
        return [c for c in self.commands if c.group == group]

    def default_command(self, group: str) -> Command | None:
        for c in self.commands:
            if c.group == group and c.name == "":
                return c
        return None

    # -- hooks -------------------------------------------------------------------------------
    def status(self, fn: Callable) -> Callable:
        """``(ctx) -> str | list[str] | None`` for ``tn status``."""
        self.status_hooks.append(fn)
        return fn

    def check(self, fn: Callable) -> Callable:
        """``(ctx) -> None | str`` for ``tn doctor``; the docstring's first line is the label."""
        self.check_hooks.append(fn)
        return fn

    def sessions(self, fn: Callable) -> Callable:
        """``(ctx) -> list[Session]`` for ``tn sessions``."""
        self.session_hooks.append(fn)
        return fn

    def completer(self, name: str) -> Callable:
        """Register the named completer ``(ctx, prefix) -> list[str | (value, description)]``."""
        def deco(fn: Callable) -> Callable:
            self.completers[name] = fn
            return fn
        return deco


def check_label(fn: Callable) -> str:
    doc = (fn.__doc__ or "").strip().splitlines()
    return doc[0].strip() if doc else fn.__name__.replace("_", " ")
