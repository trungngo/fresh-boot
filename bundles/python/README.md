# python

Python through [uv](https://docs.astral.sh/uv/) (Astral): uv itself, then the newest stable
CPython as uv's managed default, with `python3` and `python` in `~/.local/bin`. macOS and Linux.
Also a [tn](../tn/README.md) plugin with one doctor check (see [tn plugin](#tn-plugin)).

## Installs

| | uv | CPython |
|---|---|---|
| macOS | `brew install uv` | `uv python install --default ...` |
| Linux | `github_release` of `astral-sh/uv` (`uv-<arch>-unknown-linux-gnu.tar.gz`: `uv`, `uvx` to `~/.local/bin`) | same |

uv downloads **prebuilt** CPython ([python-build-standalone](https://github.com/astral-sh/python-build-standalone),
into `~/.local/share/uv/python`), so there is no compiler, no build-dependency list and no
per-machine build any more.

The CPython step picks the newest stable minor uv knows, from `uv python list --only-downloads
--output-format json` (keys matching `cpython-3.X.Y-` exactly, so prereleases such as
`3.15.0rc1` and the freethreaded builds are skipped), and runs

    uv python install --default --upgrade --preview-features python-install-default 3.X

- `--upgrade` with a minor request installs it, or moves it to its newest patch release.
- `--default` also installs `python3` and `python` (besides `python3.X`) into uv's bin
  directory, `uv python dir --bin` = `~/.local/bin` (on `PATH` via
  [common](../common/README.md), ahead of `/usr/bin`). It is still a preview option; naming
  the preview feature only silences the warning.

The step is satisfied while `~/.local/bin/python3` exists. `dot apply --upgrade` upgrades uv
first (the release, or brew), then runs the same command: a newer patch replaces the old one in
place (uv keeps a `cpython-3.X-...` minor-version link, so virtualenvs follow), a newer minor
becomes `python3`. Older minors stay installed (`uv python list --only-installed`,
`uv python uninstall 3.X`). uv's list of downloadable Pythons is compiled into uv, so a new
CPython minor shows up only after uv itself is upgraded.

A project pins its own version with `uv python pin` / `.python-version` or `requires-python`;
`uv venv`, `uv run` and `uvx` pick it up. `python -m venv` works as before.

`python.zsh` (linked to `~/.config/zsh/conf.d/`) only loads the `uv` / `uvx` completions:
nothing else is needed, there are no shims and no init script.

## tn plugin

The `python` plugin (`plugin.py`, copied to `~/.local/share/tn/plugins/python.py`; spec:
[docs/tn.md §7.7](../../docs/tn.md)) has no commands, only a check: `tn doctor` warns when uv
is missing (`dot apply python`).

`tn dj` (Django `manage.py`) and `tn py serve` were removed as outdated: run
`python manage.py ...` (or `uv run python manage.py ...`) and
`python3 -m http.server --bind 127.0.0.1` directly.

## Gotchas

- **No pyenv.** It used to be a vendored submodule symlinked to `~/.pyenv`, then (in this repo)
  an upstream `git:` checkout; both are gone, along with `PYENV_ROOT`, `~/.pyenv/bin` on `PATH`,
  `pyenv init` and the CPython build dependencies (`libssl-dev`, `tcl-tk@8`, ...). A leftover
  `~/.pyenv` *symlink* is removed (only a symlink); a real `~/.pyenv` with versions built by an
  earlier setup is left alone: delete it by hand once no virtualenv points into it.
- uv never edits shell rc files here: it is installed from its release tarball or brew, not by
  `uv-installer.sh` (which would add a PATH line to `~/.zshrc`, a link into this repo), and
  `uv python update-shell` is never run (common's `path: [~/.local/bin]` already covers it).
- The Linux asset is the glibc (`-gnu`) build; uv's own installer picks that one too on any
  glibc new enough, which every supported Ubuntu is.
- On Ubuntu, `/usr/bin/python3` (the distro's) stays; `~/.local/bin/python3` wins on `PATH` for
  your shells. System tools use their own shebang (`/usr/bin/python3`) and are unaffected.
- Nothing is pinned: no Python or uv version appears in this repo.
