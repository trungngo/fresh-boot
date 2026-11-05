---
name: claude-resume
description: Wake a stopped or offline Claude session and put it back on Remote Control in tmux, keeping its conversation. Use when the user says "wake up <session>", "resume <session>", "bring it back", "it shows offline in the desktop app", or when a peer session asks for a named session to be revived. Not for starting a new session on a directory - that is claude-remote.
---

# Waking a stopped session

`tn claude start` runs each session as an interactive `claude` inside a detached tmux session.
When that tmux session is gone, the whole conversation is still on disk. It can be gone because
of `tn claude stop`, because Claude exited, or because of a reboot. Resuming reattaches to the
conversation; starting fresh abandons it. The two are easy to confuse, because both end with a
session of the right name in the right directory.

Always pass `--json` and read the JSON. On failure, stderr carries one line
`{"error": {"code", "message", "fix", "hint", "choices"}}`.

## First choice: `tn claude resume`

tn records every session it starts, so it can sort them by what happened:

```bash
tn claude resume --all -n --json   # what it would wake, each with its "state"; changes nothing
tn claude resume --all --json      # wake every crashed, rebooted or account-switched session
tn claude resume <name> --json     # one session, by tmux name, title, context or uuid prefix
```

States: `crashed`, `rebooted` and `account` (it runs on the account you were signed in as
before; run `tn claude login` first) are woken by `--all`. `stopped` (`tn claude stop`) and
`exited` (`/exit`, or archived in the desktop app) were ended on purpose: `--all` leaves them,
and a name still brings one back. Each result has `resumed` and `error`. Exit 1 with `--all`
means some failed. Read their `error`s.

Use the manual route below only for a session tn has no record of (started before tn
recorded sessions, then gone), when `resume <name>` exits 2 without it in `choices`.

## Is it actually stopped?

```bash
tn claude ls --json      # [{tmux, name, context, status, age_seconds, attached, dir, uuid, started}]
```

If the session is listed there, it is running. "Offline in the desktop app" with a live tmux
session is a Remote Control problem, not a stopped session. Read its pane before doing anything:

```bash
tmux capture-pane -p -t '=<tmux-name>:' | tail -40
```

**A reboot kills every tmux session.** So if one is reported down, check whether the others are
down too, and offer to wake them together.

## Find the conversation

`--resume` takes the **full UUID**, never an 8-character short id: a short id exits 2. The
transcript directory is authoritative, and each filename is a UUID:

```bash
ls -lt ~/.claude/projects/<dir-with-every-non-alphanumeric-as-dash>/
```

`/Users/me/myprojects/acme/src-01/shop-web` becomes
`-Users-me-myprojects-acme-src-01-shop-web`. Each `<uuid>.jsonl` is one session. Check the size
before reporting anything. A few KB is a session that never did any work; a few hundred KB is one
worth resuming.

If `tn claude stop` stopped it, the stop's JSON already held the exact command in its `resume`
field: `tn claude start <dir> --resume <uuid>`. Use it if it is in front of you.

**When no session was named, do not guess.** List the candidates with directory, name, age and
size, and let the user pick. If exactly one fits, still say which one you are about to wake rather
than acting silently.

## Resume it

```bash
tn claude start <the session's directory> --resume <full-uuid> --json
tn claude start <the session's directory> --resume --json      # the newest conversation there
```

Put the directory **before** `--resume`. This starts a new tmux session that runs
`claude --resume <uuid>` with Remote Control and the derived name. Check the JSON: `resumed` must
be `true`, and `uuid` must be the one you asked for.

It refuses (exit 1) in two cases, and neither should be worked around:

- **`conversation <uuid> is running outside tmux (pid N)`**: someone is sitting in it in a
  terminal. Two processes on one transcript corrupt it. Tell the user, and let them exit the other
  one.
- **`conversation <uuid> is already running`**: it is already in tmux. The `fix` names the
  session: `tn claude attach <tmux>`.

`--resume` with no uuid picks the newest transcript in the directory. When several sessions have
run there, that may not be the one the user means, so prefer the explicit uuid.

## Do not substitute a plain start

`tn claude start` without `--resume` starts a **new** conversation. It looks like it worked: right
name, right directory, Remote Control connected. Meanwhile the conversation it was supposed to
restore sits on disk untouched.

## Expect it back busy

A session stopped mid-task may resume mid-task. Read its pane before sending it anything new.
