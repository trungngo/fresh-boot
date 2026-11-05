# unity

[Unity Hub](https://unity.com/download), the official installer and launcher for Unity editors.
Desktops on macOS and Windows.

## Installs

| | how |
|---|---|
| macOS | cask `unity-hub` (dot adds `--adopt`) |
| Windows | winget `Unity.UnityHub` |

## Why only the Hub

Unity's supported way to get an editor is through the Hub: each project pins its own editor
version (`ProjectSettings/ProjectVersion.txt`), and the Hub needs a signed-in Unity account and
an activated licence before an editor runs. Installing an editor from here would mean writing a
version number into this repository (CLAUDE.md, "No pinned versions"), so editors and their
modules (Android, iOS, WebGL build support) are installed from the Hub when a project asks for
them.

## Gotchas

- **Ubuntu**: Unity ships the Hub for Linux only through its own apt repository, and Ubuntu is
  not selected here; the bundle's `when` drops it there.
- **Windows**: the Hub installs for all users, so its installer asks for elevation (a UAC
  prompt) when dot is not run from an elevated terminal.
- **The Unity CLI** (installed by hand, not by this bundle) puts its binaries in
  `~/.unity/bin` and appends `. "$HOME/.unity/env"` to `~/.zshrc`, which is this repository's
  `bundles/zsh/zshrc`: delete that line (it names your home directory and fails
  `test/privacy-check.sh`). The bundle's `path:` step puts `~/.unity/bin` on PATH on macOS
  instead. The old dotbot repo sourced the same file from zshrc.
