# godot

The [Godot](https://godotengine.org) game engine editor. Desktops on Linux, macOS and Windows.

## Installs

| | how |
|---|---|
| Ubuntu desktop | the official build from the latest GitHub release of `godotengine/godot`, unpacked into `~/.local/share/godot`, `~/.local/bin/godot` linked to it, and a desktop entry in `~/.local/share/applications/godot.desktop` |
| macOS | cask `godot` (or `godot-mono`) |
| Windows | winget `GodotEngine.GodotEngine` (or `GodotEngine.GodotEngine.Mono`) |

No sudo on Linux: the build is one self-contained executable (the .NET build adds a `GodotSharp/`
directory next to it).

## Why the release build

Ubuntu packages Godot but lags far behind (25.10 carried 4.4.1 while upstream was at 4.7.2). The
`download: { release: ... }` step asks GitHub for the latest release, takes the asset for this CPU
(`linux.x86_64` or `linux.arm64`), checks it against the release's published digest, and replaces
the whole tree on an update, so no file of an older version lingers. `~/.local/bin/godot` follows
the versioned executable name. `dot apply --upgrade godot` (or a plain `dot apply`) moves to a new
release; nothing is pinned.

## The .NET (C#) build

Set the bundle var `godot_mono=true` for this machine, in `~/.config/dot/local.env` or with
`--var godot_mono=true`: macOS then installs the `godot-mono` cask, Windows
`GodotEngine.GodotEngine.Mono` and Linux the `_mono_` asset.
It needs a .NET SDK: `dot apply dotnet`.

## Not tracked

Editor settings (`editor_settings-4.tres`): Godot rewrites the file wholesale, so a link would
fight the editor and churn the repository.

## Gotchas

- 32-bit ARM and x86 Linux builds exist upstream but have no `asset:` entry here: the step fails
  with "no `asset:` pattern for linux/<arch>" on such a machine.
- The desktop entry's `Exec=` is an absolute path (desktop files do not expand `~`), rendered from
  `home` at apply time.
