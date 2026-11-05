# ghostty

The [Ghostty](https://ghostty.org) terminal. Desktop only (`role: desktop`), Linux and macOS.

## Installs

- macOS: the `ghostty` cask (dot adds `--adopt`).
- Ubuntu / Debian: Ghostty is not packaged by either and has no apt repository.
  [mkasberg/ghostty-ubuntu](https://github.com/mkasberg/ghostty-ubuntu) publishes a `.deb` per
  release instead; a `github_release: { package: ghostty }` step installs the latest one through
  apt (so its dependencies are resolved) and skips while that release is installed.
  `dot apply --upgrade` is not needed for it: every apply compares with the latest release.

## Files

| destination | how | source |
|---|---|---|
| `~/.config/ghostty/config` | link | `config` |

Ghostty reads `~/.config/ghostty/config` on macOS too.

## Gotchas carried over

- **Asset names carry the distribution release.** They are
  `ghostty_<version>_<arch>_<release>.deb`, where `<release>` is the Ubuntu version number
  (`24.04`, `25.10`, `26.04`) or the Debian codename (`trixie`, `forky`), and `<arch>` is dpkg's
  (`amd64`, `arm64`). The bundle picks by the `version` fact on Ubuntu and the `codename` fact on
  Debian, per CPU. A release the project does not build for fails the step (nothing falls back to
  another release's build); check the releases page.
- **Version spelling.** The file name spells the Debian revision `1.3.1-0.ppa2`, dpkg records
  `1.3.1-0~ppa2` and the tag is `1.3.1-0-ppa2`. dot considers the package current from its own
  record of what it installed, so a Ghostty installed by hand (or by the old dotbot script) is
  reinstalled once, then recorded.
- **Resize amounts are pixels, not cells.** `resize_split:left,100` is about 10 columns at
  `font-size = 17`; vertical uses 200 for about 10 rows. Kitty and tmux count cells, so the
  numbers are deliberately different. Both are guesses at "about 10 columns"; adjust to taste.
- **Keys are shared** with tmux, vim/IdeaVim, VS Code and Zed (`ctrl+space` chord prefix,
  standing in for vim's `<Space>` leader, which cannot lead in a terminal). See
  [docs/keymap.md](../../docs/keymap.md).
