# rectangle

[Rectangle](https://rectangleapp.com): move and resize windows with keyboard shortcuts and snap
areas. The free version, from its Homebrew cask `rectangle` (the app updates itself).

## Installs

| | how |
|---|---|
| macOS | cask `rectangle` (dot adds `--adopt` when the app is already in `/Applications`) |

Nothing is linked: Rectangle keeps its shortcuts and preferences in its own defaults, not in a file
the repository could own.

## Gotchas

- **Accessibility permission.** On first launch macOS asks for Accessibility access (System
  Settings > Privacy & Security > Accessibility). Without it Rectangle cannot move windows.
- **Start at login** is set inside the app (its preferences), not by this bundle.
- **macOS only.** On other systems the bundle is skipped.
