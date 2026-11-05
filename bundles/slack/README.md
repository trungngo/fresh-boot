# slack

The [Slack](https://slack.com) desktop client. Desktops only (`role: desktop`).

## Installs

| | how |
|---|---|
| Ubuntu desktop | the `slack` snap |
| macOS | cask `slack` (dot adds `--adopt`) |
| Windows | winget `SlackTechnologies.Slack` |

Nothing is linked. Slack keeps only generated state and workspace sessions (on Linux under
`~/snap/slack/current/.config/Slack`), none of which belongs in a repository.

## Why the snap

Slack retired its apt repository, leaving the snap or a hand-downloaded `.deb` (whose URL carries
the version) as the Linux options. The snap is publisher-verified and updates itself, so nothing
is pinned, like every other bundle. `snapd` comes from [common](../common/README.md).

## Gotchas

- **snapd needs systemd as PID 1.** In a container, or WSL without `[boot] systemd=true`, the
  `snap` binary can be there while `snap install` fails with "System has not been booted with
  systemd as init system". The Linux step is guarded with `when: { init: systemd }`.
- **Never apt.** dot falls back from snap to the distro's manager under the same name when
  snapd is not available, and Debian's `slack` package is an unrelated configuration-management
  tool. The snap is marked `fallback: false`, so that cannot happen: without snapd the step fails
  saying so. Start snapd (`sudo systemctl enable --now snapd.socket`) and re-run `dot apply
  slack`, or install the `.deb` from <https://slack.com/downloads/linux> by hand. snapd that
  `common` installs earlier in the same run is picked up (the step is planned again when it runs).
- On a Mac that already has Slack in `/Applications` from a manual download, `--adopt` fails when
  that copy's version differs from the cask's: move the app aside and re-run (dot's
  `brew-adopt-conflict` hint says the same).
