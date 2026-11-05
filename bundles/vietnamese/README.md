# vietnamese

Vietnamese on an Ubuntu desktop (`distro: ubuntu, role: desktop`): the language packs, and Telex /
VNI typing through IBus Unikey; and on Windows, the `vi-VN` language pack and Windows' own
Vietnamese Telex keyboard. Selected by the desktop and windows profiles; the bundle's `when` drops
it on macOS, and its Linux steps do nothing on Debian, whose archive has no `language-pack-*`.

## Installs

| step | how |
|---|---|
| language packs | apt `language-pack-vi` (pulls in `-base`, which generates the `vi_VN.UTF-8` locale) and `language-pack-gnome-vi` (GNOME / GTK translations): what Settings > Language Support installs |
| input method | apt `ibus-unikey` (brings `ibus`) |
| input source | `('ibus', 'Unikey')` appended to `org.gnome.desktop.input-sources sources` with `gsettings` |

Only installing the packs does not change the display language, formats or the login screen:
pick Vietnamese in Settings > System > Region & Language if wanted.

## Windows

| step | how |
|---|---|
| language pack | `Install-Language -Language vi-VN` (the LanguagePackManagement module Settings uses), in an elevated pwsh: one UAC prompt, and the run waits for it. Skipped when `Get-InstalledLanguage` already lists a language pack for `vi-VN` |
| keyboard | Windows 11's built-in **Vietnamese Telex** input method (`042A:{C2CB2CF0-AF47-413E-9780-8BC3A3C16068}{5FB02EC5-0A77-4684-B4FA-DEF8A2195628}`) added to Vietnamese in the user's language list (`Set-WinUserLanguageList`); the plain "Vietnamese" layout that adding the language brings is removed |

Neither changes the display language (`-CopyToSettings` is not passed). **Win+Space** switches
between English and Vietnamese Telex. No third-party IME (Unikey, EVKey) is installed: the
built-in Telex comes with Windows 11. The language pack step needs someone at the machine to
accept the UAC prompt; from a session where nobody is there, the run waits on it.

## Why Unikey

Ubuntu's archive has `ibus-unikey` (and `fcitx5-unikey`), so it comes from the package manager
like everything else. `ibus-bamboo` handles some apps better but is only distributed from a
third-party repository, which this repo does not use (CLAUDE.md: official sources only). IBus is
GNOME's own input framework on Ubuntu, so no `im-config` change is needed.

## Using it

- **Super+Space** switches between the keyboard layout and Vietnamese (Unikey); the top bar shows
  which is active.
- Telex is the default. Unikey's preferences (input method, charset, spelling check, macros) are
  in the input source's menu in the top bar, or `/usr/lib/ibus/ibus-setup-unikey`.

## Gotchas

- **gsettings needs the desktop session.** The input-source step writes through the user's D-Bus
  session (dconf). Run `dot apply` from a terminal in the desktop session; over SSH with nobody
  logged in graphically, `gsettings set` fails and the step reports it. It is skipped on a desktop
  without GNOME's `org.gnome.desktop.input-sources` schema (KDE and others manage input methods
  their own way).
- **Removing the input source by hand** (Settings > Keyboard) is undone by the next `dot apply`:
  the step only checks that Unikey is in the list.
- **A new IBus engine** shows up after logging out and back in if IBus was already running
  without it; on a fresh install the first login has it.
- **Chrome / Electron apps on Wayland** take IBus input only with Wayland IME support on
  (`--enable-wayland-ime`, or the X11 backend); in the browser's address bar Unikey may otherwise
  miss keystrokes.
