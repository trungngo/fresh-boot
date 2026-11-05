# vim

Plain Vim, with no plugin manager and no plugins, plus the IdeaVim config.

## Installs

`vim`: apt, Homebrew, winget `vim.vim` (the `vim` entry of dot.yml's package map). common installs
vim too on Linux and macOS; this bundle says it again so it stands alone and covers Windows.

Nothing else: no vim-plug, no plugin checkouts, nothing fetched at launch. The vimrc uses only
what ships with Vim, including three of its optional packages loaded with `silent! packadd!`
(skipped quietly on a Vim too old to have them):

| package | what | since |
|---|---|---|
| `matchit` | `%` between `if`/`else`/`endif`, HTML tags, ... | Vim 8.0 |
| `editorconfig` | honours `.editorconfig` | Vim 9.0.1799 |
| `comment` | `gc{motion}` / `gcc` toggle comments | Vim 9.1 |

The colour scheme is `habamax` (ships with Vim 9), falling back to `desert` on older builds.

## Links

| | Linux, macOS | Windows |
|---|---|---|
| `vimrc`: core settings, packages | `~/.vimrc` | `~/_vimrc` (Vim on Windows does not read `~/.vimrc`) |
| `before.vimrc`: `<Space>` leader, before any mapping | `~/.before.vimrc` | same |
| `after.vimrc`: maps, functions, overrides | `~/.after.vimrc` | same |
| `ideavimrc`: IntelliJ's IdeaVim | `~/.ideavimrc` | same |

On Windows without Developer Mode, dot copies files instead of linking them (and keeps the copies
in sync).

Also: `~/.local.vimrc`, created empty and never tracked, sourced **last** by vimrc (machine-local
overrides win). The old repo created it but, after oh-my-vim was dropped, nothing sourced it any
more; vimrc does now. `VISUAL=vim` and `EDITOR=vim` are `env:` entries (Linux and macOS), exported
to shells by `dot env` (they were in the old zshrc).

## Keys

Leader is `<Space>`, as in IDEA, VS Code and Zed. The window keys after the leader (`v` / `\`
split right, `-` split down, `hjkl` focus, `HJKL` resize, `Tab` next, `z` zoom, `q` close) are the
ones tmux and ghostty use after their prefix: [docs/keymap.md](../../docs/keymap.md).
`ideavimrc` maps the same keys to IDE actions, plus the IDE-only groups (refactor, goto, find,
build, `p1/p2/p3` preview layouts).

## Why no plugins

Plain Vim for now. The old setup was oh-my-vim +
NeoBundle (archived upstream in 2022; NeoBundle dead since 2018), then vim-plug, which
git-cloned about 30 plugins at first launch: exactly the kind of runtime `git clone` of
third-party code this repository no longer does. What went with them: molokai / solarized,
fzf.vim, NERDTree (netrw's `:Explore` instead), fugitive, gitgutter, surround, repeat,
commentary (Vim 9.1's `comment` package instead), UltiSnips, ALE, vim-tmux-navigator, the
language plugins, and their settings in vimrc.

A plugin that comes back later goes in as a Vim package from a package manager or a copied file,
not a plugin manager that clones at runtime.

## Notes

- `ideavimrc` keeps its `Plug` / `set surround` / `set easymotion` lines: those are IdeaVim's own
  emulated extensions (built into the IDE plugin), not Vim plugins, and download nothing.
- IdeaVim ignores unknown action IDs silently, so a wrong one in `ideavimrc` looks like a dead key.
- `~/.vimrc` is a plain link. It used to be generated with `sed` to bake an absolute `$OH_MY_VIM`
  path into it; nothing needs that now.

## Moving from the old repo

A machine that ran the vim-plug vimrc still has `~/.vim/autoload/plug.vim` and `~/.vim/plugged/`
(`~/vimfiles/...` on Windows). Nothing loads them any more; delete them by hand when convenient.
