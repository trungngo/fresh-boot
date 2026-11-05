# projects

The `tn` plugin for the machine's project layout (CLAUDE.md, "The project layout convention"):
`tn proj`, `tn repo`, `tn ws` and `tn cd`, plus the Python API the claude, codex and
git plugins build on. The full specification is [docs/tn.md §7.1](../../docs/tn.md).

    $MYPROJECTS_DIR/<project>/src/<repo>                  # ~/myprojects: ongoing work
    <project>/src-01/<repo>, src-02/...                   # parallel workspaces (tn ws new)

## Installs

| path | what | how |
|---|---|---|
| `~/.local/share/tn/plugins/projects.py` | the plugin | `copy` of `plugin.py` |

Nothing else: no packages (git comes from `common`, tn from the `tn` bundle, which this bundle
`requires`). `tests/` is never copied. docs/tn.md §7 has the claude, codex and git bundles
`requires: [projects]`, so it is applied wherever they are.

## Commands

| command | does | replaces |
|---|---|---|
| `tn proj new <name> [--root KEY] [--forge F] [--group G] [--identity P] [--cd]` | `<root>/<name>/{src,bin,rel,key,tmp}` (`[proj].dirs`), and a `tn.toml` with the given keys | `proj-init.sh` |
| `tn proj ls [--root KEY]` | projects with their repos, workspaces, forge and identity | new |
| `tn proj show [project]` | one project, its repos' state and its `tn.toml` | new |
| `tn repo new <name> [-p P] [--forge [F]] [--cd]` | `<project>/src/<name>`, `git init`, the project identity, `.gitattributes`; `--forge` adds the forge remote | `repo-init.sh` |
| `tn repo clone <source> [name] [-p P] [--cd]` | clone `gh:owner/repo`, `work:group/sub/repo`, a URL, or `owner/repo` (the project's forge) into `src/`, then set the project identity | `repo-clone.sh` |
| `tn repo ls [project] [--ws ID \| --all-ws] [--all] [--fetch]` | branch, changes, ahead/behind, remote and identity for every repo | `repo-scan.sh` (dropped) |
| `tn repo show [repo]` | one repo: the `ls` row, last commit, top authors, files by extension, project markers | `repo-stats.sh` |
| `tn ws new [ID] [--cd]` | a parallel workspace `src-NN` of clean clones on the main branch | `src-new.sh` |
| `tn ws ls [project]` | workspaces with dirty / unpushed repo counts and the sessions running in them | new |
| `tn ws rm <ID>` | delete a workspace; refuses while any repo has uncommitted, stashed or unpushed work, or a session runs there; confirms (`--yes`) | new |
| `tn cd [query...] [--print]` | fuzzy jump to a project, workspace (`acme@02`) or repo (`acme/shop`); a remote path also matches | new |

Every command takes the global flags (`--json`, `-n`/`--dry-run`, `-y`, `-C DIR`, ...; docs/tn.md
§2.3). `--cd` and `tn cd` change the shell's directory through the `tn` shell function that the
tn bundle's `tn.zsh` installs; without it tn prints the path and a hint.

## Why it works this way (carried over from the old scripts)

- **Workspaces are local clones, never `git worktree`.** A worktree writes into the source
  repository's `.git`, and the point of `src-NN` is that `src/` is not touched at all. A local
  `git clone` writes nothing to the source and hardlinks the objects. The copy holds exactly what
  the default branch tracks: no uncommitted, untracked or gitignored files (`.env`,
  `node_modules`, `.claude/settings.local.json` must be recreated), exactly one local branch,
  and the source's remotes (a repo without remotes stays without, rather than pointing at the
  original directory). Commits the source has not pushed are reported (`note: src/<repo> is N
  unpushed commit(s) ahead - not copied`), not silently dropped.
- The default branch is `origin/HEAD`, else a local `main` / `master`, else the checked-out
  branch.
- **`tn ws rm` never deletes work.** There is no `--force`: every repo must be clean, have no
  stash and no rebase or merge in progress, and every local commit (every branch and tag, and a
  detached HEAD) must be on a remote or in the original `src/<repo>`; a repo with no remote is
  therefore removable exactly when its original holds everything it has. Anything else in the
  workspace, hidden entries included (a hidden repo is checked like any other), blocks it too.
  A Claude or Codex session running inside it must be stopped first. The id is a single name:
  `tn ws rm` only ever removes a `src-*` directory directly inside the project.
- **A new repo goes to `src/`** even when run from `src-NN`: new repos belong to the original.
- **Identity follows the project.** `repo new` and `repo clone` set
  `user.name` / `user.email` locally from the project's `tn.toml` `identity`
  (a people key from the git bundle's private `conf.d/git-private.toml`), else from `me` (`MY_NAME` /
  `MY_EMAIL`, dot prompts kept in `~/.config/dot/local.env` and exported by `dot env`).
- **The clone name is a real choice** (`alex/demo-app` lives in `demo/src/app`), so
  `tn repo clone` asks for it on a terminal, with the last path segment pre-filled.
- **No remotes by default** on `tn repo new`: add one with `--forge` or `tn git remote add`.

## Configuration

From `~/.config/tn` (docs/tn.md §4): `[roots]` (default `$MYPROJECTS_DIR`),
`[proj].dirs`, the
`[forges.*]` and `[people.*]` the git bundle ships, and per project `<project>/tn.toml`
(`forge`, `group`, `identity`).

## Python API

Documented at the top of `plugin.py`: `resolve(ctx, target, ws=, prefer_repo=)` → `Where`
(`path`, `ctx`, `name`, `git_root`, `session(kind)`, `label()`, `workspace_created`),
`session_name`, `iter_projects`, `iter_repos`, `workspaces`, `repo_state`, `default_branch`,
`ws_new`, `ws_blockers`, `identity_for`, `set_identity`, `add_remote` (what
`tn git remote add` does), `read_remotes`, `read_identity`. Other plugins import it with
`from tn.plugins import projects` and list `projects` in both `requires=` and their bundle's
`requires`.

## Tests

`test/tn-tests.sh projects` (real git in temp directories; gh / glab are fakes; nothing touches
`$HOME` or the network).
