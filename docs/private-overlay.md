# The private overlay

This repository is publishable and holds no secrets. Nothing in it names a person, an e-mail
address, a company, a client or project code name, a private host, an account or a machine.
Tests, docs and examples use example data (`alex`, `Alex Doe`, `alex@example.com`,
`gitlab.example.com`).

Your own values live outside the repository, on each machine:

| what | where it lives | how it gets onto a machine |
|---|---|---|
| your name, e-mail, machine name | `~/.config/dot/local.env` | `dot apply` asks once (`prompt:` vars in `dot.yml`) |
| private `tn` config (optional): people, your own namespaces | `~/.config/tn/conf.d/*-private.toml` | you write it; the bundles' `*.example` files show the shape |
| secrets you add yourself (optional) | `~/.config/dot/secrets.env` (0600) | you write it, or a provider such as LastPass |

Plus one file for checking, never used by any bundle: the privacy denylist
(`~/.config/dot/privacy-denylist`, section 4).

## 1. Prompted variables (`~/.config/dot/local.env`)

Declared in `dot.yml` with `prompt:` and `persist: local`. The first interactive `dot apply`
asks for each one that has no value, checks it against its `pattern`, and appends it to
`~/.config/dot/local.env`; later runs read it from there and never ask again.

| variable | used by | example |
|---|---|---|
| `MY_NAME` | `~/.gitconfig` (`user.name`), tn's `me` person | `Alex Doe` |
| `MY_EMAIL` | `~/.gitconfig` (`user.email`), tn's `me` person | `alex@example.com` |
| `MY_MACHINE` | Claude / Codex session names (`#U1-00`) | `U1` |

Optional, set by hand in the same file when you need them: `DOT_PROFILE`, `DOT_ROLE`
(`server` or `desktop`), `DOT_REPO`.

`dot apply --host user@server`, run from a machine that has them, forwards `MY_NAME` and
`MY_EMAIL` from its `local.env` to the server's run (a value the server's own `local.env` sets
wins). `MY_MACHINE` is `per_machine: true`: it names one machine, so it is never copied; dot asks
for the server's and keeps the answer in the server's `local.env`, or takes
`--var MY_MACHINE=S1`.

A non-interactive run (`--yes` over ssh, cloud-init) cannot ask: it fails up front and names the
missing variables. Write them first:

    mkdir -p ~/.config/dot && cat >> ~/.config/dot/local.env <<'EOF'
    MY_MACHINE=S1
    MY_NAME="Alex Doe"
    MY_EMAIL=alex@example.com
    EOF

or pass `--var NAME=value`. `dot vars` shows every value and where it came from. The committed
`.env` is empty: it is for shared values that are neither secret nor personal.

## 2. Private tn config (optional)

tn merges `~/.config/tn/conf.d/*.toml` in name order, then `~/.config/tn/config.toml`
(docs/tn.md §4.1). The committed part (for example the public forges in
`bundles/git/git-forges.toml`) is copied from the repository. Anything personal, such as your
own forge namespaces or the people `tn git as` knows, goes in a `*-private.toml` you write
yourself, next to it: start from the bundle's `private.toml.example`. `~/.config/tn/config.toml`
still wins over both for one machine's tweaks. Project settings (`<root>/<project>/tn.toml`)
live in the project directories, outside this repository already.

## 3. Your own secrets

fresh-boot ships none and needs none: `gh` and `glab` log in interactively (`gh auth login`,
`glab auth login`), and every other login is a tool's own prompt. If you fork it and a bundle of
yours needs a secret, declare it with dot, not in a committed file:

- a `secrets.yml` at the repository root (`dot schema secrets` prints its JSON Schema) mapping a
  **generic** logical name (`<bundle>_<what>`, never a person, company or host) to a provider
  and a fallback in `~/.config/dot/secrets.env` (mode 0600);
- use it as `{{ secret("name") }}` in a `shell`, `template` or `block` step, or
  `secret_file: { <dest>: { secret: <name> } }` for a file;
- keep the values in the provider or in `secrets.env`, never in the repository (`.gitignore`
  already ignores `secrets.env`, `*.ovpn`, `*.pem`, `*.key` as a backstop).

If you fork this repository privately, keep your secrets out of it the same way. See
`dot --help` and `dot schema secrets`.

## 4. Keeping it clean: `test/privacy-check.sh`

    test/privacy-check.sh                    # this repository
    test/privacy-check.sh --history main     # also the commits of the branch to publish

It scans every tracked and untracked (not ignored) file, and every file name, for e-mail
addresses outside `example.com` / `example.org` / `example.net` (and `*.example`, `*.invalid`,
`*.test`, `noreply`), `/Users/<name>` and `/home/<name>` paths whose name is not a placeholder
(`me`, `user`, `tester`, ...), private-looking hosts (`*.internal`, `*.lan`, `*.corp`, a
self-hosted `gitlab.<domain>`), and every literal of the **denylist**. A binary file (a `.pyc`,
an image) is not skipped: its printable strings are checked the same way. Exit 1 lists the hits.
`test/privacy-check-tests.sh` tests the script itself against a made-up denylist.

The denylist holds the real identifiers (names, company, clients, code names, colleagues,
hosts), one literal per line, matched case-insensitively as whole words, where `_`, `-` and `.`
end a word and a camelCase word is split (`JaneDoeMBP`). An entry of six or more letters and
digits also matches inside a word once separators are dropped (`Jane Doe` finds `jane_doe`,
`JaneDoeMBP`); start a shorter one with `*` for the same. It lives at
`~/.config/dot/privacy-denylist` (override: `PRIVACY_DENYLIST`) and must never be inside a
repository: the script refuses one that is.

`test/privacy-allowlist` (committed) lists the intentional references, removed from a line
before it is checked: only where dot and this repository are published (the install one-liners,
`dot self-update`, the `$schema` lines) and the license holder. A repository may add its own
`.privacy-allowlist`.

`--history REF` checks the author, committer and message of every commit reachable from `REF`
and the `user.name` / `user.email` the next commit would get; push only when it prints `clean`.
A commit carries its author's name and e-mail, which the files never show, so use a neutral
identity such as GitHub's noreply address (Settings, Emails):

    git config user.name  "<public name or handle>"
    git config user.email "<id>+<handle>@users.noreply.github.com"

### Run it before every push

`test/pre-push` is a git hook that runs `test/privacy-check.sh` and, when installed,
`gitleaks detect` over the working tree, and aborts the push if either finds something:

    ln -sf ../../test/pre-push .git/hooks/pre-push
    brew install gitleaks            # or your package manager; the hook skips it when absent

## 5. A new machine

1. Install (README.md). On an interactive terminal the first `dot apply` asks for the prompted
   variables (section 1); on a headless one, write `local.env` first.
2. `gh auth login` and `glab auth login` once, if you use them.
3. Copy your private tn config (section 2), if you keep one, to `~/.config/tn/conf.d/`.
