# tailscale

[Tailscale](https://tailscale.com): a WireGuard-based mesh VPN that puts this machine on your
tailnet, reachable from your other devices by name wherever they are. Desktops and servers.
**Opt-in**: no profile selects it; `dot apply tailscale`.

## Installs

| | how |
|---|---|
| Ubuntu / Debian | `tailscale` from Tailscale's own apt repository (`package_repo`, key fingerprint pinned, suite `{{ codename }}` with `noble` / `bookworm` as fallback) |
| macOS | cask `tailscale-app` (the standalone app) |
| Windows | winget `Tailscale.Tailscale` |

## Why these sources

Ubuntu's archive has no Tailscale package; Tailscale's repository is upstream's own build and
always current (nothing is pinned: apt takes the candidate). On macOS the `tailscale-app` cask is
the standalone app Tailscale distributes outside the App Store; the `tailscale` formula would be
only the CLI and daemon, without the menu bar app.

## Logging in

Joining the tailnet is a one-time, per-machine browser login, so the bundle does not do it:

    sudo tailscale up          # Linux: prints a login URL
    tailscale status

On macOS and Windows, open the app and sign in. On a headless server, `sudo tailscale up --ssh`
also lets Tailscale SSH replace key management for that host. No auth key is kept in this
repository or its secrets: an auth key in a `shell` step would let any copy of the repository
join machines to the tailnet.

## Gotchas

- **The .deb starts tailscaled** (systemd). In a container or WSL without systemd the daemon is
  not running; start it by hand (`sudo tailscaled --tun=userspace-networking &`).
- **macOS `.pkg`.** The cask installs a package, which runs `sudo installer`: run `dot apply
  tailscale` from a terminal (dot's `cask-pkg-sudo` hint says the same).
- **Other VPNs.** A full-tunnel VPN (an OpenVPN profile, say) can take the routes
  Tailscale needs; if peers go unreachable while it is up, that is why.
