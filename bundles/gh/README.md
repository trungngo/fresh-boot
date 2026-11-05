# gh

The [GitHub CLI](https://cli.github.com/). Selected by every profile (mac, ubuntu-desktop,
ubuntu-server, windows).

## Installs

| platform | from |
|---|---|
| macOS | Homebrew `gh` |
| Debian / Ubuntu | GitHub's apt repository `https://cli.github.com/packages` (`package_repo`), package `gh` |
| Windows | winget `GitHub.cli` |

**Not Ubuntu's `gh`**: universe carries it, but it lags badly (2.46 against 2.98 upstream when
the old module was written), so the vendor's repository is used, as GitHub documents and the old
`install.sh` did. `dot apply --upgrade` upgrades gh with the rest of apt's packages; dot refreshes
the apt lists itself (the old `refresh_apt` helper is gone).

The repository's keyring (`/etc/apt/keyrings/githubcli-archive-keyring.gpg`, the name GitHub
documents, so a machine set up by the old module is taken over in place) holds **two** primary
keys: the current signing key `7F38BBB59D064DBCB3D84D725612B36462313325` and the one it rotated
from, `2C6106201985B60E6C7AC87323F3D4EA75716059`. Both are pinned (`fingerprint:` list); a
keyring with any other key is refused. When GitHub rotates again, check the new fingerprint
against <https://github.com/cli/cli/blob/trunk/docs/install_linux.md> and add it. `replaces:`
removes the old one-line `/etc/apt/sources.list.d/github-cli.list`: dot writes a deb822
`github-cli.sources` instead, and apt refuses a repository listed twice.

## Links

| destination | source |
|---|---|
| `~/.config/gh/config.yml` (macOS, Linux) | `config.yml`: settings and aliases |
| `%APPDATA%\GitHub CLI\config.yml` (Windows, `{{ config_dir }}`) | `config.yml` |
| `~/.config/zsh/conf.d/gh.zsh` | `gh.zsh`: zsh completion |

gh uses `~/.config/gh` on macOS too (XDG), hence the literal path; on Windows it uses
`%APPDATA%\GitHub CLI`.

`config.yml` is **linked** because gh preserves the symlink when it rewrites the file, so
`gh alias set` / `gh config set` edits land in this repository. It never holds credentials; those
are in `hosts.yml` (not tracked) and the keyring. Settings: `git_protocol: https`, alias
`co: pr checkout`. On Windows without Developer Mode dot falls back to a copy, which gh's edits
then turn into an ordinary file (backed up and replaced on the next apply): make the edit here.

## Authentication (by hand, once per machine)

    gh auth login

Tokens are **not** tracked. `gh auth login` stores them in the system keyring. Two accounts are
normally stored (say a personal and a work account), switched with `gh auth switch`. No `GH_TOKEN`
or `GITHUB_TOKEN` is exported anywhere: an environment token overrides the stored credentials
and would break `gh auth switch` between accounts.

git uses gh for github.com over https through the credential helper in
[git](../git/README.md).
