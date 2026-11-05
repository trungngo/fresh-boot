# flameshot

Flameshot on a Linux or Windows desktop, with the `Print` key bound to `flameshot gui` on GNOME
and set as Flameshot's own hotkey on Windows. Selected by the desktop and windows profiles; the
bundle's `when` drops it on macOS, which uses its built-in capture (`Cmd+Shift+5`, `Cmd+Shift+4` for a region, Markup to annotate).

## Installs

| step | how |
|---|---|
| Flameshot | apt `flameshot` (Ubuntu / Debian archive); winget `Flameshot.Flameshot` on Windows |
| `Print` key (Windows) | Snipping Tool's Print key turned off; Flameshot (which registers `Print` itself) started at sign-in; OneDrive's screenshot option off by hand (below) |
| `Print` key | a GNOME custom shortcut `Flameshot` running `flameshot gui`, set with `gsettings` |

## The Print binding

GNOME Shell's own screenshot UI (`org.gnome.shell.keybindings show-screenshot-ui`) holds `Print`,
and the shell grabs its keys before any custom shortcut, so the step first unbinds it. GNOME's
`Shift+Print` (full screen) and `Alt+Print` (window) are left alone. It then writes the custom
shortcut at `/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/flameshot/` and
appends that path to `custom-keybindings`, keeping any shortcuts already there. dot has no
gsettings directive, hence a `shell` step; its `unless:` checks all four values, so changing the
shortcut by hand is undone by the next `dot apply`.

## Windows

Flameshot for Windows always registers `Print` as its capture key (its `GlobalShortcutFilter`,
besides the configurable `TAKE_SCREENSHOT` shortcut, which defaults to Win+Shift+X there), but
only while it runs in the tray. The bundle:

1. turns off Windows 11's "Use the Print screen key to open screen capture" (`HKCU\Control
   Panel\Keyboard` `PrintScreenKeyForSnippingEnabled` = 0; Settings > Accessibility > Keyboard),
   which otherwise hands `Print` to the Snipping Tool first. It takes effect at the next sign-in
   (or an Explorer restart);
2. sets `startupLaunch=true` (`[General]`) in `%APPDATA%\flameshot\flameshot.ini`, keeping its
   other keys, and the `HKCU\...\Run` value `Flameshot` that Flameshot's own "Launch at startup"
   writes, so it is in the tray after every sign-in;
3. restarts Flameshot, or starts it.

**OneDrive takes `Print` too**, and that one is by hand, once per machine: with "Save screenshots
I capture to OneDrive" on, OneDrive hooks the key and nothing else sees it (Flameshot still holds
the hotkey, and pressing `Print` does nothing). Turn it off in OneDrive > Settings > Sync and
backup > Advanced settings. OneDrive keeps that switch in its own settings database, not the
registry, so dot cannot set it. `Win+Shift+S` still opens the Snipping Tool.

## Gotchas

- **gsettings needs the desktop session.** The step writes through the user's D-Bus session
  (dconf). Run `dot apply` from a terminal in the desktop session; over SSH with nobody logged in
  graphically, `gsettings set` fails and the step reports it. It is skipped on a desktop without
  GNOME Shell (KDE and others bind keys their own way).
- **Wayland**: flameshot captures through the desktop portal, which may ask for screenshot
  permission the first time.
- **Moved out of common**: machines set up before keep the package and the binding; nothing is
  removed.
