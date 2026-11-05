---
name: project-clone
description: Clone existing repositories from GitHub or GitLab into the ~/myprojects tree, creating the project if it does not exist yet. Use when the user asks to "clone <repo>", "pull down <project>", "get my repos onto this machine", "set up <project> here", or names a repo that is not checked out locally. Always asks which forge and account to pull from before listing anything.
---

# Clone into the project tree

This brings existing repositories onto the machine in the layout everything else assumes:

    $MYPROJECTS_DIR/<project>/src/<repo>        # MYPROJECTS_DIR=~/myprojects

Use [project-new](../project-new/SKILL.md) instead when the code does not exist yet.

Always pass `--json` to `tn` and read the JSON. On failure, stderr carries one line
`{"error": {"code", "message", "fix", "hint", "choices"}}`.

## Ask where to pull from, always

There is no default, and guessing wrong is expensive. Each forge has more than one identity behind
it, so **ask before listing anything**. The forges tn knows are keys in its config:

| forge key | host | CLI | accounts |
|---|---|---|---|
| `gh` | github.com | `gh` | `alex` (the usual one), `alex-partnerco` |
| `work` | gitlab.example.com (self-hosted) | `glab` | the work account |
| `gitlab` | gitlab.com | `glab` | |
| `bitbucket` | bitbucket.org | none | legacy |

`tn config get forges --json` shows the exact list on this machine.

Check the CLI logins before listing. `tn doctor --json` reports each forge's login, and so do
`gh auth status` and `glab auth status`. Switch GitHub accounts with `gh auth switch`. The GitLab
API token has expired before. When it has, listing fails, but `git clone` over SSH still works,
because the SSH key is registered. If the user wants to browse GitLab repos with an expired token,
they must re-authenticate first: `glab auth login --hostname <host> --web`. Say that rather than letting the listing
error.

## Then list and choose

```bash
gh repo list <owner> --limit 100 --json name,visibility,pushedAt   # omit owner for the active account
glab repo list                                                     # needs a working token
```

Show a short numbered list (name, visibility, last push), and let the user pick one or several.
When they already named the repo in the prompt, skip straight to cloning.

## Clone

```bash
tn proj ls --json                                   # does the project exist?
tn proj new <code-name> --json                      # only if it does not
tn repo clone <forge>:<path> <local-name> -p <code-name> --json
```

The `source` of a clone takes one of these forms:

- `gh:alex/demo-app` or `work:acme/web/shop-all`: through the forge's CLI
  (`gh repo clone` / `glab repo clone`), so private repos work without extra setup;
- a full URL (`https://…`, `git@host:path.git`): plain `git clone`. Use this for GitLab while its
  API token is expired, because SSH does not need the token;
- a bare `owner/repo`: the project's own forge (`forge` in its `tn.toml`). Without one, it exits 2
  and asks you to say which forge.

`tn repo clone` refuses to overwrite an existing directory (exit 1). The JSON is
`{"project", "repo", "path", "source", "url", "forge", "identity"}`.

**The local directory name is a real decision, not a formality.** Always pass it explicitly.
Without a terminal, tn silently uses the last segment of the remote path. There is no mechanical
mapping between remote and local names in this tree:

| remote | local |
|---|---|
| `alex/demo-app` | `demo/src/app` |
| `partnerco-umbrella/app` | `umbrella/src/sow-app` |
| `alex/initech-core` | `initech/src/initech-core` |
| `gitlab.example.com:acme/web/shop-all` | `acme/src/shop-all` |

Sometimes the project prefix is stripped, sometimes kept, and the owner is not the project. When
it is not obvious, ask which project a repo belongs under and what to call it locally. GitLab
paths here are nested groups (`<group>/<subgroup>/<repo>`), so the default name is the last
segment only.

For several repos into one project, clone them one at a time, so that a single failure does not
abandon the rest. Report which ones succeeded.

## Identity

The clone gets a local `user.name` / `user.email`. It is the project's `identity` from its
`tn.toml` when that is set, else the `MY_NAME` / `MY_EMAIL` the machine was set up with. The
JSON's `identity` says which. For a personal project, switch the repo, or better, set the
project's identity once so every repo tn creates or clones there gets it:

```bash
tn -C <repo path> git as alex-personal --json            # this repo; tn git as --list --json lists people
tn -C <project dir> config set identity alex-personal --project
tn -C <repo path> git whoami --json                       # {name, email, source, expected, matches}
```

## Verify, then offer a session

`path` in the clone's JSON is where the repo landed. `tn -C <path> status --json` must show
`.context.project` and `.context.repo`. When they are null, the clone landed outside the
convention.

Then **ask whether to open a Remote Control Claude session** on what was just cloned: pulling code
down is usually the start of working on it. If yes, hand off to
[claude-remote](../claude-remote/SKILL.md) with `tn claude start <project>/<repo> --json`. Pass no
name: it derives one from the layout. With several repos cloned, ask which one the session should
root at, or use the project (`tn claude start <project> --json`) if the work spans them.
