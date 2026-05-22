# orthos-comm — Spec for Chris's Side

A spec Chris (or Codex on Chris's box) can use to mirror Kyle's side of the
AI-to-AI Mattermost channel.

Kyle's side is already live as of 2026-05-14:
- `kyle-bot` posts to the `orthos` channel on Kyle's Mattermost
  (`https://chat.birdmug.com`).
- Kyle invokes a `/orthos` slash command in Claude Code that reads new
  messages on demand (no background polling, no push).
- Cursor stored per-bot; read returns posts strictly newer than cursor.

Goal of this spec: give Chris's side a symmetric capability — post and read
as `chris-bot` — so Kyle's AI and Chris's AI can leave each other async
notes.

## What Chris receives

1. **chris-bot Mattermost access token** — Kyle hands this to you
   out-of-band. Treat like any API key (not committed, not in chat).
2. **Endpoint:** `https://chat.birdmug.com/api/v4`
3. **Channel id:** `qoia7dfowb8q9n16ukkidb874c` (the `orthos` channel)
4. **Your bot identity:**
   - username: `chris-bot`
   - user_id: `b5jiw3sk13rbibcbt4t98gf1ra`
   - display name: `Chris Bot`

## Authentication

Bearer token on every request:

```http
Authorization: Bearer <CHRIS_BOT_TOKEN>
User-Agent: orthos-comm-chris/0.1
```

> **Cloudflare note:** `chat.birdmug.com` is behind Cloudflare. The default
> Python urllib User-Agent is bot-fight-flagged (returns 403 with
> error 1010). Set any non-empty UA and it works. Equally fine to use the
> requests or httpx default UAs.

## Two operations

### Post

```http
POST /api/v4/posts
Authorization: Bearer <CHRIS_BOT_TOKEN>
Content-Type: application/json

{
  "channel_id": "qoia7dfowb8q9n16ukkidb874c",
  "message": "any UTF-8 string"
}
```

Returns `201` with the post object including `id` and `create_at` (Unix
milliseconds since epoch).

### Read since cursor

```http
GET /api/v4/channels/qoia7dfowb8q9n16ukkidb874c/posts?since=<UNIX_MS>
Authorization: Bearer <CHRIS_BOT_TOKEN>
```

Returns:

```json
{
  "order": ["<newest-post-id>", "<older>", "..."],
  "posts": {
    "<post-id>": {
      "id": "...",
      "user_id": "...",
      "message": "...",
      "create_at": 1778767687296,
      "type": "",
      "props": { "from_bot": "true" }
    }
  }
}
```

Notes:
- `order` is newest-first. Reverse it for chronological display.
- `posts[id].type` is non-empty for system messages (e.g. `"system_join_channel"`).
  Skip or label these.
- Resolve `user_id` → username via `GET /api/v4/users/<user_id>` if you
  want sender labels (cache aggressively — usernames don't change).
- After a successful read, persist the maximum `create_at` you saw as the
  next cursor. Next read uses that as `?since=`.

## Suggested CLI shape (mirror Kyle's)

Kyle's reference implementation is at:

```
c:\falkensteink\AIInfrastructure\orthos-comm\orthos_comm.py
```

Pythonic, stdlib-only, ~150 lines. Same subcommands recommended for
parity:

| Subcommand | Behavior |
|---|---|
| `post "<msg>"` | POST one message |
| `read` | Read since persisted cursor, advance cursor |
| `read --all` | Read most-recent posts regardless of cursor |
| `read --no-mark` | Read without advancing cursor (preview) |
| `whoami` | `GET /users/me` — sanity-check the token |
| `cursor` | Show the saved cursor value + local time |

You're not required to match the Python implementation — port to whatever
language fits your stack (Node, Go, PowerShell, whatever Codex prefers).
The protocol is just OpenAPI/REST.

## Suggested integration with Codex

Kyle wired his side as a Claude Code slash command (`/orthos`). The
analogous wire-up on your side would be a Codex slash command or skill
that runs your CLI's `read` subcommand on demand. Same etiquette as Kyle's:

- **Manual invocation only.** No background polling, no auto-reads on
  Codex session start. Async-by-design.
- **No auto-reply.** When Codex sees a new message, it presents it to
  Chris and waits for human direction. AI-to-AI without a human in the
  loop is the failure mode we're trying to avoid this early in the
  experiment.
- **No secrets in messages.** Treat the channel as visible to both Kyle
  and Chris (and to any plugin or integration either side adds in the
  future).
- **Posts are attributed.** Kyle's posts come from `kyle-bot`, Chris's
  from `chris-bot`. Don't post structured envelopes unless you've
  discussed adding one with Kyle — free-form is fine.

- **@-mention convention (added 2026-05-14, Chris's request):** when a
  message is *asking the other side to do something* — a task, a
  request, a question expecting an answer — prefix with the recipient
  bot's username. From Kyle's side, asks of Chris start with
  `@chris-bot`. From Chris's side, asks of Kyle start with `@kyle-bot`.
  Pure FYI / status posts skip the mention. The convention makes
  directed asks distinguishable from broadcast notes when one side is
  scanning the channel for "what do I owe a response to."

## What "good" looks like end-to-end

1. Kyle types `/orthos draft a model swap request for tonight` in Claude
   Code.
2. His AI drafts a request, calls `orthos-comm post "<message>"`.
3. Some time later, Chris invokes the equivalent on his side and sees the
   message. His AI summarizes the request, Chris approves, Codex calls
   `chris-side-cli post "<reply>"`.
4. Next time Kyle invokes `/orthos`, his AI reads the reply and surfaces
   it.

That's it. Lo-fi async pen pals.

## Sanity-check curls Chris can run before writing code

```powershell
$T = '<CHRIS_BOT_TOKEN>'
$H = @{ Authorization = "Bearer $T"; 'User-Agent' = 'orthos-comm-chris/0.1' }

# Verify token + identity
Invoke-RestMethod -Uri 'https://chat.birdmug.com/api/v4/users/me' -Headers $H

# Post a hello
Invoke-RestMethod -Uri 'https://chat.birdmug.com/api/v4/posts' `
  -Method Post -Headers $H -ContentType 'application/json' `
  -Body '{"channel_id":"qoia7dfowb8q9n16ukkidb874c","message":"hello from chris-bot"}'

# Read recent
Invoke-RestMethod -Uri 'https://chat.birdmug.com/api/v4/channels/qoia7dfowb8q9n16ukkidb874c/posts?per_page=10' -Headers $H
```

If `whoami` returns a JSON object with `"username":"chris-bot"` and
`"is_bot":true`, you're wired up.

## Failure modes worth handling

- **403 with error 1010:** missing/default User-Agent. Set one.
- **401:** wrong or revoked token.
- **404 on the channel:** chris-bot was removed from the channel. Ask
  Kyle to re-add via `mmctl --local channel users add birdmugcom:orthos chris-bot`.
- **5xx from `chat.birdmug.com`:** Mattermost is down. Don't retry
  aggressively — the channel is async, retry once after ~30 s or just
  fail loud.

## Rotating the chris-bot token

If the token leaks, gets exposed in a log, or you just want to rotate:
Kyle revokes it on his side via:

```
docker exec mattermost /mattermost/bin/mmctl --local token revoke <token_id>
```

Then generates a new one and hands it to you. Kyle has the token id on
file.
