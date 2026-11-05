# common

The clean-machine baseline. `implicit: true`: it is part of every run, and every other bundle
says `requires: [common]` so it runs first and its `path:` / `env:` entries are visible to them.
It is the only bundle another may assume.

## Installs

| | |
|---|---|
| macOS | Homebrew (official installer, on the terminal), then `curl wget git git-lfs vim ranger htop` and the `font-meslo-lg-nerd-font` cask |
| Linux | `ca-certificates curl wget git git-lfs unzip vim ranger htop openssh-client`; `snapd` where systemd is init |
| Linux desktop | `fonts-powerline` |
| Windows | `Git.Git` (winget; includes Git LFS), `Microsoft.PowerShell` (PowerShell 7: the windows profile runs its shell steps in `pwsh`, and Windows ships only 5.1), `Python.PythonInstallManager` (`py`) |

On Windows the install manager puts only `python` / `py` on PATH. `pip` is one of its shortcuts
in `%LOCALAPPDATA%\Python\bin`, and what pip installs lands in the runtime's
`pythoncore-3.X-64\Scripts`; common adds both to the user PATH (new terminals only) and drops an
older runtime's `Scripts`. `python -m pip` works without either.

`unzip` is here because godot's archive and fnm's startup check need it and nothing else can be
assumed. `snapd` is here for [slack](../slack/bundle.yml):
Ubuntu ships it, minimal images may not. It needs systemd as PID 1, hence `init: systemd`.

**Git LFS** is enabled in git's **system** config (`git lfs install --system --skip-repo`): the
`filter.lfs` keys go to `/etc/gitconfig` on Linux (sudo; Ubuntu's `git-lfs` package already does
this from its postinst) and to Homebrew's `etc/gitconfig` on macOS (no sudo), never to
`~/.gitconfig`, which the [git](../git/) bundle renders from a template and would rewrite. Git
for Windows ships LFS enabled. A repository cloned before LFS was enabled needs `git lfs pull`
once; `git lfs install` inside a repository adds its hooks if they are missing.

Powerline fonts are packaged by Ubuntu; macOS has no such package, so it gets a Nerd Font, a
superset of Powerline's glyphs and what modern prompts target.

## Sets up

- `~/.local/bin` on `PATH` (and created): where `tn`, the claude installer and
  `github_release` / `download` `bin:` put executables. Being on `PATH` before those installers
  run is also what keeps them out of `~/.zshrc`. On Windows the step uses `persist: user`, so
  the folder is also written into the user's `Path` in the registry (cmd, PowerShell and
  Explorer find `tn.cmd` without `dot env`); `dot remove common` takes it out only if dot
  added it.
- Homebrew on `PATH` (`/opt/homebrew/{bin,sbin}` on Apple silicon, `/usr/local/{bin,sbin}` in
  front of the system directories on Intel), so later steps find `brew` in the same run, and
  `HOMEBREW_PREFIX` / `HOMEBREW_CELLAR` / `HOMEBREW_REPOSITORY`: together what the old zshrc's
  `eval "$(brew shellenv)"` exported, without a process per shell start.
- `/snap/bin` appended to `PATH` where snapd can run: Ubuntu adds it through `/etc/profile.d`,
  which bash login shells read and zsh does not (the old zshrc added it by hand).
- `MYPROJECTS_DIR` (from the `projects_dir` var) for the scripts'
  project layout convention; shells get them through `dot env --shell zsh`.
- Directories: `~/.ssh` (0700), `~/myprojects`, `~/mylearning`.
- `clean: ["~"]`: dangling links into this repository left in `$HOME` after a file was renamed or
  removed here.
