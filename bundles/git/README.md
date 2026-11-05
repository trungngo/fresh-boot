# git

Global git configuration and the `tn git` commands. git itself is installed by
[common](../common/README.md) (apt, brew, winget `Git.Git`); this bundle only configures it.
Every profile selects it (mac, ubuntu-desktop, ubuntu-server, windows). It requires
[tn](../tn/README.md) (the command) and [projects](../projects/README.md) (whose Python API
the plugin uses for project context, identities and remotes).

## Files

| destination | how | source |
|---|---|---|
| `~/.gitconfig` | `template` | `gitconfig` |
| `~/.gitconfig.local` | `create` (empty, only when missing; never touched again) | |
| `~/.gitignore_global` | `link` | `gitignore_global` |
| `~/.local/share/tn/plugins/git.py` | `copy` | `plugin.py` |
| `~/.config/tn/conf.d/git-forges.toml` | `copy` | `git-forges.toml` |

`~` is `%USERPROFILE%` on Windows, which is where Git for Windows looks too.

## Why a template, and where local settings go

The old module linked `gitconfig` with the identity hardcoded. It is now rendered: `user.name` /
`user.email` come from `MY_NAME` / `MY_EMAIL`: `dot.yml` prompts, asked on the first `dot apply` and kept in
`~/.config/dot/local.env` (never in the repository: docs/private-overlay.md). Change a value
there and `dot apply git` rewrites the file.

Because `~/.gitconfig` is rendered, **`git config --global ...` edits are overwritten** by the
next apply (and show as drift in `dot status`). Put machine-local settings in
`~/.gitconfig.local` instead, which the template includes last so it wins:

    git config --file ~/.gitconfig.local user.email someone@example.com

A machine set up by the old dotbot repo has `~/.gitconfig` as a symlink into that repository; the
template replaces the link with a file and never writes through it.

## Credential helpers

https authentication is delegated to the CLIs, which keep their tokens in the system keyring;
nothing is stored by git or in this repository:

- `gh auth git-credential` for `github.com` and `gist.github.com` ([gh](../gh/README.md))
- `glab auth git-credential` for `gitlab.com` and the self-hosted GitLab
  ([glab](../glab/README.md))

Each section starts with an empty `helper =`, which clears helpers configured earlier (Git for
Windows sets `credential.helper=manager` system-wide; macOS git may use `osxkeychain`) so only the
CLI answers for that host.

The helpers are written **without an absolute path** so they resolve through `PATH`: `/usr/bin/gh`
is right on Linux but wrong on macOS, where Homebrew uses `/opt/homebrew/bin` or
`/usr/local/bin`. `excludesfile` is `~/.gitignore_global` for the same reason: it used to be a
hardcoded `/Users/...` path, which silently disabled the global ignore file on Linux.

dot's own clones use https, never SSH (no SSH keys are assumed on a clean machine; generate one
per machine and register it with `gh ssh-key add` / `glab ssh-key add` if you want SSH). The
remotes `tn git remote add` writes are ssh by default (see "Forges and people" below).

## gitignore_global

Ignores `**/.claude/settings.local.json` (Claude Code's per-user, per-project settings) in every
repository.

## `tn git`

The plugin (`plugin.py`, spec: `docs/tn.md` §7.5) replaces the old `git-*.sh` scripts of the
`scripts` bundle. There are no aliases for the old names. Every command works on the repository
around the current directory (`tn -C <dir> git ...` for another one); `init`, `as --list` and
`ignore --list` work anywhere. `--json` gives machine output, `-n` a dry run.

| command | does | replaces |
|---|---|---|
| `tn git pull [--remote R \| --all]` | `git pull` from the upstream, from R, or from every remote in turn (carries on past a failure, exits 1) | `git-pull.sh`, `git-pull-<forge>.sh` |
| `tn git sync [--remote R]` | pull from every remote (or R), then push the branch to each whose pull worked | `git-sync.sh`, `git-sync-<forge>.sh` |
| `tn git remote add <forge> [--name N] [--path P] [--no-fetch]` | add the forge's remote; the path comes from the project and repo (`{group}/{repo}`); a failed fetch says how to create the repository | `git-remote-{work,bitbucket,github,gitlab}.sh` |
| `tn git remote ls` | remotes with their forge, path and web URL | |
| `tn git open [repo\|pr\|ci\|issues] [--remote R] [--print]` | open the page in a browser (over ssh, or with no display, it only prints the URL) | `git-web-<forge>.sh` |
| `tn git as <person>` / `tn git as --list` | commit as a person in this repo (fuzzy: key, alias, name or email; `me` is MY_NAME / MY_EMAIL) | `git-<person>.sh` (34), `git-me.sh` |
| `tn git whoami` | the identity commits get here (local / global / unset) and the project's expected one | |
| `tn git init [--forge [F]]` | idempotent `git init` + identity + `.gitattributes` (+ remote) | `git-init.sh`, `git-attributes.sh` |
| `tn git ignore <template...>` / `--list` | append GitHub's official templates (`gh api gitignore/templates/<Name>`) to `.gitignore`, once each | `git-ignore.sh` |
| `tn git log [RANGE] [--max-count N] [--author WHO]` | compact log, 20 commits by default | (`git-log.sh` rewrote history; dropped) |
| `tn git changed` | changed and untracked files, staged or not | `git-modified.sh` |
| `tn git authors` | commit counts per author, matched to people | `git-commiters.sh` |
| `tn git export [REF] [-o FILE]` | `git archive` to `<project>/rel/<project>-<repo>-<YYYYMMDD>.zip` | `git-export.sh` |
| `tn git feature new <name> [--from B]` / `feature ls` | `feature/<name>` from `develop` (local or on the primary remote), else the default branch; no git-flow | `git-feature-start.sh`, `git-features.sh` |

`tn status` shows `<branch>, <n> changed, ahead <a>, behind <b>` for the current repo; `tn doctor`
checks that git is installed, that each forge CLI on the machine (`gh`, `glab`) is logged in to
its hosts, and that every repo of a project whose `tn.toml` sets `identity` commits as that person
(fix: `tn -C <repo> git as <key>`).

Gotchas:

- **`-n` is tn's `--dry-run`** (global flags are taken out anywhere before `--`), so `tn git log`
  takes `--max-count N` (or `--limit N`), not `-n N`.
- `tn git open` needs the remote's host in a `[forges.*]` table; a host no forge names exits 1.
- `pull`, `sync` and `feature new` refuse a detached HEAD. "Remotes" leaves out one named `local`,
  as the old scripts did.
- `tn git ignore` needs `gh` (the [gh](../gh/README.md) bundle) logged in; it exits 3 with
  `run: gh auth login` otherwise.

### Forges and people (`conf.d`)

The data the old scripts had baked into their file names is config now, copied (not linked) into
`~/.config/tn/conf.d/`; `~/.config/tn/config.toml` wins over both, so add a forge or a person
there (or `tn config set`) rather than editing the copies.

- **`git-forges.toml`** (public, copied): `gh` (github.com, remote `github`), `gitlab`
  (gitlab.com, remote `gitlab-com`) and `bitbucket` (no CLI). Remotes use the ssh URL
  (`git@host:path.git`), as the old scripts did; set `clone = "https"` on a forge for https
  remotes. The old `git-pull-<remote>.sh` / `git-sync-<remote>.sh` scripts that named only a
  remote, never a host, need no forge: `tn git pull --remote <name>` covers them.
- **`git-private.toml`** (private, not installed: you write it by hand, mode 0600; shape and
  example data in `private.toml.example`): your `owner` on github.com, your Bitbucket `path`
  template, a self-hosted GitLab forge and the people `tn git as` knows (one `[people.<key>]`
  each, so `tn git as <key>` commits as that person). `me` is not listed: tn builds it from
  `MY_NAME` / `MY_EMAIL`. A project's `tn.toml` names one of these keys as its `identity`. Names,
  e-mail addresses and hosts are personal, so they stay out of this repository
  (docs/private-overlay.md).
