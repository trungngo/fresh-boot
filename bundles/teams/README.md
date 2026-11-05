# teams

Microsoft Teams (work or school). Desktops only (`role: desktop`): macOS, Ubuntu desktop and
Windows. **Opt-in**: no profile selects it; `dot apply teams`.

> **On Linux this is not Microsoft's app.** Microsoft retired its Linux client; what this bundle
> installs there is [teams-for-linux](https://github.com/IsmaelMartinez/teams-for-linux), an
> **unofficial**, community-maintained Electron app that wraps the Teams **web app**
> (<https://teams.microsoft.com>) in a window of its own. It is not affiliated with Microsoft,
> and features are limited to what the web app offers.

## Installs

| | how |
|---|---|
| macOS | cask `microsoft-teams` (Microsoft's `.pkg`; Homebrew asks for the sudo password in the terminal) |
| Windows | winget `Microsoft.Teams` (Microsoft's MSIX, per user) |
| Ubuntu / Debian desktop | **unofficial** `teams-for-linux`: the `.deb` from the project's latest [GitHub release](https://github.com/IsmaelMartinez/teams-for-linux/releases) (`github_release` with `package: teams-for-linux`), x86_64 or arm64 |

Nothing is linked: Teams keeps your sign-in and settings in its own directories.

## Why teams-for-linux, and the release `.deb`

Microsoft discontinued the Teams client for Linux and points Linux users at the web app (a
Progressive Web App in Edge or Chrome). teams-for-linux is the long-standing, widely used
wrapper around that web app, adding a tray icon, notifications and screen sharing; it is the
closest thing to a desktop client.

Its GitHub releases carry `.deb`, `.rpm`, AppImage and tarballs; snap and Flathub builds are
published to the Snap Store and Flathub.
This bundle takes the `.deb` from the project's own releases (the latest stable one; pre-releases
are skipped) rather than the separate apt repository at teamsforlinux.de, which a third party
hosts with its own signing key. The `.deb` adds no apt source (its install script only links
`/usr/bin/teams-for-linux` and installs an AppArmor profile), so a `dot apply` after a new
release moves it on.

If you would rather not run third-party code, skip this bundle on Linux and use
<https://teams.microsoft.com> in a browser ("Install this site as an app" in Chrome or Edge).

## Gotchas

- **macOS 14 or later.** The `microsoft-teams` cask requires it; on an older macOS the step
  fails. Homebrew's cask leaves Microsoft AutoUpdate out; Teams updates itself (its own
  updater daemon), so `brew upgrade` leaves it alone (`auto_updates`).
- **macOS: the sudo prompt.** The cask is a `.pkg`, so Homebrew runs `sudo installer` and asks
  for the password in the terminal; a non-interactive run needs passwordless sudo for it.
- **macOS over ssh** (`dot apply --host`): installing or replacing an app in `/Applications`
  from an ssh session needs App Management permission for `/usr/libexec/sshd-keygen-wrapper`
  (docs/provision-mac.md); otherwise the install fails with "Operation not permitted".
- **Windows: two Teams.** Windows 11 may come with "Microsoft Teams (free)", the consumer app
  (winget `Microsoft.Teams.Free`). That is a different app; this bundle installs Teams for work
  or school (`Microsoft.Teams`) beside it.
- **teams-for-linux sign-in** goes through Microsoft's web login, as in a browser. Some tenants'
  conditional-access policies treat it as an unmanaged browser and block it; then use the web
  app in Edge.
- teams-for-linux's other builds (AppImage, tarball, armv7l) are in the same releases; only the
  amd64 / arm64 `.deb` is installed here.
