---
name: project-parallel
description: Create a parallel workspace beside a project's src/ - src-01, src-02 - holding a clean clone of every repository in it, each reset to its main branch, so a second line of work can run without touching the original working tree. Use when the user asks to "work on this in parallel", "make another src", "give me a clean copy of the repos", "src-01", "a second workspace", or wants a fresh session that will not disturb what is already checked out. Not for creating a new project or repo (those are project-new).
---

# A parallel workspace

    $MYPROJECTS_DIR/<project>/src/<repo>       the original, never written to
                             /src-01/<repo>    a parallel workspace
                             /src-02/<repo>


Always pass `--json` and read the JSON. On failure, stderr carries one line
`{"error": {"code", "message", "fix", "hint", "choices"}}`.

## Make one

```bash
tn -C <project dir> ws new [suffix] --json
```

`tn ws new` works on the project that the directory lies in: pass the project with `-C`, or run it
from anywhere inside the project. Outside the tree it exits 2 rather than guessing.

With no suffix, it takes the lowest unused two-digit name. A suffix names the workspace instead:
`01` and `src-01` both give `src-01`, and anything else is literal (`review` gives `src-review`).
It refuses to overwrite an existing directory.

The JSON:

```json
{"project": "acme", "workspace": "src-01", "ws_id": "01", "path": "…/acme/src-01",
 "repos": [{"repo": "shop-web", "state": "copied", "branch": "main", "primary_remote": "origin",
            "unpushed": 2, "submodules": false, "reason": null}]}
```

`state` is `copied`, `skipped` (with a `reason`) or `failed`. Exit 1 means at least one repo
failed; the workspace is kept.

To make the workspace and start a session on it in one step:

```bash
tn claude start <project>/<repo> --ws new --json     # workspace_created names the new src-NN
```

## What the user is actually getting

Say this before running it, because two of the three points surprise people later:

- **Exactly what git tracks on the main branch.** No uncommitted changes, no untracked files, and
  **no gitignored ones**: `.env`, `node_modules`, virtualenvs and `.claude/settings.local.json` do
  not come along. A workspace that needs `npm install` before it runs is normal, not broken.
- **Only pushed work.** Each repo is reset to its remote's main branch, so commits sitting
  unpushed on the original's main are not in the copy. `unpushed` counts them per repo. Pass any
  non-zero count on rather than letting it scroll past.
- **One branch.** Whatever the original had checked out, and every other local branch, is gone.

Repos with no remote at all (which is what `tn repo new` creates) are copied from the local
checkout instead. They end up with no remotes, rather than pointing at the original directory.
Directories under `src/` that are not git repos are skipped, not copied. A repo with submodules
has `submodules: true`: run `git submodule update --init` in the copy.

## Why not `git worktree`

It is the obvious answer, and the wrong one. `git worktree add` writes into the original
repository's `.git`, and the whole point is that `src/` stays untouched. A local `git clone`
writes nothing to the source and hardlinks the object store, so it is nearly free. Do not
"improve" this by switching to worktrees.

## Seeing and removing workspaces

```bash
tn ws ls <project> --json        # [{ws_id, ws, repos, dirty_repos, unpushed_repos, sessions, age_seconds, path}]
tn -C <project dir> ws rm 01 --yes --json
```

`tn ws rm` refuses (exit 1) while any repo has uncommitted or stashed work, a rebase or merge in
progress, or a commit (on any branch, tag or detached HEAD) that is neither on a remote nor in the
original `src/<repo>`, or while a session runs inside the workspace. A copy of a repo with no
remote is removable once everything in it is also in the original. The error's `hint` lists what blocks it.
Never work around the refusal. It deletes the directory only after confirmation: pass `--yes` only
when the user asked for the removal.

## Then open a session

Workspaces exist so two lines of work can run at once, so **offer a Remote Control session on the
new workspace**: that is the payoff. Hand off to [claude-remote](../claude-remote/SKILL.md):

```bash
tn claude start <project>/<repo>@01 --json
```

Pass no name. The derived name already carries the workspace number, which is exactly what tells
this session apart from the one on the original `src/` (`Acme Shop Web #U1-01` beside
`Acme Shop Web #U1-00`).

**A new workspace is an untrusted directory.** Claude Code only loads plugins in trusted
directories. So a project carrying vendored bundles under `.claude/skills/` would start with
none of them, silently. `tn claude start` marks the directory
trusted before Claude starts (`"trusted": true` in its JSON), which covers this. Trust is read at
startup, so a session started with `--no-trust` must be restarted after trusting.
