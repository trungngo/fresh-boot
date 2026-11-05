# Provisioning a new Windows machine

This sets up a fresh Windows 10 / 11 machine with the `windows` profile. **Windows is the least
tested platform**: dot's Windows code is exercised by CI, but the bundles have had little use on
real machines, so expect to fix things the first time (and send the fix back).

Unlike the Ubuntu server and Mac guides, this one is not driven over ssh: `dot apply --host`
supports Linux and macOS remotes only (it needs a POSIX `sh` there). Everything runs **on the
Windows machine itself**, in PowerShell as a normal user (not "Run as administrator"). In the
examples the machine's short name is `W1`.

## 1. Prepare Windows

1. **Developer Mode** on: Settings > System > For developers (Windows 10: Settings > Update &
   Security > For developers). Then dot's `link` steps make real symlinks. Without it, dot copies
   files and makes junctions for directories instead; the copies become links on a later
   `dot apply` once Developer Mode is on, while junctions stay junctions.
2. **winget**: `winget --version`. If it is missing, update "App Installer" from the Microsoft
   Store.

## 2. Run the installer

In PowerShell:

    irm https://raw.githubusercontent.com/trungngo/fresh-boot/main/install/windows.ps1 | iex

It installs Git (winget) and the Visual C++ runtime if missing, clones this repository to
`~\.dot` over https (no login needed), installs `dot` from its public release (checksum
verified) and runs `dot apply`. Piped this way it cannot take arguments; to pass some
(`--upgrade`), save the script and run `.\windows.ps1 --upgrade`.

`dot apply` shows the plan and asks `Apply? [Y/n]`. It asks once for this machine's short name
(`MY_NAME`, `MY_EMAIL`, `MY_MACHINE`: type `W1`), and keeps the answers in
`~\.config\dot\local.env`. Don't pass `--var MY_MACHINE=W1` here: a `--var` value on a local run
is used for that run only, so the next plain `dot apply` would ask again. There is no sudo
password on Windows. Open a new terminal afterwards, so the new Path and PowerShell profile take
effect.

The windows profile runs every step in `pwsh` (PowerShell 7); the `common` bundle installs it
with winget, and dot re-reads the Path afterwards.

## 3. Later

    git -C $HOME\.dot pull
    dot apply

`dot apply --upgrade` also upgrades outdated packages; `dot status` shows drift.

## Not yet verified

- line endings: `git clone` on Windows checks files out with CRLF by default
  (`core.autocrlf=true`); whether every tool is happy with LF in the templates, linked configs
  and `tn.cmd` is untried. Clone with `git clone -c core.autocrlf=false` to keep LF;
- dot's Windows code in practice: the live view (ConPTY), the persisted Path write, winget
  handling, the copy-and-junction fallback without Developer Mode, `tn.cmd` and `py install`;
- SmartScreen or Defender reacting to dot.exe;
- Windows on ARM (the installer picks the matching dot build).

## Troubleshooting

| symptom | cause and fix |
|---|---|
| the install is blocked, or `dot.exe` is removed or will not run | `dot.exe` is not code-signed, so Windows Security reports it as a potentially unwanted app. Turn off Windows Security → App & browser control → Reputation-based protection settings → **Potentially unwanted app blocking**, run the installer again, then turn it back on |
| `The term 'dot' is not recognized` after the installer | `install/windows.ps1` adds `%LOCALAPPDATA%\Programs\dot` to your user Path; open a new terminal. If it still fails, add that folder to the Path by hand, or run it by its full path |
| `The term 'dot' is not recognized` | `~\.local\bin` is not on this terminal's Path yet; open a new terminal after the first `dot apply` |
| ``the interpreter `pwsh` is not installed (or not on PATH)`` | PowerShell 7 is missing, or the terminal predates it: `winget install --exact --id Microsoft.PowerShell`, then open a new terminal |
| `winget is not installed yet` in the plan | update "App Installer" from the Microsoft Store |
| `dot apply --host` says it needs a POSIX `sh`, or `MINGW64_NT-... is not supported by --host` | Windows remotes are not supported: follow this guide on the machine itself |
| files are copies, not links | Developer Mode was off: turn it on (step 1) and run `dot apply` again (directory junctions stay) |
| `dot apply` asks for `MY_MACHINE` again | it was given only with `--var`: type it at the prompt once |
