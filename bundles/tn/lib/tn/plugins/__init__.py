"""Namespace for installed tn plugins.

tn points this package's ``__path__`` at the directories of ``TN_PLUGIN_PATH`` (default
``$TN_HOME/plugins``, i.e. ``~/.local/share/tn/plugins``), so ``import tn.plugins.<name>`` and,
inside a plugin, ``from tn.plugins import projects`` load the plugin files dot copied there.
The same path is set here on first import, so a test module can import a plugin at the top.
Nothing in this directory itself is ever a plugin.
"""

import os as _os
from pathlib import Path as _Path


def _plugin_path() -> list:
    v = _os.environ.get("TN_PLUGIN_PATH")
    if v:
        return [p for p in v.split(_os.pathsep) if p]
    home = _os.environ.get("TN_HOME")
    base = _Path(home) if home else _Path.home() / ".local" / "share" / "tn"
    return [str(base / "plugins")]


__path__[:] = _plugin_path()  # noqa: F821 - __path__ is set by the import system
