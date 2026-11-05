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

The bundle only installs glab; it never stops to ask anything. Log in yourself, once per machine:

    glab auth login

glab asks for a browser OAuth flow or a pasted token. Nothing is tracked here and no token is
ever exported. For a self-hosted GitLab use `glab auth login --hostname <host>`; inside a
checkout of one of its repositories glab takes the host from the git remote.

- **`GITLAB_TOKEN` is never set.** glab reads it for the default host, and an exported empty
  value shadows the stored login (gitlab.com answers 401).
- `glab auth login` exits 0 even when a pasted token is rejected and stores nothing; check with
  `glab auth status`.

## Platform notes

- [git](../git/README.md) delegates https credentials for gitlab.com to `glab auth git-credential`.
