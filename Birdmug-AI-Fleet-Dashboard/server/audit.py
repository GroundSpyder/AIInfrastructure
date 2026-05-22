"""Append-only audit log for model management actions.

Every write op (load, unload, pull, delete, env change, service restart,
warm-set edit) appends one JSON line to /data/fleet_audit.log inside the
container. The path is backed by a named volume (fleet_audit_data) so
the log survives container rebuilds.

Format: one JSON object per line — {ts, action, host, model, user,
status, error, extras}. Newest entries last. The /api/audit route tails
the file and returns the most recent N entries.

No silent failures: if writing the log fails (disk full, perms wrong),
we log a WARNING but the calling operation still returns its real
result — losing an audit entry is bad but not as bad as failing the
user's actual action because the log file is broken.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

log = logging.getLogger(__name__)

AUDIT_PATH = os.environ.get("FLEET_AUDIT_PATH", "/data/fleet_audit.log")


def record(
    action: str,
    host: str | None = None,
    model: str | None = None,
    user: str | None = None,
    status: str = "ok",
    error: str | None = None,
    **extras: Any,
) -> None:
    """Append one entry to the audit log. Best-effort — never raises."""
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "action": action,
        "host": host,
        "model": model,
        "user": user,
        "status": status,
        "error": error,
        **extras,
    }
    try:
        os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
        with open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except OSError as e:
        log.warning("audit write failed path=%s err=%s entry=%s", AUDIT_PATH, e, entry)


def tail(limit: int = 200) -> list[dict[str, Any]]:
    """Return the most recent `limit` audit entries, newest last."""
    try:
        with open(AUDIT_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            # Corrupt line — surface as a sentinel so we know it exists
            out.append({"ts": "?", "action": "corrupt-entry", "raw": line[:200]})
    return out
