# Keymap

Carried over from the old repo's README. The bundles that own these configs (tmux, ghostty, vim,
vscode, zed, idea) must keep them in sync; change a key in all of them or in none.

One key per action, everywhere. Press the tool's prefix first, then the key.

| tool | prefix |
|---|---|
| vim, idea, zed | `<Space>` (vim leader) |
| **vscode** | `ctrl+space` for windows, `<Space>` for editor actions |
| ghostty | `ctrl+space` |
| tmux | `C-a` — see the note below |

**VS Code splits its keymap by capability.** Window and view keys are native keybindings on
`ctrl+space`; editor actions stay on the `<Space>` vim leader. Vim mappings only fire while a text
editor has focus, so window management — the thing you need *when focus is somewhere else* — cannot
live there. The keys after each prefix are unchanged; only which prefix carries them differs.

VS Code also adds `e` (focus the editor, the way out of a preview or panel) and
`shift+tab` / `shift+z` / `shift+q` for move-editor, zen and hide-sidebar, which the other editors
keep under `<Space>w`.

## Windows and panes

| action | key | notes |
|---|---|---|
| split right | `v` or `\` | tmux also accepts `\|` |
| split down | `-` | tmux also accepts `_` |
| focus left / down / up / right | `h` `j` `k` `l` | |
| resize | `H` `J` `K` `L` | shift+hjkl, ~10 columns / rows per press in every tool |
| next pane | `tab` | in editors this is bare `<Tab>`, no leader |
| zoom / maximize | `z` | |
| close | `q` | |
| reload config | `r` | zed hot-reloads instead; vscode has no equivalent |

## Editor and IDE

Terminal multiplexers have no equivalent for these, so they apply to vim, idea, vscode and zed.

| action | key | notes |
|---|---|---|
| goto file | `g f` | vscode also binds `Shift Shift` |
| goto symbol | `g s`, `g c` | |
| command palette | `g a` | |
| goto definition | `g d` | |
| goto related | `g r` | idea and zed only |
| file outline | `s` | |
| find in file / project / usages | `f f` `f a` `f u` | |
| next / prev error | `g e`, `] e` `[ e` | |
| format / organize imports / commit | `c f` `c o` `c p` | |
| rename | `r r` | |
| refactor menu | `a`, `e` `i` `m` | zed has `a` only |
| quick fix | `<CR>` | not in zed |
| theme | `t` | |
| clear search highlight | `t h` | |
| recent projects / switcher | `w p` `w s` | |
| hide panels / zen mode | `w q` `w z` | |
| run / debug / breakpoint | `b r` `b d` `b b` | |
| font size | `=` `-` | not in the terminals |
| easymotion | `<Space><Space>` | idea and vscode; zed uses stock vim |
| markdown view | `p1` `p2` `p3` | editor / editor+preview / preview only. zed has no `p1` |

Plain vim has the window keys and `r`; the IDE actions above are IDE-only.

## Resize steps

Every tool measures resize differently, so the numbers in the configs look inconsistent while the
*result* is the same — roughly 10 columns or rows per press:

| tool | config | unit |
|---|---|---|
| tmux | `resize-pane -L 10` | cells |
| ghostty | `resize_split:left,100` | **pixels** — ~100px ≈ 10 columns at font-size 17; vertical uses 200 for ~10 rows |
| vscode | `runCommands` × 8 | one `increaseViewWidth` is a small fixed step with no size setting |

ghostty is the one to watch: its amount is in pixels, not cells, so a value that looks reasonable
next to the others is nearly invisible on screen.

## Known divergences

**tmux keeps `C-a`.** It cannot share `ctrl+space` with ghostty: a terminal emulator consumes its
own leader before the byte reaches the PTY, so tmux running inside it would never see the prefix.
The keys *after* the prefix are identical; only the prefix differs.

**`next pane` is bare `<Tab>` in the editors** but `<prefix> tab` in the terminals — one keystroke
apart, the last remaining depth mismatch.

**`q` closes, `w q` hides panels.** `q` used to hide panels in the editors while closing a pane in
the terminals; the terminal meaning won.

**`h` moves, it does not split.** It used to split-down in the editors, which is why navigation was
buried under `w`. `-` is now the only split-down key.
