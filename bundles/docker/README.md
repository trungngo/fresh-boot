# docker

Docker Desktop on desktops (Ubuntu / Debian x86_64, macOS, Windows); Docker Engine with the
compose and buildx plugins on Linux servers. **Opt-in**: no profile selects it, so run `dot apply docker`.

## Installs

| | |
|---|---|
| Ubuntu / Debian desktop, x86_64 | **Docker Desktop only**: `docker-ce-cli` from Docker's apt repository, then Docker's `docker-desktop-amd64.deb`, installed with apt; you are added to the `kvm` group. No Engine, no `docker` group, no services |
| Ubuntu / Debian server (and other architectures) | `docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin` from Docker's apt repository (`download.docker.com`); you are added to the `docker` group; `docker` and `containerd` are enabled and running (systemd only) |
| macOS | the `docker-desktop` cask |
| Windows | `Docker.DockerDesktop` (winget) |

"Latest" is the vendor repository's candidate (the cask's / winget's current version on the
others); `dot apply --upgrade docker` upgrades.

## Why it looks like this

- **Docker's own repository, not Ubuntu's `docker.io`.** Ubuntu's package trails Docker's and
  has no buildx/compose plugins. The repository is a deb822 `docker.sources` with its own
  `Signed-By:` keyring, and the key is checked against its pinned fingerprint
  (`9DC8 5822 9FC7 DD38 854A E2D8 8D81 803C 0EBF CD88`) before anything is installed. The very
  old version of this module used `apt-key add` and an unsigned `add-apt-repository` line;
  `apt-key` was **removed** in Ubuntu 24.04, so that chain died at its first command.
- **The keyring is `/etc/apt/keyrings/docker.asc`**, the name in Docker's instructions and in
  the old module, so a machine set up by either is taken over in place (dot rewrites the key only
  when it differs) instead of being left with two keys.
- **The legacy `/etc/apt/sources.list.d/docker.list`** (apt-key era, or Docker's older
  instructions) is removed when the new source is written (`replaces:`): apt refuses every source
  when two entries for one repository name different keys.
- **New Ubuntu releases.** Docker only builds for some suites. It does publish some that are not
  on its support matrix (25.10 `questing` was one), so dot probes
  `dists/<codename>/Release` and uses the codename when it exists, else `noble`. Debian falls
  back to `bookworm` the same way.
- **The plugins are the point.** Without `docker-compose-plugin` and `docker-buildx-plugin`
  there is no `docker compose` / `docker buildx` (the old module missed them once). Compose v1,
  the hyphenated `docker-compose`, is EOL: the command is `docker compose`.
- **Conflicting packages.** Ubuntu's `docker.io`, `containerd`, `runc`, `podman-docker` conflict
  with Docker's packages; apt removes them while installing. Nothing else here removes packages.
- **Services** are enabled by the packages on Ubuntu already; the `service` steps put a stopped
  or disabled daemon right. They are skipped without systemd (containers, WSL without
  `[boot] systemd=true`), where you start `dockerd` yourself.

## Docker Desktop on Linux

Docker publishes the `.deb` at one fixed URL (`desktop.docker.com/linux/main/amd64/`), always the
current release, and no apt repository for it. The step is a `download` with `package:`, as Zoom's:
apt installs the file (so its dependencies resolve) and dot re-downloads when the server reports a
changed file, so `dot apply --upgrade docker` updates it. No version is written down. It is x86_64
only and needs a desktop session and KVM (`/dev/kvm`; the `kvm` group, which needs a re-login).

**Desktop replaces the Engine on a desktop, it does not sit beside it.** Desktop runs its own
engine in a VM (context `desktop-linux`, socket `~/.docker/desktop/docker.sock`) and bundles
compose and buildx, so the Engine, `containerd.io`, the plugin packages, the `docker` group and
the two services are skipped (`if: not (role == "desktop" and arch == "x86_64")`). The one thing
it takes from Docker's repository is `docker-ce-cli`, the `docker` command, which its package
depends on. Containers run as your user; nothing here is root-equivalent. A machine that already
has the Engine from an earlier apply keeps it (nothing is removed): `sudo apt remove docker-ce
containerd.io` once, and `docker context use desktop-linux`. A desktop on another architecture,
and every server, still gets the Engine.

## Gotchas

- **The `docker` (Engine) and `kvm` (Desktop) groups need a re-login.** dot prints a notice. `newgrp docker` is deliberately
  not run: it execs an interactive subshell, which does nothing useful from a provisioning run.
  Until then, `sudo docker ...` (Engine); Desktop's VM needs `/dev/kvm` and fails to start without `kvm`. Membership of `docker` is root-equivalent on that machine.
- **macOS: the cask was renamed** from `docker` to `docker-desktop` upstream. dot adds `--adopt`
  (the artifact is `Docker.app`), so a Docker.app installed by hand is taken over when it is the
  same version; when it is not, move it aside (the `brew-adopt-conflict` hint says so). If
  OrbStack or colima already provide a `docker` CLI, the cask's binaries conflict with theirs, so
  the step has `unless: command -v docker` and is skipped when any `docker` is on PATH (the old
  module's `which docker ||`).
- **Windows:** Docker Desktop needs WSL 2 (`wsl --install`, then a reboot) and asks for elevation
  itself. The installer puts the installing user in `docker-users`; another user needs adding by
  hand (dot's `user` directive does not exist on Windows).
- **`dot status`** without bundle names also checks opt-in bundles applied by name: after
  `dot apply docker`, docker stays included until `dot remove docker`.
