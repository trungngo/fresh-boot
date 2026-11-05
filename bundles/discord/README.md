# discord

[Discord](https://discord.com/download), the voice, video and text chat app. Desktops only
(`role: desktop`): macOS, Ubuntu desktop (x86_64) and Windows. **Opt-in**: no profile selects
it; `dot apply discord`.

## Installs

| | how |
|---|---|
| Ubuntu / Debian desktop (x86_64) | Discord's `.deb` (`https://discord.com/api/download?platform=linux&format=deb`), installed as the package `discord` |
| macOS | cask `discord` |
| Windows | winget `Discord.Discord` (Discord's own installer) |

Nothing is linked: Discord keeps its settings with your account.

## Why the .deb

Discord publishes no apt repository; its Linux downloads are the `.deb` and a tarball. The API
URL redirects to the current versioned file on `dl.discordapp.net`, so nothing is pinned. The
`.deb`'s install script adds **no** apt source (it reloads AppArmor and registers the
`discord://` handler), so there is no repository to clash with. The Linux client does not
update itself; when a new build is out it refuses to start until you install it ("Must be your
lucky day"). `dot apply` downloads the file again when Discord's server reports it changed.
Discord publishes no checksum; the download is over https from Discord's own host. The snap
`discord` is community-packaged (Snapcrafters), not Discord's, so it is not used.

## Gotchas

- **x86_64 only on Linux.** Discord ships no arm64 `.deb`; on an arm64 desktop the step is
  skipped. The web app (<https://discord.com/app>) works in a browser.
- **Updating on Linux closes Discord.** The `.deb`'s post-install script kills a running
  Discord and clears every user's `~/.config/discord/Cache` and `GPUCache`.
- **Windows: per user**, under `%LOCALAPPDATA%\Discord`: no UAC prompt. The installer starts
  Discord when it finishes, and Discord adds itself to sign-in startup (turn it off in Discord's
  Settings > Windows Settings).
- **Updates on macOS and Windows** come from Discord itself on launch (the cask is
  `auto_updates`, so `brew upgrade` leaves it alone).
- **An existing Discord** installed by hand: on Linux an installed `discord` package satisfies
  the step; on macOS dot adopts the app already in `/Applications`.
