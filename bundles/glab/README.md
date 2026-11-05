# glab

The [GitLab CLI](https://gitlab.com/gitlab-org/cli). Opt-in outside the default profiles' set
only if you remove it from `dot.yml`; selected by every profile by default.

## Installs

| platform | from |
|---|---|
| macOS | Homebrew `glab` |
| Debian / Ubuntu | the `.deb` of the latest `gitlab-org/cli` release on gitlab.com (`github_release: { source: gitlab, package: glab }`) |
| Windows | winget `GLab.GLab` |

**Not from Ubuntu's archive.** Questing carried 1.53.0 against 1.116.0 upstream, 63 minor
versions behind, and an EOL release never moves. GitLab publishes a `.deb` per release but no apt
repository, so dot looks up the latest release through the GitLab API, picks the `.deb` for this
architecture by the asset's **name** (the asset URLs percent-encode their dots,
`glab_1%2E116%2E0_linux_amd64%2Edeb`, which is why the old `install.sh` needed Python), checks it
against the release's checksum and installs it with apt. A plain `dot apply` installs a new
release as soon as it is out.

## Links

- `~/.config/zsh/conf.d/glab.zsh` -> `glab.zsh`: zsh completion.

## Authentication

Interactive, once per machine. The bundle runs

    glab auth login --use-keyring

(without `--use-keyring` on a server, which has no Secret Service) unless
`glab auth status --hostname gitlab.com` already succeeds. glab asks for a browser OAuth flow or
a pasted token and stores it in the system keyring (Windows: Credential Manager). Nothing is
tracked here and no token is ever exported.

For a self-hosted GitLab run `glab auth login --hostname <host>` yourself; inside a checkout of
one of its repositories glab takes the host from the git remote.

- `--use-keyring` is **not** glab's default: without it the token is written in plain text to
  `~/.config/glab-cli/config.yml`. On a server (`role: server`) the flag is left out and glab
  keeps the token in that file (mode 0600, outside this repository).
- **`GITLAB_TOKEN` is never set.** glab reads it for the default host, and an exported empty
  value shadows the keyring credential (gitlab.com answers 401).
- `glab auth login` exits 0 even when a pasted token is rejected and stores nothing; check with
  `glab auth status`.

## Platform notes

- Windows: the login step is PowerShell. A glab that winget installed earlier in the same run is
  found because dot re-reads `PATH` from the registry after every winget install.
- [git](../git/README.md) delegates https credentials for gitlab.com to `glab auth git-credential`.
