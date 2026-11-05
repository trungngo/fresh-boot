# Provisioning a new Ubuntu server from your workstation

Two ways to set up a fresh Ubuntu Server box. On the server itself, the one-liner of the README
(`install/install.sh`) is enough. This guide is the other way: drive the server over ssh from a
workstation (macOS or Linux) that has a checkout of this repository, so the server needs nothing
but ssh. It ends up with the `ubuntu-server` profile: command-line tools only, no GUI apps. The
same for a Mac: [provision-mac.md](provision-mac.md); for Windows, which `--host` does not
support: [provision-windows.md](provision-windows.md).

In the examples the server is `user@server`: the account the Ubuntu installer created, and the
server's address or a `~/.ssh/config` alias. Run the commands from your checkout of this
repository, in a terminal whose `TERM` the server knows (for example `xterm-256color`).

## Quick start

    dot apply --host user@server --repo . --profile ubuntu-server --var MY_MACHINE=S1

It shows the plan, asks `Apply? [Y/n]`, then your sudo password on the server once. `dot` itself
comes from its public release: it is downloaded on the workstation and copied over, and no token
is sent to the server.

## 1. Install Ubuntu Server with ssh key login

In the Ubuntu Server installer, tick **Install OpenSSH server** and **Import SSH key** from
GitHub (give your GitHub user name): the installer adds that account's public keys to the new
user's `~/.ssh/authorized_keys` and turns password login over ssh off. Log in as the user the
installer created. Check from the workstation:

    ssh user@server true && echo ok

If you skipped the key import, log in at the server's console and run
`ssh-import-id gh:<your-github-user>` (or append your public key to `~/.ssh/authorized_keys`).
`ssh-copy-id` does not work while password login is off.

## 2. Optional: your terminal's definition on the server

Skip this from macOS Terminal. If your terminal is Ghostty (or kitty, WezTerm, ...), the server
has no terminfo entry for its `TERM` (`xterm-ghostty`), and zsh completion, keys and paste
misbehave (the zsh bundle falls back to `xterm-256color`). Copy the entry over once:

    infocmp -x xterm-ghostty | ssh user@server -- tic -x -

## 3. Optional: preview

    dot plan --host user@server --repo . --profile ubuntu-server --var MY_MACHINE=S1

This copies dot to the server (`~/.local/bin/dot`), syncs this repository there (`~/.dot`) and
prints the server's plan: bundles in order, what each step would change, which steps need sudo.
Nothing else changes on the server.

`MY_MACHINE` is the server's short name (`S1`, `S2`, ...), used in Claude/Codex session names.
It is per machine, so it is never copied from the workstation: give it with `--var`, or leave
`--var` out and dot asks. `--profile ubuntu-server` is optional: a box with no graphical session
is detected as a server anyway.

## 4. Apply

    dot apply --host user@server --repo . --profile ubuntu-server --var MY_MACHINE=S1

dot shows the plan, asks `Apply? [Y/n]`, then asks for your **sudo password on the server once**,
and runs. Output streams live; the exit code is the server's. `MY_NAME` and `MY_EMAIL` are
forwarded from the workstation's `local.env`, `MY_MACHINE` is saved in the server's. `--yes`
skips the confirmation but also means non-interactive: it fails up front unless sudo works
without a password and the personal variables are already set (docs/private-overlay.md §1).
Leave it out for a first install. Afterwards, log out and back in: zsh became the login shell.

## 5. Later

Change the repository on the workstation, then run the same apply again. It syncs the
repository, upgrades dot on the server when needed, and applies only what differs. Name bundles
to limit the run (`... --var MY_MACHINE=S1 zsh vim`); `--upgrade` also upgrades outdated
packages. On the server itself: `dot status` shows drift, `dot apply` uses `~/.dot`.

## Troubleshooting

| symptom | cause and fix |
|---|---|
| `Permission denied (publickey)` | wrong user (keys were imported for the installer's account), or the key was never imported: step 1 |
| `ssh-copy-id` fails with `Permission denied (publickey)` | password login is off: import the key at the console (step 1) |
| `zsh: command not found: dot` on the workstation | install dot: `curl -fsSL https://raw.githubusercontent.com/trungngo/dot-cli/main/install.sh \| sh` |
| a vendor apt repository has no release for a new Ubuntu | `package_repo` falls back to the previous suite; `dot plan` names the suite it uses |
| completion, keys or paste misbehave over ssh | the server lacks your terminal's terminfo entry: step 2 |
| `dot apply` asks which profile the server pins | the server's `local.env` sets `DOT_PROFILE`; pass `--profile` to confirm it |
