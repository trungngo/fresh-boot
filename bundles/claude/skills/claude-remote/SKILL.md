---
name: claude-remote
description: Open a Remote-Control Claude session on an existing project, or repo in ~/myprojects, so the Claude desktop or mobile app can drive it. Use when the user asks to "open claude on <project>", "start a remote session for <repo>", "run claude headless there", or asks for a session without saying where. Also covers listing, attaching to, and stopping those sessions.
---

# Remote Claude on a project or repo

`tn claude start` runs a Claude session in a detached tmux session, rooted at a project or repo.
The session keeps running after the command returns, and the desktop app picks it up over Remote
Control. It runs in tmux rather than under `claude --bg` because a `--bg` session drops offline
after a long idle stretch; one in tmux stays connected until stopped.

Always pass `--json` and read the JSON. Never parse the text output. On failure, stderr carries
one JSON line, `{"error": {"code", "message", "fix", "hint", "choices"}}`, and stdout is empty.

## The target

`tn` searches one tree:

    $MYPROJECTS_DIR/<project>/src/<repo>        # ~/myprojects

**If the user named one**, pass their words as the target. Do not search the directories first.
The target can be any of these:

| target | means |
|---|---|
| `acme/shop-web` | project and repo |
| `acme/shop-web@02` | the same repo in the parallel workspace `src-02` |
| `acme` | a project. When it holds exactly one repo, that repo is used. |
| `shop-web` | a repo name, searched in every project |
| `~/some/dir`, `./x` | a directory |

```bash
tn claude start <target> --json
```

- **Exit 2 with `choices`**: the name matched several things, or nothing. Show the choices as a
  short numbered list and ask which one. Then call again with the exact choice. Do not guess.
- **If the user named nothing**, list the projects and let them choose:

  ```bash
  tn proj ls --all --json        # projects: name, root, repos, workspaces
  tn repo ls <project> --json    # the repos in one project
  ```

  `tn claude start --json` with no target starts in the **current directory**, which is rarely
  what a user who named nothing wants. Ask first.

## Start it

**Pass the target only.** The name is derived, and the convention is the point of it:

    <Project> <Repo> #<Machine>-<Workspace>        Acme Shop Web #U1-00

`<Workspace>` is which src directory the session runs in: `00` for `src/`, `01` for a parallel
`src-01`. This keeps two sessions on the same repo in different workspaces apart. `<Machine>` is
this machine, so sessions on several machines stay apart too. `--name <title>` **overrides all
of that**. Use it only when the user asked for a particular name. Do not invent one.

The JSON result:

```json
{"tmux": "claude-acme-shop-web-00", "name": "Acme Shop Web #U1-00",
 "uuid": "0f3c…-full-uuid", "dir": "/Users/…/acme/src/shop-web", "context": "acme/shop-web",
 "resumed": false, "trusted": true, "trust_changed": true, "workspace_created": null}
```

Report `name`, `tmux` and `dir`. The command **returns after about two seconds**: it waits that
long to check that Claude did not die on startup. Then the session keeps running in tmux, so
there is nothing to wait for or interrupt.

Things worth knowing:

- **It runs at the git root.** A subdirectory of a repo starts the session at the repository
  root, so Claude sees the whole project. The name follows the root.
- **It trusts the directory.** A detached session has nobody to answer the interactive trust
  prompt. Without trust, the session would come up with none of the workspace's own skills and no
  error saying why. `--no-trust` opts out. Offer it for a directory the user did not create.
- **`--ws new`** first creates the next parallel workspace (`src-01`, ...) and starts there. The
  JSON's `workspace_created` names it. See [project-parallel](../project-parallel/SKILL.md).

When it fails, pass the `fix` on rather than working around it:

| exit | message | what to do |
|---|---|---|
| 1 | `already running in tmux session <tmux>` | it is up already: report it, and offer `tn claude attach <tmux>` for the user's terminal. Do not start a second one under another name. |
| 1 | `claude exited straight away` | `fix` holds the command to run by hand, which shows why |
| 3 | `Claude Code has not been set up on this machine` | the fix is `claude`: the user runs it once in a terminal, finishes the theme and login screens, and exits. You cannot do it for them (it signs in through a browser). Then start again. |
| 3 | `MY_MACHINE is not set` | the fix is `tn config set machine <name>`. Ask the user for the machine's short name (such as `U1`). Never invent one. |
| 3 | `tmux is not installed` / `claude is not installed` | `dot apply tmux` / `dot apply claude` |
| 3 | `Claude sessions run in tmux, which Windows lacks` | run it in WSL |

## Afterwards

```bash
tn claude ls --json                  # [{tmux, name, context, status, age_seconds, attached, dir, uuid, started}]
tn claude stop <tmux-name> --json    # stops that one; no prompt when a name is given
tn sessions --json                   # Claude and Codex sessions together
```

`status` is Claude's own `idle` / `busy` (null when Claude has not registered yet). `stop` with no
name picks interactively, and without a terminal it exits 2 with the `choices`. Always pass the
tmux name, taken from `tn claude ls` and confirmed with the user. `--all` stops every session and
needs `--yes`: use it only when the user asked for all of them.

Stopping kills the tmux session but **keeps the conversation**. The stop JSON's `resume` field
(`tn claude start <dir> --resume <uuid>`) brings it back; see
[claude-resume](../claude-resume/SKILL.md).

Attaching (`tn claude attach [name]`) is for the user's own terminal. It hands the terminal to
tmux, so it rejects `--json`. The user detaches with `C-a d`, which leaves the session running.
To see what a session is doing from here, read its pane instead:

```bash
tmux capture-pane -p -t '=<tmux-name>:' | tail -40
```

## For Codex instead

`tn codex start|ls|attach|stop` exists but works differently. Codex runs one shared daemon rather
than a session per process, so there is no per-directory session to name. See
[bundles/codex/README.md](../../../codex/README.md).
