---
name: port-forward
description: Expose a port on this machine to the internet through a VS Code dev tunnel and hand back a link that works from anywhere. Use when the user asks to "forward port 3000", "give me a link for localhost:8080", "share my dev server", "let me open this on my phone", "make this reachable remotely", or wants to show a running app to someone else. Also covers listing and stopping those forwards.
---

# Port forwarding, link back

`tn tunnel` wraps the `devtunnel` CLI. It uses the same Microsoft dev tunnels service as VS
Code's PORTS panel.

```bash
tn tunnel open <port> [--public] [--for 2h] --json   # start one, print the link
tn tunnel ls --json                                  # what is forwarded right now
tn tunnel close <port> --json                        # stop one
```

Always pass `--json` and read the JSON. On failure, stderr carries one line
`{"error": {"code", "message", "fix", "hint", "choices"}}`.

`tn tunnel open` **returns** once the link appears, usually in two or three seconds. The tunnel
keeps running in the background, so there is nothing to wait for and nothing to Ctrl-C.

## Getting the link

```bash
tn tunnel open 3000 --json
```

It prints an array with one entry per port:

```json
[{"port": 3000, "url": "https://k7m2xq04-3000.asse.devtunnels.ms", "access": "private",
  "pid": 4242, "started": "…", "expires": null, "label": "acme-shop-web-3000",
  "context": "acme/shop-web", "reused": false}]
```

Report both `url` and `access`. The URL alone hides the important half.

Opening the same port again returns the existing link (`"reused": true`) rather than starting a
second tunnel. So it is safe to call when you are unsure whether one is already up. With no port,
it forwards the project's `[tunnel] ports` from its `tn.toml`, when that is set.

## Private by default: ask before making it public

| | who can open the link | when |
|---|---|---|
| default | only the account that started it, after a browser sign-in | the user reaching their own machine from a phone, a laptop, vscode.dev |
| `--public` | anyone on the internet holding the link | showing it to a client, a webhook, a colleague, a device that cannot sign in |

**Never pass `--public` on your own initiative.** If the request implies that someone else must
open the link, say that it needs `--public` and what that means, then let the user choose.
Examples: "send this to the client", "point Stripe's webhook at it", "my phone won't log in".
`--public` is per forward and never remembered. So an existing private forward must be closed and
opened again to become public.

A private link is useless to `curl` and to API clients, because the sign-in is a browser
redirect. For a non-browser client on a private tunnel, issue a token instead:
`devtunnel token <tunnel-id> --scopes connect`. Send it as the
`X-Tunnel-Authorization: tunnel <token>` header.

`--for 2h` (also `30m`, `1d`, `1h30m`) closes the forward by itself after that time. Suggest it
for a public link that is only needed briefly.

## Which port

If the user names a port, use it. If they describe the app instead ("share the dev server"), find
the port rather than guessing at 3000:

```bash
ss -ltnp                           # Linux: what is listening, with the process name
lsof -iTCP -sTCP:LISTEN -nP        # macOS
```

When nothing is listening on the port yet, `tn tunnel open` warns but starts anyway. The link
returns 502 until the server comes up, which is fine if the user is about to start it. Do not
treat that warning as a failure.

## Stopping

```bash
tn tunnel close 3000 --json      # by port, no prompt: use this form
tn tunnel close --all --json     # every forward
```

Without a port or `--all`, it picks interactively, and without a terminal it exits 2 with the
`choices`. Unless `--for` was given, nothing else ends a forward: it has no expiry, and it outlives
the terminal it started in. **The link does not come back.** The tunnel is temporary, so closing
deletes it at the service end, and the next `tn tunnel open 3000` gets a different URL. Say so
before closing a link the user has already shared.

Leaving a forward running is the normal state. When finishing a session, mention any forwards
that are still up, but do not close them unasked.

## When it is not set up

The fix comes back as exit 3 with the command to run in `fix`. Both fixes are one-time, and
neither can be automated:

- **`devtunnel is not installed`**: `dot apply vscode`.
- **Not logged in to dev tunnels**: `devtunnel user login -g` (GitHub, opens a browser). Add `-d`
  for a device code when there is no browser on this machine.

This login is **separate from `code tunnel user login`**, even on the same GitHub account: the two
keep separate token caches. Being signed in for vscode.dev says nothing about whether
`tn tunnel open` will work. `tn doctor --json` checks both.

## Not the same thing as the vscode.dev tunnel

The `vscode` bundle installs a service that makes *this machine's editor* reachable at vscode.dev.
That is remote **development**: always on and machine-wide. `tn tunnel` forwards one **port** of
one running server, on demand. A user asking for "a link to my app" wants this. A user asking to
"open my machine in the browser" wants the vscode.dev tunnel. See
[bundles/vscode/README.md](../../../vscode/README.md).

The dev tunnel needs no separate account and shows up in VS Code's PORTS panel.
