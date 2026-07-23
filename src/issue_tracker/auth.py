"""Authentication: API tokens (CLI/agents) and WebAuthn passkeys (web).

Auth is OFF by default so local/dev usage is unchanged. Set ``ISSUE_TRACKER_AUTH``
to a truthy value to require credentials on every data endpoint.

- **API tokens** are random strings shown once and stored only as SHA-256
  hashes. Sent as ``Authorization: Bearer <token>``.
- **Web sessions** are established with a passkey (WebAuthn) and carried in a
  signed, HttpOnly cookie.
- On first run with auth enabled and no admin token, a one-time bootstrap admin
  token is written to ``.issues/bootstrap-token.txt`` (mode 600).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone

from . import db

# --- Configuration ----------------------------------------------------------


def auth_enabled() -> bool:
    return os.environ.get("ISSUE_TRACKER_AUTH", "").lower() in ("1", "true", "yes", "on")


def rp_id() -> str:
    # Relying Party ID = the site's registrable domain.
    return os.environ.get("ISSUE_TRACKER_RP_ID", "localhost")


def rp_name() -> str:
    return os.environ.get("ISSUE_TRACKER_RP_NAME", "Agent Issue Tracker")


def expected_origin() -> str:
    origin = os.environ.get("ISSUE_TRACKER_ORIGIN")
    if origin:
        return origin
    host = rp_id()
    return f"http://{host}" if host in ("localhost", "127.0.0.1") else f"https://{host}"


SESSION_COOKIE = "it_session"
CHALLENGE_COOKIE = "it_challenge"
SESSION_TTL = 60 * 60 * 24 * 14  # 14 days
CHALLENGE_TTL = 300  # 5 minutes
WEBAUTHN_USER_ID = b"issues-primary-user"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


# --- Server secret (for signing cookies) ------------------------------------

_secret_cache: bytes | None = None


def _secret_path():
    return db.db_path().parent / "secret.key"


def server_secret() -> bytes:
    global _secret_cache
    if _secret_cache is not None:
        return _secret_cache
    path = _secret_path()
    if path.exists():
        _secret_cache = path.read_bytes()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        secret = secrets.token_bytes(32)
        path.write_bytes(secret)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        _secret_cache = secret
    return _secret_cache


# --- Signed cookies ---------------------------------------------------------


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _sign_payload(payload: dict) -> str:
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(server_secret(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64e(sig)}"


def _read_payload(cookie: str | None) -> dict | None:
    if not cookie or "." not in cookie:
        return None
    body, sig = cookie.rsplit(".", 1)
    expected = hmac.new(server_secret(), body.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(expected, _b64d(sig)):
            return None
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("exp", 0) < _epoch():
        return None
    return payload


def make_session(sub: str) -> str:
    return _sign_payload({"sub": sub, "exp": _epoch() + SESSION_TTL})


def read_session(cookie: str | None) -> str | None:
    payload = _read_payload(cookie)
    return payload.get("sub") if payload else None


def make_challenge_cookie(challenge: bytes, kind: str) -> str:
    return _sign_payload(
        {"c": _b64e(challenge), "k": kind, "exp": _epoch() + CHALLENGE_TTL}
    )


def read_challenge_cookie(cookie: str | None, kind: str) -> bytes | None:
    payload = _read_payload(cookie)
    if not payload or payload.get("k") != kind:
        return None
    try:
        return _b64d(payload["c"])
    except (KeyError, ValueError):
        return None


# --- API tokens -------------------------------------------------------------

TOKEN_PREFIX = "it_"


def _hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def create_token(
    conn: sqlite3.Connection, name: str, is_admin: bool = False
) -> tuple[str, dict]:
    """Create a token; returns (plaintext, row). The plaintext is shown once."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Token name must not be empty")
    plaintext = TOKEN_PREFIX + secrets.token_urlsafe(32)
    cur = conn.execute(
        "INSERT INTO api_tokens (name, token_hash, is_admin, created_at) "
        "VALUES (?, ?, ?, ?)",
        (name, _hash_token(plaintext), 1 if is_admin else 0, _now()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM api_tokens WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return plaintext, dict(row)


def verify_token(conn: sqlite3.Connection, plaintext: str | None) -> dict | None:
    if not plaintext:
        return None
    row = conn.execute(
        "SELECT * FROM api_tokens WHERE token_hash = ? AND revoked = 0",
        (_hash_token(plaintext),),
    ).fetchone()
    if row is None:
        return None
    conn.execute(
        "UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (_now(), row["id"])
    )
    conn.commit()
    return dict(row)


def list_tokens(conn: sqlite3.Connection, include_revoked: bool = False) -> list[dict]:
    q = "SELECT id, name, is_admin, created_at, last_used_at, revoked FROM api_tokens"
    if not include_revoked:
        q += " WHERE revoked = 0"
    q += " ORDER BY id"
    return [dict(r) for r in conn.execute(q).fetchall()]


def revoke_token(conn: sqlite3.Connection, token_id: int) -> bool:
    cur = conn.execute("UPDATE api_tokens SET revoked = 1 WHERE id = ?", (token_id,))
    conn.commit()
    return cur.rowcount > 0


def has_admin_token(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM api_tokens WHERE is_admin = 1 AND revoked = 0 LIMIT 1"
    ).fetchone()
    return row is not None


def ensure_bootstrap(conn: sqlite3.Connection) -> str | None:
    """If auth is enabled and there is no admin token, mint one and write it to
    ``.issues/bootstrap-token.txt``. Returns the plaintext if created."""
    if has_admin_token(conn):
        return None
    plaintext, _ = create_token(conn, "bootstrap", is_admin=True)
    path = db.db_path().parent / "bootstrap-token.txt"
    try:
        path.write_text(plaintext + "\n")
        os.chmod(path, 0o600)
    except OSError:
        pass
    return plaintext


# --- WebAuthn (passkeys) ----------------------------------------------------


def credentials(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM webauthn_credentials ORDER BY id"
        ).fetchall()
    ]


def has_credentials(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute("SELECT 1 FROM webauthn_credentials LIMIT 1").fetchone()
        is not None
    )


def registration_options(conn: sqlite3.Connection) -> str:
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    exclude = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credential_id"]))
        for c in credentials(conn)
    ]
    options = generate_registration_options(
        rp_id=rp_id(),
        rp_name=rp_name(),
        user_id=WEBAUTHN_USER_ID,
        user_name="issues",
        user_display_name="Issues",
        exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    return options_to_json(options), options.challenge


def verify_registration(
    conn: sqlite3.Connection, credential: dict, challenge: bytes, name: str
) -> dict:
    from webauthn import verify_registration_response
    from webauthn.helpers import bytes_to_base64url

    verification = verify_registration_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=rp_id(),
        expected_origin=expected_origin(),
    )
    cred_id = bytes_to_base64url(verification.credential_id)
    pub = bytes_to_base64url(verification.credential_public_key)
    transports = json.dumps(credential.get("response", {}).get("transports", []))
    conn.execute(
        "INSERT OR REPLACE INTO webauthn_credentials "
        "(credential_id, public_key, sign_count, name, transports, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (cred_id, pub, verification.sign_count, name or "passkey", transports, _now()),
    )
    conn.commit()
    return {"credential_id": cred_id, "name": name or "passkey"}


def authentication_options(conn: sqlite3.Connection):
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.structs import (
        PublicKeyCredentialDescriptor,
        UserVerificationRequirement,
    )

    allow = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credential_id"]))
        for c in credentials(conn)
    ]
    options = generate_authentication_options(
        rp_id=rp_id(),
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return options_to_json(options), options.challenge


def verify_authentication(
    conn: sqlite3.Connection, credential: dict, challenge: bytes
) -> dict:
    from webauthn import verify_authentication_response
    from webauthn.helpers import base64url_to_bytes

    raw_id = credential.get("id") or credential.get("rawId")
    row = conn.execute(
        "SELECT * FROM webauthn_credentials WHERE credential_id = ?", (raw_id,)
    ).fetchone()
    if row is None:
        raise ValueError("Unknown passkey")
    verification = verify_authentication_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=rp_id(),
        expected_origin=expected_origin(),
        credential_public_key=base64url_to_bytes(row["public_key"]),
        credential_current_sign_count=row["sign_count"],
    )
    conn.execute(
        "UPDATE webauthn_credentials SET sign_count = ?, last_used_at = ? WHERE id = ?",
        (verification.new_sign_count, _now(), row["id"]),
    )
    conn.commit()
    return {"name": row["name"] or "passkey"}
