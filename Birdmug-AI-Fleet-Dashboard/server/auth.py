"""BirdMug-Auth integration.

Read a JWT from the `birdmug_token` cookie (set by accounts.birdmug.com with
`domain=.birdmug.com`, so it reaches every BirdMug subdomain), or fall back to
`bm_token` cookie / `Authorization: Bearer <token>` header. Decode with
`BIRDMUG_JWT_SECRET` (HS256) — validate signature + issuer + expiry; skip the
audience check because obd isn't a registered `applications` row.

If the secret is the dev placeholder `dev-secret-change-in-prod`, auth is
disabled entirely (local development).

If no token / invalid token, redirect browsers to accounts.birdmug.com/login
with `?next=` back to the dashboard. API calls (anything under `/api/`) get
401 JSON instead of a redirect.
"""

import os
from functools import wraps
from urllib.parse import quote

import jwt
from flask import jsonify, redirect, request

JWT_SECRET = os.environ.get("BIRDMUG_JWT_SECRET", "dev-secret-change-in-prod")
AUTH_URL = os.environ.get("BIRDMUG_AUTH_URL", "https://accounts.birdmug.com")
DEV_DISABLED = JWT_SECRET == "dev-secret-change-in-prod"


def _extract_token() -> str | None:
    for name in ("birdmug_token", "bm_token"):
        v = request.cookies.get(name)
        if v:
            return v
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _is_valid(token: str) -> bool:
    try:
        jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            issuer="accounts.birdmug.com",
            options={"verify_aud": False},
        )
        return True
    except jwt.InvalidTokenError:
        return False


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if DEV_DISABLED:
            return f(*args, **kwargs)
        token = _extract_token()
        if token and _is_valid(token):
            return f(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"error": "unauthorized"}), 401
        return redirect(f"{AUTH_URL}/login?next={quote(request.url)}")

    return wrapper
