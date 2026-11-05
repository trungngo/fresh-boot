"""Global options and the per-invocation state core helpers read (``run`` honours dry-run, ...)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Options:
    json: bool = False
    dry_run: bool = False
    yes: bool = False
    quiet: bool = False
    verbose: int = 0
    color: bool = False     # allowed by flags and environment; each stream still needs a TTY


class _State:
    """What the current invocation runs with. Reset by ``tn.cli.main`` on every call."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.options = Options()
        self.plugin: str | None = None           # the plugin whose code is running
        self.handoff_hook = None                 # tn.testing: record instead of exec
        self.debug = False


state = _State()


def current() -> Options:
    return state.options
