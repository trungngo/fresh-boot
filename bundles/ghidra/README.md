# ghidra

[Ghidra](https://github.com/NationalSecurityAgency/ghidra), the NSA's open-source software
reverse engineering suite (disassembler, decompiler, scripting). Every platform, **opt-in**: no
profile selects it, so install it with `dot apply ghidra`. It `requires: [java]`: the java
bundle's Temurin JDK (current LTS) is what runs it; Ghidra needs JDK 21 or newer.

## Installs

| | how |
|---|---|
| Linux (desktop and server) | the latest GitHub release's `ghidra_<version>_PUBLIC_<date>.zip`, unpacked into `~/.local/share/ghidra`, `~/.local/bin/ghidraRun` linked to its launcher; on a desktop also `~/.local/share/applications/ghidra.desktop` |
| Windows | the same zip, unpacked into `%LOCALAPPDATA%\ghidra`, and a Start menu shortcut **Ghidra** to `ghidraRun.bat` |
| macOS | Homebrew formula `ghidra` (`ghidraRun` on PATH) |

On a server, use the headless analyzer: `~/.local/share/ghidra/support/analyzeHeadless`.

## Why the release zip

Ubuntu does not package Ghidra and winget has no package for it, but every GitHub release
carries one zip that runs on all three platforms (pure Java plus native decompilers for each).
`download: { release: ... }` takes the latest release's asset (the glob matches whatever version
it carries: nothing is pinned), checks it against the digest GitHub publishes for the asset,
strips the versioned top directory so the install path stays put, and replaces the whole tree on
an update (`dot apply ghidra`, or `--upgrade`), so no file of an older version lingers.

macOS uses Homebrew's formula instead (Homebrew has no Ghidra cask), as the rest of this repo
prefers the package manager on macOS. The formula depends on Homebrew's `openjdk@21`, so a Mac
ends up with that JDK next to Temurin; Ghidra runs on either.

## Not tracked

Ghidra keeps its preferences and per-version settings under `~/.config/ghidra` (Linux, macOS)
or `%APPDATA%\ghidra` (Windows), and projects wherever you create them. Nothing is linked.

## Gotchas

- **Which JDK.** The launcher takes `java` from PATH (then `JAVA_HOME`) and remembers the JDK it
  found. If a newer Temurin moves the JDK, Ghidra asks for its path once at start.
- **A Ghidra unpacked by hand** in `~/.local/share/ghidra` or `%LOCALAPPDATA%\ghidra` is kept as
  `<dir>.dot-backup` on the first run, then replaced by dot's copy.
- **Extensions** installed into the Ghidra tree itself (`Ghidra/Extensions`) are lost when an
  update replaces the tree; install them from the GUI (File > Install Extensions), which puts
  them in the user settings directory instead.
