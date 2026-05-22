# orthos-comm - Codex project rules

This file mirrors [CLAUDE.md](./CLAUDE.md). Codex reads `AGENTS.md`; Claude reads `CLAUDE.md`. Keep both in sync.
If there is drift, `CLAUDE.md` is the source of truth.

If the Claude guide refers to `.claude/` assets, use them by type: `.claude/agents/*.md` files are reusable prompt/reference docs you can read directly; settings, scheduled tasks, and slash commands are Claude runtime features and should be treated as reference only.

---
# orthos-comm — instructions for Claude

You are in the `orthos-comm` directory. This is a small CLI Kyle uses to
send/receive async messages on a shared Mattermost channel with Chris's
Codex sessions. See `README.md` for the full picture.

**Naming:** the directory is `orthos-comm` and the Python module is
`orthos_comm.py` because the underlying Mattermost channel is `orthos`.
The user-facing wrapper on PATH is `botchat` (avoids collision with
"Orthos" the inference node). When Kyle says "bot chat" / "the bot
channel" / asks to "post to the bots", they mean this tool.

## When asked to touch this code

- **Test cross-platform.** Any change touching paths must work on both
  Windows (`Path.home()` → `C:\Users\<user>`) and Linux (`Path.home()` →
  `/home/<user>`). Don't reintroduce `os.environ["USERPROFILE"]`.
- **Stdlib only.** No `requests`, no `httpx`, no third-party deps. This
  ships to three hosts as a file copy — adding a dep means adding a pip
  install step to each host's deploy.
- **No silent fallbacks.** If the token can't be found or the API
  returns an error, exit non-zero with a clear stderr message. The user
  (or a calling script) needs to know it failed.
- **Cloudflare gotcha.** `chat.birdmug.com` is behind Cloudflare; the
  default Python urllib User-Agent triggers error 1010. Always set a
  non-default UA. The shipped code does this — don't remove it.

## When asked to use this code from a Claude session

- The slash command `/orthos` is the intended interface. Prefer it over
  raw CLI calls when in an interactive Claude Code session.
- `read` advances the cursor. If you only want to peek, use `read --no-mark`.
- Never auto-reply to incoming messages. Surface them to Kyle. He
  decides what to send back. (This is encoded in the slash command, but
  worth re-stating: AI-to-AI conversation without human routing is the
  failure mode being avoided.)
- Don't send secrets through the channel — it's visible to both Kyle and
  Chris.

## When asked to extend this

Likely directions and what to think about:

- **A second channel** (e.g., for fleet-event spam separate from
  human-routed notes): hardcoded `ORTHOS_CHANNEL_ID` becomes a config or
  CLI arg. Cursor file gets a per-channel suffix.
- **A second bot** (a teammate joins): see "Add a new bot" in README.
  Pattern is documented; don't reinvent it.
- **Shared cursor across hosts**: today each host's cursor is local.
  Moving to a shared location (Doppler, NFS, Mattermost custom prop) is
  doable but introduces a write coordination problem — discuss with Kyle
  before implementing.
- **Webhook-style push instead of polling**: would require an inbound
  endpoint somewhere reachable. Toshi already runs cloudflared; could
  expose a webhook receiver there. But "git fetch" semantics are
  intentional — don't replace polling with push without discussing with
  Kyle first.

## Before any change to this directory

Run `code-reviewer` (read-only) on changed files. The CLI is small but
touches auth, error paths, and network calls — exactly the surface where
silent failures sneak in.

## Cross-references

- `../GroundSpyder-API-Orthos-ReadMe.md` — the Orthos *inference* node
  (separate concept from this comms channel; both use the word "orthos"
  because Chris's box does both)
- `../Birdmug-Orthos-Blackflame-Dashboard/` — read-only Orthos inference
  dashboard (also unrelated to this comms channel; same name reuse)
- `../../TOSHI.md` — Mattermost lives on Toshi; deployment/admin context
- `c:/falkensteink/CLAUDE.md` — root falkensteink conventions
