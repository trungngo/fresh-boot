# gimp

[GIMP](https://www.gimp.org), the GNU Image Manipulation Program. Desktops only
(`role: desktop`). **Opt-in**: no profile selects it; `dot apply gimp`.

## Installs

| | how |
|---|---|
| Ubuntu / Debian desktop | apt `gimp` (the distribution's archive) |
| macOS | cask `gimp` (dot adds `--adopt`) |
| Windows | winget `GIMP.GIMP` |

Nothing is linked: GIMP keeps only its own generated settings.

## Why these sources

GIMP's official Linux channel is Flathub; using it would mean adding flatpak and Flathub to
every desktop for one app, so the bundle takes the distribution's own package, which updates with
the system (an older release on an older Ubuntu: 24.04 ships the 2.10 series). The `gimp` snap is
a community build, not upstream's. On Windows `GIMP.GIMP` tracks the newest release;
`GIMP.GIMP.2` and `GIMP.GIMP.3` would pin a major version.

## Gotchas

- Want the newest GIMP on an older Ubuntu: `flatpak install flathub org.gimp.GIMP` by hand
  (and `sudo apt remove gimp`, so the launcher does not show two).
- On a Mac that already has GIMP in `/Applications`, `--adopt` fails when that copy's version
  differs from the cask's: move the app aside and re-run (dot's `brew-adopt-conflict` hint).
