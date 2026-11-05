---
name: project-new
description: Create a new project, or a new repository inside an existing project, in the ~/myprojects tree. Use when the user asks to "start a new project", "create a project", "add a repo to <project>", "init a new repo", or names a project and repo that do not exist yet. Handles the $MYPROJECTS_DIR/<project>/src/<repo> layout that tn and the Claude sessions assume.
---

# New project, new repo

The machine organises work as a two-level convention, and `tn` works out where it is from it
rather than from arguments:

    $MYPROJECTS_DIR/<project>/src/<repo>        # MYPROJECTS_DIR=~/myprojects

A **project** is a unit of work (a client, a product, a personal area) holding `src/`, `bin/`,
`rel/`, `key/` and `tmp/`. A **repo** is one git repository inside that project's `src/`. So
`~/myprojects/alex/src/website` is project `alex`, repo `website`.

Do not create directories by hand. Two commands own this, and everything else depends on exactly
what they produce. Always pass `--json` and read the JSON. On failure, stderr carries one line
`{"error": {"code", "message", "fix", "hint", "choices"}}`.

## Creating

```bash
tn proj new <code-name> --json                 # the project and its five subdirectories
tn repo new <repo-name> -p <code-name> --json  # <project>/src/<repo>, git init, identity, .gitattributes
```

- `tn proj new` JSON: `{"project", "root", "path", "dirs", "config": {"forge", "group", "identity"}}`.
  It fails (exit 1) if the project exists. Names are lowercase letters, digits, `.`, `_` and `-`.
- `tn repo new` JSON: `{"project", "repo", "path", "identity", "remote"}`. It fails if the repo
  exists. It always creates the repo in `src/`, even when run from a parallel `src-NN`.
- Adding a repo to an existing project is just the second line.

Project code names in this tree are short and arbitrary (`orbit`, `ember`, `acme`).
They are not descriptions. If the user has not named one, ask rather than invent one.

A project can carry its defaults in `<project>/tn.toml`. Set them at creation when the user knows
them, because every later repo in the project then gets them:

```bash
tn proj new <code-name> --forge gh --group <owner-or-group> --identity alex-personal --json
```

`--forge` is a forge key (`gh`, `work`, `gitlab`, `bitbucket`; see
`tn config get forges --json`). `--identity` is a people key (`tn git as --list --json`). An
unknown key exits 2 with the `choices`.

## The two things to confirm, not assume

**Commit identity.** `tn repo new` sets the repo's local `user.name` / `user.email` to the
project's `identity` when it has one. Otherwise it uses `MY_NAME` / `MY_EMAIL` (dot's prompts, kept in
`~/.config/dot/local.env`), usually the work address (`alex@example.com` in these examples). The global `~/.gitconfig` carries the
same work address, so that is the default *everywhere*. A personal project therefore needs an
explicit switch, and nothing prompts for it. The JSON's `identity` says what the repo got. Tell
the user, and offer to change it:

```bash
tn -C <repo path> git as alex-personal --json   # personal; tn git as --list --json lists every person
tn -C <repo path> git whoami --json              # {name, email, source, expected, matches}
```

**Remotes.** `tn repo new` adds none unless it is given `--forge`. Ask where the repo should live,
then:

```bash
tn -C <repo path> git remote add gh --json       # path from the project and repo names
tn -C <repo path> git remote add work --json    # the self-hosted gitlab.example.com
```

The JSON is `{"name", "url", "forge", "path", "fetched"}`. `fetched: false` with a warning
usually means the repository does not exist on the forge yet. Creating it is a separate step:
`gh repo create <path>` or `glab repo create <path>`. See the [gh](../../../gh/README.md) and
[glab](../../../glab/README.md) bundles. `tn repo new <repo> -p <project> --forge --json` does
both steps at once when the project's `tn.toml` names its forge.

## Verifying

```bash
tn -C <repo path> status --json
```

`.context.project` and `.context.repo` must name the project and repo, and `.context.path` must be
the repo's absolute path. Null values mean the directory is outside the convention. That is not an
error from tn, so check for it.

## Then offer a session

Creating a project is usually the start of working in it, so **ask whether to open a Remote Control
Claude session on the new repo**. Do not just finish silently. If yes, hand off to
[claude-remote](../claude-remote/SKILL.md) with `tn claude start <project>/<repo> --json`. Pass no
name: it derives one from the layout (`Demo App #U1-00`).
