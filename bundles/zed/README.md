# zed

The [Zed](https://zed.dev) editor. Desktop only (`role: desktop`). Works on macOS, Ubuntu
desktop and Windows; **opt-in** everywhere: no profile selects it, `dot apply zed`.

## Installs

- Linux: the latest GitHub release's `zed-linux-<arch>.tar.gz`, as a `download` step: checked
  against the release's published digest, unpacked into `~/.local/zed.app` (swapped in whole on
  an update, so nothing of an old version lingers), and `~/.local/bin/zed` linked to
  `zed.app/bin/zed`. It is skipped while the installed release is the latest. No sudo. A
  `template` writes the desktop entry `~/.local/share/applications/dev.zed.Zed.desktop` with
  absolute paths into `~/.local/zed.app`, which is what upstream's `install.sh` does after
  unpacking.
- macOS: the `zed` cask (dot adds `--adopt`). Windows: winget `ZedIndustries.Zed`.

This replaces the old `install.sh`, which existed only because upstream's installer always
removes and re-extracts `~/.local/zed.app`: it compared `zed --version` with the latest tag
first. The `download` step records what it installed, so the check is built in.

## Files

| destination | how | source |
|---|---|---|
| `~/.config/zed/settings.json` (Linux, macOS) | link | `settings.json` |
| `~/.config/zed/keymap.json` (Linux, macOS) | link | `keymap.json` |
| `%APPDATA%\Zed\settings.json`, `keymap.json` (Windows) | link | same |

Zed uses `~/.config/zed` on macOS too (not Application Support). Linked, so changes made from
Zed's UI land in this bundle.

## Tab jumps between splits

`tab` moves to the next pane, matching IDEA and VS Code.

It sits in its own block with context `VimControl && !menu`, deliberately mirroring Zed's stock
`"tab": "vim::Tab"` binding. Matching the default's context exactly removes any question of
precedence: a broader or narrower context leaves it to Zed's resolution rules, and this key is
used too often to leave to chance.

## Markdown

| key | effect |
|---|---|
| `<Space>p2` | preview to the side (`markdown::OpenPreviewToTheSide`) |
| `<Space>p3` | preview (`markdown::OpenPreview`) |

**There is no `<Space>p1`.** The other editors bind it to "editor only", but Zed has no such
action: its preview opens as a separate tab rather than a mode of the current one, so the
equivalent is closing the preview tab. Toggling in place is an open upstream request.

Zed also has no setting to open `.md` in preview by default, unlike the
`workbench.editorAssociations` entry in [vscode](../vscode/README.md) and the
`MarkdownSettings.splitLayout` written by [idea](../idea/README.md). Also an open request.

## Notes

- `settings.json` still carries JSON comments (Zed accepts them); `keymap.json` does not.
- `vim_mode` also enables Zed's stock vim keymap, which provides the `ctrl-w` window commands;
  `keymap.json` adds the `<Space>` leader bindings ported from IdeaVim
  ([vim](../vim/README.md) `ideavimrc`). Shared keys: [docs/keymap.md](../../docs/keymap.md).
- Never observed on a GUI yet (old TODO): the `tab` binding and `<Space>p2/p3`.
