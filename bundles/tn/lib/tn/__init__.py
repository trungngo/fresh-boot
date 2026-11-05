"""tn: the helper command of the dotfiles repository (docs/tn.md).

The public API for plugins is re-exported here::

    from tn import Plugin, Context, arg, run, capture, need, out, pick, confirm, UsageError
"""

__version__ = "0.1.0"

from .errors import Cancelled, Fail, Missing, Problem, TnError, UsageError
from .options import Options
from .config import Config, Forge, Person, ProjectConfig, split_url
from .context import Context, pascal, slugify
from .plugin import Plugin, Session, arg
from .output import out
from .proc import capture, git, handoff, need, pid_alive, run, spawn_detached
from .prompt import ask, can_prompt, confirm, pick
from .match import match
from . import clock, fs, term

__all__ = [
    "__version__", "Cancelled", "Fail", "Missing", "Problem", "TnError", "UsageError", "Options",
    "Config", "Forge", "Person", "ProjectConfig", "split_url", "Context", "pascal",
    "slugify", "Plugin", "Session", "arg", "out", "capture", "git", "handoff", "need",
    "pid_alive", "run", "spawn_detached", "ask", "can_prompt", "confirm", "pick", "match",
    "clock", "fs", "term",
]
