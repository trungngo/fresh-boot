# vscode

[Visual Studio Code](https://code.visualstudio.com/). Selected by every profile: mac,
ubuntu-desktop, ubuntu-server and windows.

**On a headless server** (`role: server`) it installs only the remote half: the `code` package
(for its CLI), the tunnel service (so vscode.dev reaches the machine), devtunnel, and the tn
plugin behind `tn tunnel` (port forwards). The settings links and the extension set are `role:
desktop` steps: a server's extensions live in the VS Code server that a remote client installs.
The old repo ran this module's linux build on every host, servers included; the `code` package
pulls in its GUI libraries there too, as it did then.

## Installs

| | Linux (apt) | macOS | Windows |
|---|---|---|---|
| VS Code | `code` from Microsoft's apt repository | cask `visual-studio-code` | winget `Microsoft.VisualStudioCode` |
| extensions | `package: { vscode: [...] }` (`code --install-extension`) | same | same |
| tunnel service | `code tunnel service install` (systemd --user) | same (launchd) | not set up |
| devtunnel CLI | `download` of Microsoft's binary + apt `libsecret-1-0` | cask `devtunnel` | winget `Microsoft.devtunnel` |

**The apt repository is bootstrapped, not managed.** The `code` package maintains
`/etc/apt/sources.list.d/vscode.sources` itself ("THIS FILE IS AUTOMATICALLY CONFIGURED"), so the
`package_repo` step has `if_missing: true`: it writes the file only on a fresh machine. It uses
the package's own keyring path, `/usr/share/keyrings/microsoft.gpg`, so the two never disagree on
`Signed-By` (apt refuses every source when two entries for one repository name different keys).
The key is pinned by fingerprint (`BC52 8686 B50D 79E3 39D3 721C EB3E 94AD BE12 29CF`,
"Microsoft (Release signing)"). dot refreshes apt before trusting the candidate version, which is
what the old `refresh_apt` helper did by hand.

On Windows, winget's user-scope install puts `code` in
`%LOCALAPPDATA%\Programs\Microsoft VS Code\bin` and adds that to the user PATH. dot re-reads PATH
from the registry after every winget install, so the extensions step finds `code` in the same run.

## Links: this is the sync mechanism

- `settings.json`
- `keybindings.json`
- `snippets/`

All three are symlinked from VS Code's user config directory (`{{ config_dir }}/Code/User`:
`~/.config/Code/User` on Linux, `~/Library/Application Support/Code/User` on macOS,
`%APPDATA%\Code\User` on Windows) into this bundle, so **changing a setting in VS Code writes
straight into `bundles/vscode/`**. There is no export step: edit in the UI, then `git status` shows
the change, and committing syncs it to your other machines, where the same symlinks pick it up. On
Windows without Developer Mode, dot copies the two files instead of linking them (and links the
directory as a junction); UI changes there then do not reach the repository.

Generated state (`globalStorage`, `workspaceStorage`, `History`, `profiles`) is deliberately not
tracked; VS Code rewrites it constantly and none of it is configuration.

## Extensions

The tracked set is the `VS Code extensions` step in `bundle.yml` (it replaces `extensions.txt` and
`extensions.sh`). Anything listed that is missing is installed; extras a machine carries are left
alone. There is no `--prune`: compare by hand with

    code --list-extensions

and add what should be everywhere to the list.

## Tunnel

The tunnel step installs the VS Code tunnel as a background service, so this machine stays
reachable from vscode.dev without holding a terminal open. Without it, a tunnel lives only as long
as the `code tunnel` process that started it. It registers with `systemd --user` on Linux and
launchd on macOS, with **no sudo** either way. The tunnel name defaults to the hostname. `code
tunnel service install` writes its own unit, which is why this is a `shell` step (with `only_if` / `unless` guards) and not a
`service:` step.

**Authentication is not automated.** `code tunnel user login` is an interactive browser flow and
is needed once per machine. Until then the step is skipped by its `only_if:` guard (`code` on
PATH and `code tunnel user show` succeeding), so a provisioning run never hangs on a prompt; run
the login, then `dot apply vscode`. Its `unless` makes it a no-op once the service is installed.

The step also runs `loginctl enable-linger "$USER"`. A `systemd --user` service stops when the
user logs out of every session, so without lingering the tunnel would die at the login screen and
after a reboot, which defeats the point of installing it as a service. That part is non-fatal:
some machines need a polkit prompt a provisioning run cannot answer.

Worth stating plainly: **this machine is reachable from vscode.dev whenever it is powered on**,
logged in or not, tied to the GitHub account you authenticated with (`code tunnel user show` says
only "GitHub Account"; confirm which at https://github.com/settings/security-log).
`loginctl disable-linger "$USER"` reverts the persistence; `code tunnel service uninstall` removes
the tunnel entirely; `code tunnel service log` shows what it is doing.

## Port forwarding: a different thing from the tunnel above

The tunnel makes *this machine's editor* reachable at vscode.dev. Port forwarding exposes *one
running server's port* to the internet and gives back a link. Same service underneath (Microsoft
dev tunnels), different feature, separate lifetime.

VS Code does it from the PORTS panel, but the `code` CLI does not: `code tunnel` has only
prune/kill/restart/status/rename/unregister/user/service. The CLI that can is Microsoft's
`devtunnel`, and what it starts appears in the PORTS panel like anything else.

    tn tunnel open 3000               # prints https://<id>-3000.<cluster>.devtunnels.ms
    tn tunnel open 3000 --for 2h      # closes itself after two hours
    tn tunnel open                    # the [tunnel] ports of the project's tn.toml
    tn tunnel ls                      # PORT ACCESS AGE EXPIRES LABEL CONTEXT LINK
    tn tunnel close 3000              # or --all; no port: pick one

`tn tunnel` is this bundle's tn plugin (`plugin.py`, copied to
`~/.local/share/tn/plugins/vscode.py`; the full contract is [docs/tn.md](../../docs/tn.md) §7.4).
It replaces the old `port-forward`, `port-list` and `port-stop` scripts, with no aliases. The
`port-forward` Claude skill in [claude](../claude/README.md) drives it through `--json`.

- **Private by default.** The link works from anywhere, but only after signing in to the account
  that started it. `--public` (devtunnel's `--allow-anonymous`) lets anyone with the link in; it
  is per forward and never remembered. A private link cannot be curl'ed: API clients use
  `devtunnel token <id> --scopes connect` and the header `X-Tunnel-Authorization: tunnel <token>`.
- **It returns to the prompt.** `devtunnel host` is a foreground process; tn starts it detached
  (its own session on Unix, `DETACHED_PROCESS` on Windows, so closing the terminal does not take
  it down), in the state directory rather than your cwd (so the directory you ran it from can
  still be removed, even on Windows), watches its log for up to 45 s for the link, and prints it. The link is the
  `https://<id>-<port>.<cluster>.devtunnels.ms` URL, not the `-<port>-inspect.` one.
- **Temporary tunnels.** The tunnel exists only while that host process runs, so `devtunnel list`
  (persistent tunnels only) shows nothing: the state files in `~/.local/state/tn/tunnels/`
  (`<port>.json`, and `<port>.log`, kept after close as the record of why a tunnel ended) are the
  truth, and an entry whose pid is gone, or now belongs to some other program (the files
  survive a reboot and pids get reused), is pruned on the next read and never signalled. A second `open` of a live
  port reprints its link; a new `open` after a close gets a new link, never the old one back.
- **`--for 90s|30m|2h|1d|1h30m`** records an expiry and starts a detached watcher (plain Python,
  so it works on Windows too) that closes the tunnel when it expires, unless the tunnel was
  closed, reopened or given a new expiry meanwhile. `tn tunnel ls` and `tn status` also close any
  tunnel past its expiry, in case the watcher died (a reboot, say).
- **Nothing listening** on the port yet is a warning, not an error: the link 502s until a server
  starts there.
- `close` sends SIGTERM, which lets devtunnel remove the tunnel at the service end, and SIGKILL
  after 10 s. On Windows the stop is TerminateProcess, a hard kill that skips devtunnel's
  cleanup, so there (and whenever SIGKILL was needed) tn also runs `devtunnel delete <id>`, the
  id taken from the link, so closed tunnels do not pile up against the account's tunnel limit.
- `tn doctor` checks that devtunnel is installed and logged in; `tn status` prints
  `tunnel  1 open: 3000 https://... (private, 12m)`.

**The two logins are separate.** `devtunnel user login -g` and `code tunnel user login` keep
different token caches even on one GitHub account, so signing in for vscode.dev does nothing for
`tn tunnel` (it exits 3 with `run: devtunnel user login -g`; add `-d`, the device-code flow, on a
machine without a browser). Neither is automated; both are interactive browser flows.
(`devtunnel user show` prints "Not logged in." and still exits 0: match the text, for the
negative, and capture it rather than piping into `grep -q`, which under `pipefail` SIGPIPEs
devtunnel and reads backwards.)

**devtunnel on Linux is a `download`, not Microsoft's installer.** The installer
(`https://aka.ms/DevTunnelCliInstall`) only curls one binary into `~/bin`, then runs `sudo apt-get
update && sudo apt-get install libsecret-1-0`, then appends `export PATH=...:~/bin` to `~/.zshrc`
(a symlink into this repository) when `~/bin` is not on PATH, and chmods the binary last, under
`set -e`, so a failed apt step used to leave a non-executable file that looked installed. The
bundle downloads the same binary
(`https://tunnelsassetsprod.blob.core.windows.net/cli/linux-{x64,arm64}-devtunnel`) straight to
`~/.local/bin/devtunnel` (mode 0755, already on PATH via common) and installs `libsecret-1-0` with
a `package` step. No rc edits, no `~/bin`, no sudo mid-run. A binary the old installer left
in `~/bin/devtunnel` is removed (it would never be updated again; `~/bin` is still on PATH, see the
zsh bundle). The download is re-fetched when the
server's ETag / Last-Modified changes, which replaces the old "re-run the installer when older than
30 days" rule (there is no version endpoint and no self-update). macOS uses the `devtunnel` cask
(a bare binary, so dot does not add `--adopt`), Windows winget.

## Settings

`settings.json` and `keybindings.json` are kept comment-free: VS Code rewrites both when you change
something in the UI, so anything explanatory belongs here instead, where it survives.

### Font sizes

VS Code has **no UI font-size setting**: no `workbench.fontSize`, no `window.fontSize`. The only
lever for the sidebar, tabs and menus is `window.zoomLevel`, which scales in 20% steps and scales
the editor and terminal along with the chrome. So `editor.fontSize` and
`terminal.integrated.fontSize` are **pre-zoom** values:

    rendered = value * 1.2 ^ zoomLevel

At `zoomLevel: 1.5` that is ×1.31: editor 14 renders ~18px, terminal 13 renders ~17px, and chrome
goes ~13px → ~17px. `editor.fontSize: 14` is deliberate, not a typo. Raise `zoomLevel` and the
other two shrink relative to the chrome unless you lower them to match.

`window.zoomLevel` is display-dependent and syncs to every machine through this repository, so a
HiDPI laptop may want a different value. There is no per-machine override today.

### Vim keys handed back to VS Code

`vim.handleKeys` reclaims keys VSCodeVim would otherwise swallow (`vim.useCtrlKeys` defaults true):

| key | why |
|---|---|
| `<C-p>` | Vim's "previous completion" shadows Quick Open |
| `<C-space>` | needed as the window-chord prefix below; VSCodeVim claims it in normal mode |

`<C-d>`, `<C-s>` and `<C-z>` are repeated at the extension's own defaults, because a user-set
object may replace rather than merge with them. Add any other shadowed key with `false`: `<C-f>`
and `<C-a>` are the usual next candidates.

## Keybindings

### Window management is native, not Vim

**All window and view keys are real VS Code keybindings under the `ctrl+space` prefix.** None of
them live in the Vim layer, and that is deliberate.

`<Space>…` mappings are VSCodeVim mappings: they only exist while a **text editor** has focus and
you are in normal mode. Inside a markdown preview, the sidebar, the terminal panel or any webview,
VSCodeVim is not running, so those keys do nothing at all, and window management is exactly what
you need *when you are stuck in one of those panes*. Configuring `<Space>` differently cannot fix
it, because `<Space>` only means something to Vim.

So the split is by capability, not by taste:

| layer | holds | works |
|---|---|---|
| `ctrl+space …` chords | splits, focus, resize, zoom, close, zen, markdown views | **everywhere** |
| `<Space>…` vim mappings | goto, find, refactor, format, run/debug: things that act on a focused editor anyway | text editor, normal mode |

`ctrl+space e` is the escape hatch: it returns focus to the editor from anywhere.

**This diverges from idea and zed on purpose.** Those keep window keys on `<Space>` because their
vim layers behave differently; see [docs/keymap.md](../../docs/keymap.md), which marks the
exception.

### Windows: the same prefix as the terminals

`ctrl+space` chords mirror tmux and ghostty (`bundles/tmux/tmux.conf`,
`bundles/ghostty/config`), so splits and navigation feel identical in the terminal and the editor:

| chord | action |
|---|---|
| `\` or `v` | split right |
| `-` | split down |
| `h` `j` `k` `l` | focus left / down / up / right |
| `shift+h/j/k/l` | narrower / shorter / taller / wider, 8 steps per press |
| `tab` | next group |
| `z` | toggle maximize |
| `q` | close editor |
| `shift+tab` | move editor to the next group |
| `shift+z` | zen mode |
| `shift+q` | hide the sidebar |
| `e` | focus the editor: the way out of a preview, sidebar or panel |
| `1` `2` `3` | editor only / editor+preview / preview only |

VS Code's `increaseViewWidth` moves a single small step and has no size setting, so the resize
chords use `runCommands` to fire it eight times per press. That is the only way to get a usable
step; a plain binding moves a barely visible amount.

Two owners had to move for the prefix to work: VS Code's IntelliSense trigger is now
`ctrl+alt+space` (the default is explicitly removed with `-editor.action.triggerSuggest`), and
VSCodeVim hands `<C-space>` back via `vim.handleKeys`.

### Shift+Shift

Double-tap Shift opens Quick Open, IDEA-style. VS Code's keybindings **UI cannot record the same
key twice**: a repeated modifier only works when written by hand in `keybindings.json`.

Watch for misfires in Vim normal mode, where capitals are commands: holding Shift across two
capitals is fine, but tapping it twice can trigger this.

## Markdown

`*.md` opens in Preview by default via `workbench.editorAssociations`. Two ways back:

| key | effect |
|---|---|
| `Ctrl+Shift+V` | toggle preview / source: VS Code's own default, kept because it fires regardless of vim mode or which pane has focus |
| `<Space>p1` | editor only (`workbench.action.reopenTextEditor`, which overrides the association) |
| `<Space>p2` | editor and preview side by side |
| `<Space>p3` | preview only |

The `<Space>` mappings are vim normal-mode only, so they will not fire while the preview pane
itself holds focus. From inside a preview use `Ctrl+Shift+V`, or the global chords
`ctrl+space 1/2/3`, or `ctrl+space e` to jump back to the editor first.

## Tab jumps between splits

`<Tab>` moves to the next editor group, matching IDEA's `nnoremap <Tab> <C-W><C-W>`.

It is bound **twice on purpose**. The vim mapping alone is not reliable: VSCodeVim's own `tab`
binding carries `!inlineEditIsVisible` in its `when` clause, so whenever an inline suggestion is
showing (`anthropic.claude-code` offers them) Tab is swallowed to accept the suggestion and never
reaches the vim layer. A user keybinding in `keybindings.json` outranks an extension's and has no
such guard, so it fires regardless.

The keybinding is scoped to `vim.mode == 'Normal'`, so accepting a suggestion with Tab still works
normally in insert mode.

## Vim keymap

Ported from `bundles/vim/ideavimrc` so the same muscle memory works in IDEA and VS Code. Leader is
`<Space>` in both; `ctrl+space` stays the window prefix, a deliberately separate layer.

Easymotion is `<Space><Space>` on both sides: VSCodeVim hardcodes `<leader><leader>` and cannot be
remapped, so the ideavimrc override was removed to let IdeaVim use its default too.

**IDEA's refactoring family collapses.** `ExtractMethod`, `ExtractInterface`, `IntroduceVariable`,
`MemberPullUp`, `ChangeSignature`, `SafeDelete` and friends have no discrete VS Code commands: they
all live behind `editor.action.refactor`, and what it offers depends on the language server. So the
family heads `<Leader>a`, `<Leader>e`, `<Leader>i`, `<Leader>m` open that menu rather than fifteen
keys doing the same thing. `<Leader>rr` stays discrete because `editor.action.rename` exists.

Not ported, for lack of any VS Code equivalent:

- `<Leader>gr`: GotoRelated has no VS Code concept
- `<Leader>cg`: was a Case Conversion plugin action
- `<Leader>jc` / `jac` / `jam`: Jupyter, needs `ms-toolsai.jupyter` (not in the extension list)

## Never observed on a GUI (from the old TODO)

- Tab jumping between splits while an inline suggestion shows (insert mode still takes Tab).
- `<Space>p1/p2/p3`, `Ctrl+Shift+V` with `*.md` pinned to the preview editor, and `ctrl+space`
  chords inside a markdown preview (webviews can swallow keys; if they do, a non-chord key such as
  `F4` forwards more reliably).
- The 8-steps-per-press resize is a guess at "about 10 columns"; adjust to taste.
