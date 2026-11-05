# Provisioning a new Mac from your workstation

On the new Mac itself, the one-liner of the README (`install/install.sh`) is enough. This guide is
the other way: set up a fresh Mac over ssh from a Mac or Linux workstation that has a checkout of
this repository, as in the [Ubuntu server guide](provision-ubuntu-server.md). It has advantages:
dot arrives over ssh, not through a browser (which adds a quarantine mark); the repository is
synced with its `.git`, so the new Mac needs no git or Command Line Tools before Homebrew is
installed; and `MY_NAME` and `MY_EMAIL` come from the workstation's `local.env`. The new Mac ends
up with the `mac` profile. For Windows, see [provision-windows.md](provision-windows.md).

Run the commands from your checkout of this repository, in **macOS Terminal** (or any terminal
that reports `TERM=xterm-256color`), not Ghostty: the new Mac doesn't know Ghostty's terminal
type yet, and programs dot starts there (the Homebrew installer, say) would misdraw. In the
examples the new Mac is `user@newmac`: the account Setup Assistant created, and the Mac's local
hostname (System Settings > General > Sharing, e.g. `newmac.local`) or a `~/.ssh/config` alias.
Its short name is `M2`.

## Quick start

Once steps 1 and 2 are done (Remote Login, key login):

    dot apply --host user@newmac --repo . --profile mac --var MY_MACHINE=M2

It shows the plan, asks `Apply? [Y/n]`, then your sudo password on the new Mac once. Then finish
at the new Mac (step 5). Step 3 and 4's preview is optional.

## 1. At the new Mac

1. Finish Setup Assistant. The first account is an administrator, which sudo needs.
2. System Settings > General > Sharing > **Remote Login**: on, and allowed for your user.
3. Recommended: `xcode-select --install` in Terminal, and wait for it to finish. The Homebrew
   installer installs the Command Line Tools itself, without a dialog; if that fails it falls
   back to a dialog nobody can answer over ssh.
4. Keep it on power and awake for the run: `caffeinate -dims` in a Terminal window.

## 2. ssh key login

macOS allows password login over ssh, so `ssh-copy-id` works:

    ssh-copy-id user@newmac
    ssh user@newmac true && echo ok

## 3. Optional: your terminal's definition on the new Mac

Skip this from macOS Terminal. From Ghostty (or kitty, WezTerm, ...), copy the terminfo entry over
once:

    infocmp -x xterm-ghostty | ssh user@newmac -- tic -x -

## 4. Optional: preview

    dot plan --host user@newmac --repo . --profile mac --var MY_MACHINE=M2

This copies dot there, syncs the repository to `~/.dot` and prints the plan: the bundles, what
each step would change and which steps need sudo. Nothing else changes. `MY_MACHINE` is the new
Mac's short name, used in Claude/Codex session names; it is per machine, so it is never copied
from the workstation.

## 5. Apply, then finish at the new Mac

    dot apply --host user@newmac --repo . --profile mac --var MY_MACHINE=M2

dot shows the plan and asks `Apply? [Y/n]`, then asks for your **sudo password on the new Mac
once** (casks shipped as `.pkg` and the login shell change need it), and runs. The Homebrew
installer step is interactive: the live view pauses for its "Press RETURN". Leave out `--yes` for
a first install: it fails up front unless sudo works without a password.

A step that needs `brew` on `PATH` when dot starts (`when: { pkg: brew }`) is skipped on a fresh
Mac, because Homebrew did not exist yet. After the run, at the new Mac:

1. Log out and back in: Homebrew's zsh became the login shell.
2. Open Ghostty (the ghostty bundle installed it) and run `dot apply`. It finds `~/.dot` and
   `local.env` by itself, and installs what the first pass could not see (Homebrew is on `PATH`
   now).
3. `gh auth login` and `glab auth login`, once.

## 6. Later

Change the repository on the workstation and run the same apply again, or work in a clone on the
new Mac and run `dot apply` there (`git -C ~/.dot pull` first). Don't mix the two without care: a
`--host` run syncs over `~/.dot`, `.git` included, so unpushed work there is gone. To upgrade dot
there, `dot self-update`.

## Without ssh

When Remote Login is not an option, run the README's one-liner at the new Mac.

## Troubleshooting

| symptom | cause and fix |
|---|---|
| `Connection refused` on port 22 | Remote Login is off: step 1 |
| `Permission denied (publickey)` | step 2, or Remote Login does not allow your user |
| the run stops at the Homebrew installer | it waits for RETURN, or for a Command Line Tools dialog at the console: step 1.3 |
| the ssh session drops in the middle | the new Mac slept: step 1.4, then run the same apply again |
| completion, keys or paste misbehave over ssh | the new Mac lacks your terminal's terminfo entry: step 3 |
| work done in `~/.dot` on the new Mac is gone | a later `dot apply --host` synced over it: step 6 |
