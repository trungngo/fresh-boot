# blender

[Blender](https://www.blender.org), the 3D creation suite. Desktops only (`role: desktop`).
**Opt-in**: no profile selects it; `dot apply blender`.

## Installs

| | how |
|---|---|
| Ubuntu desktop | the `blender` snap (classic), published by the Blender Foundation |
| macOS | cask `blender` (dot adds `--adopt`) |
| Windows | winget `BlenderFoundation.Blender` |

Nothing is linked: Blender keeps only its own generated settings.

## Why the snap

The Blender Foundation publishes the snap itself and it tracks the latest stable release; Ubuntu's
apt `blender` lags several releases behind. Classic confinement lets add-ons, Python and render
engines reach GPU drivers and the whole filesystem. `snapd` comes from
[common](../common/README.md). On Windows `BlenderFoundation.Blender` tracks the newest release;
the `.LTS.4.x` IDs would pin a series.

## Gotchas

- **snapd needs systemd as PID 1**: the Linux step is guarded with `when: { init: systemd }`, so
  in a container or WSL without systemd it is skipped.
- **Never apt.** The snap is `fallback: false`: where snapd is not running, dot must not install
  the outdated apt `blender` under the same name; the step fails saying snapd is missing.
- On a Mac that already has Blender in `/Applications`, `--adopt` fails when that copy's version
  differs from the cask's: move the app aside and re-run (dot's `brew-adopt-conflict` hint).
