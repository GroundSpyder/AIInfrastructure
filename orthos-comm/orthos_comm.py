"""orthos-comm — Mattermost client for AI-to-AI async chat on the `orthos` channel.

Subcommands:
    post "<message>"                 send a message as kyle-bot
    post --from-file <path>          read message body from a file (avoids shell-quoting hazards)
    post --from-stdin                read message body from stdin (pipe-friendly)
    read [--since TIMESTAMP | --all] read messages since last successful read
    whoami                           verify token + identity
    cursor                           show the saved last-read cursor
    refresh-token                    fetch the token from Doppler and write it to the
                                     file fallback, so transient Doppler API blips
                                     don't break sends

Auth precedence (kyle-bot token):
    1. env MATTERMOST_KYLE_BOT_TOKEN
    2. doppler -p birdmug-services -c prd_orthos_comm secrets get MATTERMOST_KYLE_BOT_TOKEN --plain
    3. ~/.config/orthos-comm/token-kyle  (cross-platform; uses Path.home())

    `refresh-token` populates source #3 from source #2 so source #2 going briefly
    unavailable (Doppler API hiccup) doesn't break sends. Run it after any
    rotation of MATTERMOST_KYLE_BOT_TOKEN in Doppler. Cross-fleet you can run it
    once per host (MB, Kaydanski; Toshi uses personal user auth and doesn't need
    the file fallback).

Config dir override:
    Set ORTHOS_COMM_CONFIG_DIR to use a non-default location for token + cursor.

Cursor:
    Per-bot file at <config-dir>/cursor-<bot>.json — Unix ms timestamp of the most
    recent post observed. `read` returns posts strictly after that.

Exit codes:
    0 success
    2 auth / config error (also: corrupt cursor file)
    3 network / Mattermost error (also: malformed Mattermost response)

Failure-surface contract:
    All errors and warnings go to stderr. This CLI is invoked from cron / n8n /
    watchdog; stderr is the only signal those callers see. Do not introduce
    silent fallbacks — every recovered error must emit a WARN line, and every
    unrecoverable error must exit non-zero with an ERROR line that names the
    cause and the relevant path or response.
"""

from __future__ import annotations

import argparse
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MATTERMOST_BASE = "https://chat.birdmug.com/api/v4"
ORTHOS_CHANNEL_ID = "qoia7dfowb8q9n16ukkidb874c"
BOT_NAME = "kyle-bot"

def _resolve_config_dir() -> Path:
    """Cross-platform config dir. Honors $ORTHOS_COMM_CONFIG_DIR override."""
    override = os.environ.get("ORTHOS_COMM_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".config" / "orthos-comm"


_CONFIG_DIR = _resolve_config_dir()
_TOKEN_FALLBACK = _CONFIG_DIR / "token-kyle"
_CURSOR_PATH = _CONFIG_DIR / f"cursor-{BOT_NAME}.json"


def _load_token() -> str:
    """Resolve the kyle-bot token. Surface a real error if no source has it."""
    env_token = os.environ.get("MATTERMOST_KYLE_BOT_TOKEN")
    if env_token:
        return env_token.strip()

    try:
        result = subprocess.run(
            [
                "doppler", "secrets", "get", "MATTERMOST_KYLE_BOT_TOKEN",
                "-p", "birdmug-services", "-c", "prd_orthos_comm",
                "--plain",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        # Doppler ran but didn't return a usable secret — surface why before
        # falling through, so a rotated-in-Doppler-but-stale-on-disk token
        # doesn't silently produce 401s downstream.
        print(
            f"WARN: doppler returned rc={result.returncode}; "
            f"stderr={result.stderr.strip()!r}. Falling back to file token.",
            file=sys.stderr,
        )
    except FileNotFoundError:
        # Doppler CLI not installed on this host — expected on Toshi/Kaydanski today.
        pass
    except subprocess.TimeoutExpired:
        print(
            "WARN: doppler timed out after 10s; falling back to file token.",
            file=sys.stderr,
        )

    if _TOKEN_FALLBACK.exists():
        return _TOKEN_FALLBACK.read_text(encoding="ascii").strip()

    print(
        "ERROR: no kyle-bot token found. Looked in MATTERMOST_KYLE_BOT_TOKEN env var, "
        f"Doppler (birdmug-services/prd_orthos_comm), and {_TOKEN_FALLBACK}.",
        file=sys.stderr,
    )
    sys.exit(2)


def _api_optional(method: str, path: str, token: str) -> dict | None:
    """Like _api but returns None on failure instead of exiting.

    Used for non-critical sub-calls (e.g. username resolution) where one bad
    response shouldn't kill the whole command. Failure is still surfaced to
    stderr — not silent.
    """
    try:
        return _api(method, path, token)
    except SystemExit:
        print(
            f"WARN: optional API call {method} {path} failed; continuing with fallback.",
            file=sys.stderr,
        )
        return None


def _api(method: str, path: str, token: str, body: dict | None = None) -> dict:
    """Single Mattermost REST call. Raises on non-2xx, surfaces server's error body."""
    url = MATTERMOST_BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    # Cloudflare blocks default Python urllib UA (error 1010). Use a labeled UA.
    req.add_header("User-Agent", "orthos-comm/0.1 (+falkensteink/AIInfrastructure)")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return json.loads(raw)
            except json.JSONDecodeError as e:
                # 200 OK from Mattermost but non-JSON body — Cloudflare interstitial,
                # proxy error page, or contract drift. Refuse to silently treat as empty.
                print(
                    f"ERROR: non-JSON response from {method} {path} "
                    f"(status={resp.status}, len={len(raw)}): {raw[:500]!r} ({e})",
                    file=sys.stderr,
                )
                sys.exit(3)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        print(f"ERROR {e.code} from Mattermost: {body_text}", file=sys.stderr)
        sys.exit(3)
    except urllib.error.URLError as e:
        print(f"ERROR reaching {url}: {e.reason}", file=sys.stderr)
        sys.exit(3)


def _read_cursor() -> int:
    """Return saved cursor, or 0 if no cursor exists. Refuse to default-to-0 on corruption.

    A silent default-to-0 on a corrupt cursor file would re-flood the channel
    output on the next `read` — under cron/n8n that's a real failure mode.
    """
    if not _CURSOR_PATH.exists():
        return 0
    try:
        data = json.loads(_CURSOR_PATH.read_text())
        return int(data["since_ms"])
    except (json.JSONDecodeError, KeyError, ValueError, OSError) as e:
        print(
            f"ERROR: cursor file {_CURSOR_PATH} is corrupt "
            f"({type(e).__name__}: {e}). Refusing to default to since_ms=0 "
            f"(would re-read every historical message). "
            f"Delete the file to start fresh, or pass --since <ms>.",
            file=sys.stderr,
        )
        sys.exit(2)


def _write_cursor(ts_ms: int) -> None:
    """Atomic cursor write — write to temp then rename. Survives Ctrl-C / power loss."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _CURSOR_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"since_ms": ts_ms, "updated_at": int(time.time())}))
    os.replace(tmp, _CURSOR_PATH)  # atomic on POSIX and Windows


def cmd_whoami(token: str) -> None:
    me = _api("GET", "/users/me", token)
    print(f"username:     {me['username']}")
    print(f"user_id:      {me['id']}")
    print(f"is_bot:       {me.get('is_bot', False)}")
    print(f"display_name: {me.get('first_name') or me.get('username')}")


def _resolve_message(
    positional: str | None,
    from_file: str | None,
    from_stdin: bool,
) -> str:
    """Resolve the post body from exactly one of: positional arg, --from-file, --from-stdin.

    Raises (via sys.exit) on:
    - none of the three provided
    - more than one provided
    - --from-file path missing / unreadable / not a regular file
    - resolved body empty or whitespace-only
    """
    # Count explicit-source provision via `is not None` (not truthiness), so empty-string
    # inputs like `post ""` or `--from-file ""` are still recognized as "provided" and
    # produce the more accurate "empty message" error rather than "no source provided."
    sources = (
        (positional is not None)
        + (from_file is not None)
        + bool(from_stdin)
    )
    if sources == 0:
        print(
            "ERROR: post requires a message. Provide it as a positional arg, "
            "--from-file <path>, or --from-stdin.",
            file=sys.stderr,
        )
        sys.exit(2)
    if sources > 1:
        print(
            "ERROR: post message specified by more than one source. Use exactly "
            "one of: positional arg, --from-file, --from-stdin.",
            file=sys.stderr,
        )
        sys.exit(2)

    if positional is not None:
        message = positional
    elif from_file is not None:
        # Skip an explicit is_file() check — let read_text raise and let the unified
        # handler catch FileNotFoundError / IsADirectoryError / PermissionError /
        # OSError / UnicodeDecodeError uniformly. Path.is_file() itself can raise
        # PermissionError (parent dir lacks +x), which would have been an unhandled
        # traceback in the prior shape.
        try:
            message = Path(from_file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(
                f"ERROR: failed to read --from-file {from_file} as UTF-8 "
                f"({type(e).__name__}: {e}).",
                file=sys.stderr,
            )
            sys.exit(2)
    else:  # from_stdin
        # Block --from-stdin against a TTY upfront — otherwise sys.stdin.read()
        # hangs forever waiting for EOF (Ctrl-D / Ctrl-Z). Common under cron / n8n
        # / watchdog where stdin sometimes gets bound to a TTY accidentally.
        if sys.stdin.isatty():
            print(
                "ERROR: --from-stdin requires piped input; stdin is a TTY. "
                "Use `cat file | orthos-comm post --from-stdin` or `--from-file <path>`.",
                file=sys.stderr,
            )
            sys.exit(2)
        try:
            message = sys.stdin.read()
        except (OSError, UnicodeDecodeError, ValueError, KeyboardInterrupt) as e:
            # ValueError covers "I/O operation on closed file";
            # KeyboardInterrupt covers Ctrl-C while blocked on read.
            print(
                f"ERROR: failed to read message from stdin "
                f"({type(e).__name__}: {e}).",
                file=sys.stderr,
            )
            sys.exit(2)

    if not message.strip():
        src_label = (
            "positional arg" if positional is not None
            else f"file {from_file}" if from_file is not None
            else "stdin"
        )
        print(f"ERROR: empty message (resolved from {src_label}).", file=sys.stderr)
        sys.exit(2)
    return message


def cmd_post(
    token: str,
    positional: str | None,
    from_file: str | None,
    from_stdin: bool,
) -> None:
    message = _resolve_message(positional, from_file, from_stdin)
    post = _api("POST", "/posts", token, {
        "channel_id": ORTHOS_CHANNEL_ID,
        "message": message,
    })
    print(f"posted (id={post['id']}, create_at={post['create_at']})")


def cmd_read(token: str, since_ms: int | None, all_posts: bool, mark_read: bool) -> None:
    """Print posts in chronological order, oldest first, with sender labels."""
    if all_posts:
        since_ms = 0
    elif since_ms is None:
        since_ms = _read_cursor()

    # per_page=200 prevents silently truncating large catch-up reads on chatty days.
    qs = f"?since={since_ms}&per_page=200" if since_ms > 0 else "?per_page=30"
    data = _api("GET", f"/channels/{ORTHOS_CHANNEL_ID}/posts{qs}", token)

    if "order" not in data or "posts" not in data:
        # Wrong-shape response — refuse to treat as "no new messages" silently.
        print(
            f"ERROR: Mattermost response missing expected keys (got {sorted(data.keys())}). "
            "Refusing to assume empty inbox.",
            file=sys.stderr,
        )
        sys.exit(3)

    order = list(reversed(data["order"]))
    posts = data["posts"]

    if not order:
        print("(no new messages)")
        return

    # Resolve usernames once per unique user_id. One bad lookup must not nuke the
    # whole read — fall back to a short id instead.
    user_ids = {posts[pid]["user_id"] for pid in order}
    usernames = {}
    for uid in user_ids:
        resp = _api_optional("GET", f"/users/{uid}", token)
        usernames[uid] = (resp or {}).get("username") or uid[:8]

    latest_ts = since_ms
    for pid in order:
        p = posts[pid]
        ts = p["create_at"]
        latest_ts = max(latest_ts, ts)
        author = usernames.get(p["user_id"], p["user_id"][:8])
        ts_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts / 1000))
        msg = p["message"] or "(empty)"
        prefix = "[system] " if p.get("type") else ""
        print(f"{ts_iso}  {author}: {prefix}{msg}")

    if mark_read and latest_ts > since_ms:
        _write_cursor(latest_ts)
        print(f"\n(cursor updated to {latest_ts})", file=sys.stderr)


def _fetch_token_from_doppler() -> str:
    """Read the kyle-bot token from Doppler. Exits non-zero on failure.

    Mirrors the Doppler invocation in _load_token but doesn't fall through to
    env / file — refresh-token's purpose is to repopulate the file from
    Doppler, so an env-var fallback would defeat the point and a file
    fallback would be circular.
    """
    try:
        result = subprocess.run(
            [
                "doppler", "secrets", "get", "MATTERMOST_KYLE_BOT_TOKEN",
                "-p", "birdmug-services", "-c", "prd_orthos_comm",
                "--plain",
            ],
            capture_output=True, text=True, timeout=15,
        )
    except FileNotFoundError:
        print(
            "ERROR: doppler CLI not found on PATH. refresh-token requires the "
            "Doppler CLI to read MATTERMOST_KYLE_BOT_TOKEN from "
            "birdmug-services/prd_orthos_comm. Install Doppler and authenticate "
            "(`doppler login`) before retrying.",
            file=sys.stderr,
        )
        sys.exit(2)
    except subprocess.TimeoutExpired:
        print(
            "ERROR: doppler timed out after 15s while fetching "
            "MATTERMOST_KYLE_BOT_TOKEN from birdmug-services/prd_orthos_comm. "
            "Retry when the Doppler API is responsive.",
            file=sys.stderr,
        )
        sys.exit(3)

    if result.returncode != 0 or not result.stdout.strip():
        print(
            f"ERROR: doppler returned rc={result.returncode} "
            f"with empty/blank stdout. stderr={result.stderr.strip()!r}. "
            "Confirm `doppler` is authenticated (`doppler me`) and that the "
            "MATTERMOST_KYLE_BOT_TOKEN secret exists in "
            "birdmug-services/prd_orthos_comm.",
            file=sys.stderr,
        )
        sys.exit(3)
    return result.stdout.strip()


def cmd_refresh_token() -> None:
    """Fetch the token from Doppler and write it to the file fallback.

    Makes botchat resilient to transient Doppler API hiccups — the script's
    3-level resolver checks Doppler before file, so steady state still uses
    Doppler (always fresh), but the file is the safety net.
    """
    token = _fetch_token_from_doppler()
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Atomic write — temp file then rename — to avoid a partial-write
    # window where another concurrent botchat could read a half-flushed
    # token. PID-suffixed tmp name so two concurrent refresh-token runs
    # don't race on the same .tmp path (would crash the second os.replace
    # on Windows when the source disappeared). os.replace is atomic on
    # both POSIX and Windows (Python docs).
    tmp = _TOKEN_FALLBACK.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(token, encoding="ascii")
    os.replace(tmp, _TOKEN_FALLBACK)
    # 0600 — owner read/write only. On POSIX this is enforced fully; on
    # Windows os.chmod only toggles the readonly bit. For real Windows
    # ACL lockdown, run `icacls <path> /inheritance:r /grant:r %USERNAME%:F`
    # separately (one-time after first refresh).
    try:
        os.chmod(_TOKEN_FALLBACK, 0o600)
    except OSError as e:
        # Surface but don't fail — token is written, just under default perms.
        print(
            f"WARN: chmod 0o600 on {_TOKEN_FALLBACK} failed ({e}). "
            "Token written under default permissions.",
            file=sys.stderr,
        )
    print(
        f"refreshed: wrote {len(token)} bytes to {_TOKEN_FALLBACK}"
    )


def cmd_cursor() -> None:
    if not _CURSOR_PATH.exists():
        print("(no cursor yet — first read will start from channel beginning)")
        return
    try:
        data = json.loads(_CURSOR_PATH.read_text())
        ts = int(data["since_ms"])
        updated_at = int(data["updated_at"])
    except (json.JSONDecodeError, KeyError, ValueError, OSError) as e:
        print(
            f"ERROR: cursor file {_CURSOR_PATH} is corrupt "
            f"({type(e).__name__}: {e}). Delete it to start fresh.",
            file=sys.stderr,
        )
        sys.exit(2)
    iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts / 1000))
    print(f"since_ms:   {ts}")
    print(f"local time: {iso}")
    print(f"saved at:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(updated_at))}")


def main() -> None:
    p = argparse.ArgumentParser(prog="orthos-comm")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_post = sub.add_parser(
        "post",
        help="send a message as kyle-bot (positional arg, --from-file, or --from-stdin)",
    )
    p_post.add_argument(
        "message",
        nargs="?",
        default=None,
        help="message body as a positional arg (use --from-file for messages "
             "containing shell-special characters)",
    )
    p_post.add_argument(
        "--from-file",
        dest="from_file",
        default=None,
        metavar="PATH",
        help="read message body from a UTF-8 file (avoids shell quoting hazards)",
    )
    p_post.add_argument(
        "--from-stdin",
        dest="from_stdin",
        action="store_true",
        help="read message body from stdin (pipe-friendly)",
    )

    p_read = sub.add_parser("read", help="read new messages since last read")
    p_read.add_argument("--since", type=int, default=None,
                        help="Unix ms timestamp (overrides cursor)")
    p_read.add_argument("--all", action="store_true",
                        help="read most-recent posts regardless of cursor")
    p_read.add_argument("--no-mark", action="store_true",
                        help="do not advance the cursor (preview mode)")

    sub.add_parser("whoami", help="verify token + show bot identity")
    sub.add_parser("cursor", help="show the saved last-read cursor")
    sub.add_parser(
        "refresh-token",
        help="fetch the kyle-bot token from Doppler and write it to the file "
             "fallback (~/.config/orthos-comm/token-kyle) so transient Doppler "
             "API hiccups don't break sends. Run after rotation.",
    )

    args = p.parse_args()

    # refresh-token + cursor don't need a working token to run — refresh-token
    # IS the way to recover when no token is loadable yet; cursor just prints
    # local state. Loading a token here would defeat refresh-token's purpose.
    if args.cmd == "refresh-token":
        cmd_refresh_token()
        return
    if args.cmd == "cursor":
        cmd_cursor()
        return

    token = _load_token()

    if args.cmd == "post":
        cmd_post(token, args.message, args.from_file, args.from_stdin)
    elif args.cmd == "read":
        cmd_read(token, args.since, args.all, mark_read=not args.no_mark)
    elif args.cmd == "whoami":
        cmd_whoami(token)


if __name__ == "__main__":
    main()
