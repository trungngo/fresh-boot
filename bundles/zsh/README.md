# zsh

The login shell, two plugins, the starship prompt, and `~/.zshrc`. This bundle is the **only**
thing that owns `~/.zshrc`; every other bundle reaches the shell through dot (see "The shell
contract"). There is no oh-my-zsh and no plugin manager: nothing is git-cloned.

## Installs

| | |
|---|---|
| Linux | `zsh`, `zsh-autosuggestions`, `zsh-syntax-highlighting` (apt); zsh made the login shell with `user: { shell: zsh }` (replaces `sudo usermod -s $(which zsh)`) |
| Linux | [starship](https://starship.rs): `github_release` of `starship/starship`, the static musl build for the CPU (`starship-x86_64-unknown-linux-musl.tar.gz`, `starship-aarch64-unknown-linux-musl.tar.gz`) into `~/.local/bin`, checked against the release's digest |
| macOS | `zsh`, `zsh-autosuggestions`, `zsh-syntax-highlighting`, `starship` (Homebrew); zsh made the login shell as `{{ homebrew_prefix }}/bin/zsh`: `/opt/homebrew/bin/zsh` (Apple silicon) or `/usr/local/bin/zsh` (Intel) |

Why these sources: the two plugins are packaged under the same names in Ubuntu/Debian and
Homebrew, so the package manager keeps them current. starship is in Homebrew, but Ubuntu only
packages it from 24.10 and lags behind, so Linux takes upstream's release (static musl, one asset
per CPU for every distro); `dot apply --upgrade` moves it to the latest release.

A login-shell change takes effect at the next login (dot prints a notice). `user:` looks the
shell up in `/etc/shells` and adds it there when missing, which is what Homebrew's zsh needs on
macOS; a plain `shell: zsh` there would keep `/bin/zsh` (same name, already listed), so the macOS
step spells out the Homebrew path. macOS already logs in with zsh, so the only reason to switch
is Homebrew's newer build (the old repo's choice, kept).

## Links and files

- `~/.zshrc` -> `zshrc`
- `~/.zshenv` (Linux): a managed `dot:zsh` block. When an interactive shell starts with a
  `TERM` this box has no terminfo entry for (`xterm-ghostty` on a stock Ubuntu), it falls back to
  `xterm-256color`; a known `TERM` is never touched. Without an entry, zsh, Claude Code, vim and
  tmux mis-handle completion, keys and paste. The proper fix is the entry: Ghostty installs it on
  `ssh` (`shell-integration-features = ssh-terminfo`, ghostty bundle), or by hand:
  `infocmp -x xterm-ghostty | ssh host -- tic -x -`. The rest of `~/.zshenv` is left alone.
- `~/.local.zshrc`: created empty, never tracked, never overwritten; sourced last, so it wins.
- `~/.config/zsh/conf.d/`: created; other bundles link `<name>.zsh` here. Dangling links in it
  (a bundle file renamed or deleted) are removed by a `clean` step, and zshrc skips them anyway.
- `~/.cache/zsh/`: made by zshrc for the completion dump (`zcompdump-<version>`) and cache.
- starship reads `~/.config/starship.toml`; none is shipped (the defaults), so a machine may add
  one without touching the repo.

## The shell contract

zshrc does nine things, in this order:

1. **PATH and environment from dot.** It sources `dot env --shell zsh`: every non-secret variable
   (`MY_NAME`, `MY_EMAIL`, `MY_MACHINE`, `MYPROJECTS_DIR`, ...)
   plus everything bundles declared with `path:` / `env:` steps, through `source "$(dot env
   --shell zsh --cache)"`: dot keeps the output in `~/.cache/dot/env.zsh` and writes it again
   only when its state, `~/.config/dot/local.env`, the repository's `dot.yml` / `.env*` or the
   `dot` binary changed. `~/.local/bin` is put on PATH first, because that is where `dot` itself
   lives.
2. **Options and history**: no beeps, `auto_cd`, `auto_pushd`, comments on the command line;
   `~/.zsh_history` with 50000 lines in memory / 10000 saved, timestamps, duplicates dropped,
   ` cmd` (leading space) kept out, shared between shells.
3. **Keys**: the emacs keymap (`bindkey -e`: zsh would pick vi mode from `EDITOR=vim`), Up/Down
   search history for what is typed so far, Home/End/Delete/Shift-Tab from terminfo,
   Ctrl-Left/Right by word, Ctrl-R, `magic-space`, Ctrl-X Ctrl-E edits the line in `$EDITOR`.
4. **Completion**: `compinit` (dump in `~/.cache/zsh`), a menu you move through, case-insensitive
   and partial-word matching. Homebrew's `share/zsh/site-functions` goes on `fpath` first.
   `docker completion zsh` and `kubectl completion zsh` when those commands exist.
5. **Aliases and functions**: coloured `ls` / `grep`, `l` / `ll` / `la`, `...`, `d`, `md`; the
   everyday aliases of oh-my-zsh's git plugin (`g ga gaa gapa gb gba gc gcmsg gco gcb gsw gswc
   gd gds gf gl gp glog gloga grb grbi gst gss gsta gstp`), its tmux ones (`ta tl ts tkss`),
   `k` for kubectl; and **`reload`** (`exec $SHELL -l`), which replaced `shell-reload.sh`: a
   script runs in a child process and cannot replace the shell that started it.
6. **Prompt**: `starship init zsh`; a plain `➜ dir` prompt until starship is installed.
7. `~/.config/zsh/conf.d/*.zsh` in name order (a file that must run early or late can be named
   `00-x.zsh` / `99-x.zsh`). They run after `compinit`, so they may call `compdef`.
8. **Plugins**: `zsh-autosuggestions` then `zsh-syntax-highlighting`, from
   `$HOMEBREW_PREFIX/share/<name>/` or `/usr/share/<name>/`, whichever exists. Syntax
   highlighting wraps the widgets defined before it, so it comes after conf.d.
9. `~/.local.zshrc`.

After editing a file by hand, run `reload`.

So a bundle never edits zshrc: PATH -> `path:`, environment -> `env:`, anything else (`eval
"$(tool init)"`, completions, aliases, functions) -> `bundles/<name>/<name>.zsh` linked to
`~/.config/zsh/conf.d/<name>.zsh`, every line guarded (`command -v`, `[[ -d ]]`), because the file
may be linked before the tool exists. Secrets are never in any of it: dot does not write sensitive
values into `dot env`, and nothing exports `GH_TOKEN` / `GITLAB_TOKEN` (they shadow the keyring
logins of gh and glab).

## What oh-my-zsh did, and where it went

The old zshrc loaded oh-my-zsh with the `robbyrussell` theme and `git tmux knife docker gitignore
ruby rake bundler rails node yarn ng npm kubectl mvn aws kops python spring`.

| oh-my-zsh | now |
|---|---|
| `lib/history.zsh`, `lib/key-bindings.zsh`, `lib/completion.zsh`, `lib/directories.zsh`, `lib/theme-and-appearance.zsh` | zshrc sections 2 to 5 (the parts listed above) |
| `robbyrussell` theme | starship |
| completions of git, npm, yarn, mvn, ... | zsh's own `_git` and friends, and what each tool installs into `site-functions` / `vendor-completions` |
| `docker`, `kubectl` plugins | `docker completion zsh`, `kubectl completion zsh` in zshrc; `k` alias |
| `git`, `tmux` plugins' aliases | the common ones, in zshrc; the rest are gone (`alias` lists what exists) |
| `gitignore` (`gi`), `knife`, `ruby`, `rake`, `bundler`, `rails`, `node`, `ng`, `aws`, `kops`, `python`, `spring` | dropped: a machine that wants one adds it to `~/.local.zshrc` |
| `omz update` | `dot apply --upgrade` (packages, starship) |

## Where the old monolithic zshrc went

| old zshrc | now |
|---|---|
| `brew shellenv` | common: `path:` + `env:` (`HOMEBREW_*`) |
| `MY_NAME`, `MY_EMAIL` | dot.yml prompt vars, kept in `~/.config/dot/local.env`, exported by `dot env` |
| `MYPROJECTS_DIR` | common `env:` (from the `projects_dir` var) |
| `MY_MACHINE` (was appended to `~/.local.zshrc` by `_machine.sh`) | dot.yml prompt var, kept in `~/.config/dot/local.env`, exported by `dot env` |
| `VISUAL` / `EDITOR` | vim `env:` |
| `PATH=~/.dotfiles/src/scripts`, `~/.scripts` + `.activate.sh` (`mux-new`, `mux-kill`) | gone: the helpers are `tn` ([docs/tn.md](../../docs/tn.md) §8), `tn tmux new` / `kill`; the tn bundle retires the old `~/.scripts` link |
| `shell-reload.sh` | the `reload` function in zshrc |
| `/snap/bin` | common `path:` (appended) |
| `~/bin` (one-off local binaries; devtunnel) | kept in zshrc when it exists, after `~/.local/bin`; devtunnel itself now goes to `~/.local/bin` (vscode, which removes the old `~/bin/devtunnel`) |
| fnm, `~/.npm-global/bin` | nodejs |
| SDKMAN init | gone: Java is Temurin from the package manager; `JAVA_HOME` in java (`java.zsh`) |
| pyenv | gone: python is uv (completions in `python.zsh`) |
| `CARGO_HOME`, `~/.cargo/bin` | rust `env:` / `path:` |
| `DOTNET_ROOT`, `~/.dotnet`; `/usr/local/go/bin` | dotnet; go (opt-in bundles) |
| gh completion | gh (`gh.zsh`) |
| glab completion | glab (`glab.zsh`) |
| `/usr/local/bin` prepended, `AWS_CONFIG_FILE`, rbenv, jenv, protoc, pnpm (`/home/me/...`), Unity (`/Users/me/.unity/env`) | dropped (see common's README); a machine that needs one uses `~/.local.zshrc` |

The pnpm and Unity lines are a warning: their installers appended them to the symlinked zshrc,
dirtying this repository, which is exactly what the contract prevents.

## Gotchas

- **Installers that write into `~/.zshrc`** must be stopped with their flag (fnm `--skip-shell`,
  rustup `--no-modify-path`, SDKMAN `?rcupdate=false`; Codex and devtunnel only when their bin
  directory is already on PATH). See CLAUDE.md. `git status` in the repo shows it when one slips.
- **`bindkey -e` is not optional.** zsh chooses the vi keymap at startup when `VISUAL` / `EDITOR`
  contains `vi`, and the vim bundle exports `EDITOR=vim`; oh-my-zsh used to hide that.
- **compinit before conf.d.** gh's and glab's completion scripts call `compdef`, which only
  exists after `compinit`. A conf.d file must not run `compinit` again.
- `compinit -i` skips group-writable completion directories silently instead of asking
  ("insecure directories"), which Homebrew's often are on a multi-user Mac.
- A `~/.oh-my-zsh` **symlink** (the old repo's vendor/ layout) is removed by
  `absent: { ~/.oh-my-zsh: { only: link } }`. A real `~/.oh-my-zsh` checkout (an earlier
  an earlier version cloned one) is left alone and no longer read: delete it by hand.

