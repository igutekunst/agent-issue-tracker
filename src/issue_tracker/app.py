"""FastAPI application: JSON API + SSE live feed + static SPA hosting."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import FEATURES, __version__, auth, db, store

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Agent Issue Tracker", version=__version__)


@app.on_event("startup")
def _startup():
    if auth.auth_enabled():
        conn = db.connect()
        try:
            token = auth.ensure_bootstrap(conn)
        finally:
            conn.close()
        if token:
            print(
                "\n[auth] No admin token found — created a bootstrap token.\n"
                f"[auth] It is written to {db.db_path().parent / 'bootstrap-token.txt'}\n"
                "[auth] Use it to `issue login` and to enroll your first passkey.\n"
            )


# Endpoints reachable without authentication (so a logged-out client can load
# the SPA shell and complete a passkey login).
_PUBLIC_API = {
    "/api/auth/status",
    "/api/webauthn/login/begin",
    "/api/webauthn/login/finish",
}


def _needs_auth(path: str) -> bool:
    if path in _PUBLIC_API:
        return False
    return path.startswith("/api/") or path == "/events"


@app.middleware("http")
async def _auth_and_actor(request: Request, call_next):
    request.state.principal = None
    request.state.is_admin = False

    if not auth.auth_enabled():
        # Open mode: attribute changes, no gate. Clients may set X-Actor.
        store.set_actor(request.headers.get("x-actor") or "web")
        return await call_next(request)

    path = request.url.path
    authz = request.headers.get("authorization", "")
    bearer = authz[7:].strip() if authz[:7].lower() == "bearer " else None
    session_cookie = request.cookies.get(auth.SESSION_COOKIE)

    if bearer or session_cookie or _needs_auth(path):
        conn = db.connect()
        try:
            tok = auth.verify_token(conn, bearer) if bearer else None
        finally:
            conn.close()
        if tok:
            request.state.principal = tok["name"]
            request.state.is_admin = bool(tok["is_admin"])
        else:
            sub = auth.read_session(session_cookie)
            if sub:
                request.state.principal = sub
                request.state.is_admin = True  # the web user is the owner

    if _needs_auth(path) and request.state.principal is None:
        return JSONResponse(
            {"detail": "authentication required"}, status_code=401
        )

    store.set_actor(request.state.principal or "web")
    return await call_next(request)


def _conn():
    return db.connect()


def _require_admin(request: Request):
    if not auth.auth_enabled():
        return
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(status_code=403, detail="admin credential required")


def _cookie_secure() -> bool:
    return auth.expected_origin().startswith("https")


# --- Request models ---------------------------------------------------------


class IssueCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "open"
    priority: str = "P2"
    parent_id: int | None = None
    branch: str | None = None
    worktree: str | None = None
    assignee: str | None = None
    metadata: dict | None = None


class IssueUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    parent_id: int | None = None
    branch: str | None = None
    worktree: str | None = None
    assignee: str | None = None
    metadata: dict | None = None


class DepBody(BaseModel):
    blocker_id: int
    blocked_id: int


class CommentBody(BaseModel):
    body: str
    author: str = "agent"


class ProposeBody(BaseModel):
    key: str
    value: str | None = None
    operation: str = "set"
    author: str = "human"
    note: str = ""


def _guard(fn):
    try:
        return fn()
    except store.StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --- Meta -------------------------------------------------------------------


@app.get("/api/meta")
def meta():
    return {
        "statuses": store.STATUSES,
        "priorities": store.PRIORITIES,
        "version": __version__,
        "features": FEATURES,
    }


@app.get("/api/version")
def version():
    return {"version": __version__, "features": FEATURES}


@app.get("/api/activity")
def api_activity(limit: int = 50):
    conn = _conn()
    try:
        return store.activity(conn, limit=limit)
    finally:
        conn.close()


@app.get("/api/changes")
def api_changes(since: str | None = None):
    """Update sentinel: has anything changed since a token/timestamp?

    Returns the current ``token`` (the latest change id). Pass it back later as
    ``?since=<token>`` (or an ISO timestamp) to get the changes since then.
    """
    conn = _conn()
    try:
        token = store.latest_change_id(conn)
        rows = store.changes_since_any(conn, since) if since is not None else []
        return {
            "token": token,
            "since": since,
            "changed": bool(rows),
            "count": len(rows),
            "changes": rows,
        }
    finally:
        conn.close()


# --- Issues -----------------------------------------------------------------


@app.get("/api/graph")
def api_graph():
    conn = _conn()
    try:
        return store.graph(conn)
    finally:
        conn.close()


@app.get("/api/issues")
def api_list_issues(status: str | None = None, priority: str | None = None):
    conn = _conn()
    try:
        return store.list_issues(conn, status=status, priority=priority)
    finally:
        conn.close()


@app.get("/api/issues/{issue_id}")
def api_get_issue(issue_id: int):
    conn = _conn()
    try:
        issue = store.get_issue(conn, issue_id)
        if issue is None:
            raise HTTPException(status_code=404, detail=f"Issue #{issue_id} not found")
        issue["blockers"] = store.blockers_for(conn, issue_id)
        issue["blocks"] = store.blocked_by_for(conn, issue_id)
        issue["children"] = [
            c["id"] for c in store.list_issues(conn, parent_id=issue_id)
        ]
        issue["comments"] = store.list_comments(conn, issue_id)
        return issue
    finally:
        conn.close()


@app.post("/api/issues", status_code=201)
def api_create_issue(body: IssueCreate):
    conn = _conn()
    try:
        return _guard(lambda: store.create_issue(conn, **body.model_dump()))
    finally:
        conn.close()


@app.patch("/api/issues/{issue_id}")
def api_update_issue(issue_id: int, body: IssueUpdate):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    conn = _conn()
    try:
        return _guard(lambda: store.update_issue(conn, issue_id, **fields))
    finally:
        conn.close()


@app.delete("/api/issues/{issue_id}", status_code=204)
def api_delete_issue(issue_id: int):
    conn = _conn()
    try:
        _guard(lambda: store.delete_issue(conn, issue_id))
        return Response(status_code=204)
    finally:
        conn.close()


# --- Dependencies -----------------------------------------------------------


@app.post("/api/dependencies", status_code=201)
def api_add_dep(body: DepBody):
    conn = _conn()
    try:
        _guard(lambda: store.add_dependency(conn, body.blocker_id, body.blocked_id))
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/api/dependencies")
def api_remove_dep(blocker_id: int, blocked_id: int):
    conn = _conn()
    try:
        store.remove_dependency(conn, blocker_id, blocked_id)
        return {"ok": True}
    finally:
        conn.close()


# --- Comments ---------------------------------------------------------------


@app.get("/api/issues/{issue_id}/comments")
def api_list_comments(issue_id: int):
    conn = _conn()
    try:
        return store.list_comments(conn, issue_id)
    finally:
        conn.close()


@app.post("/api/issues/{issue_id}/comments", status_code=201)
def api_add_comment(issue_id: int, body: CommentBody):
    conn = _conn()
    try:
        return _guard(
            lambda: store.add_comment(
                conn, issue_id, body=body.body, author=body.author
            )
        )
    finally:
        conn.close()


@app.delete("/api/comments/{comment_id}", status_code=204)
def api_delete_comment(comment_id: int):
    conn = _conn()
    try:
        _guard(lambda: store.delete_comment(conn, comment_id))
        return Response(status_code=204)
    finally:
        conn.close()


# --- Knowledge base ---------------------------------------------------------


@app.get("/api/knowledge")
def api_kb():
    conn = _conn()
    try:
        return store.kb_all(conn)
    finally:
        conn.close()


@app.get("/api/knowledge/proposals")
def api_proposals(status: str | None = "pending"):
    conn = _conn()
    try:
        return store.list_proposals(conn, status=status)
    finally:
        conn.close()


@app.post("/api/knowledge/proposals", status_code=201)
def api_propose(body: ProposeBody):
    conn = _conn()
    try:
        return _guard(
            lambda: store.kb_propose(
                conn,
                key=body.key,
                value=body.value,
                operation=body.operation,
                author=body.author,
                note=body.note,
            )
        )
    finally:
        conn.close()


@app.post("/api/knowledge/proposals/{proposal_id}/approve")
def api_approve(proposal_id: int):
    conn = _conn()
    try:
        return _guard(lambda: store.approve_proposal(conn, proposal_id))
    finally:
        conn.close()


@app.post("/api/knowledge/proposals/{proposal_id}/reject")
def api_reject(proposal_id: int):
    conn = _conn()
    try:
        return _guard(lambda: store.reject_proposal(conn, proposal_id))
    finally:
        conn.close()


@app.post("/api/knowledge/proposals/{proposal_id}/withdraw")
def api_withdraw(proposal_id: int):
    conn = _conn()
    try:
        return _guard(lambda: store.withdraw_proposal(conn, proposal_id))
    finally:
        conn.close()


# --- Auth: status, tokens, passkeys -----------------------------------------


class TokenCreate(BaseModel):
    name: str
    is_admin: bool = False


class WebAuthnFinish(BaseModel):
    credential: dict
    name: str | None = None


@app.get("/api/auth/status")
def api_auth_status(request: Request):
    enabled = auth.auth_enabled()
    conn = _conn()
    try:
        has_passkey = auth.has_credentials(conn) if enabled else False
    finally:
        conn.close()
    return {
        "auth": enabled,
        "authenticated": getattr(request.state, "principal", None) is not None
        or not enabled,
        "is_admin": getattr(request.state, "is_admin", False) or not enabled,
        "principal": getattr(request.state, "principal", None),
        "has_passkey": has_passkey,
        "rp_id": auth.rp_id() if enabled else None,
    }


@app.get("/api/whoami")
def api_whoami(request: Request):
    return {
        "principal": getattr(request.state, "principal", None),
        "is_admin": getattr(request.state, "is_admin", False) or not auth.auth_enabled(),
    }


@app.post("/api/auth/logout")
def api_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.SESSION_COOKIE)
    return resp


@app.get("/api/tokens")
def api_list_tokens(request: Request):
    _require_admin(request)
    conn = _conn()
    try:
        return auth.list_tokens(conn)
    finally:
        conn.close()


@app.post("/api/tokens", status_code=201)
def api_create_token(request: Request, body: TokenCreate):
    _require_admin(request)
    conn = _conn()
    try:
        plaintext, row = auth.create_token(conn, body.name, is_admin=body.is_admin)
        return {"token": plaintext, **row}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@app.delete("/api/tokens/{token_id}")
def api_revoke_token(request: Request, token_id: int):
    _require_admin(request)
    conn = _conn()
    try:
        ok = auth.revoke_token(conn, token_id)
        if not ok:
            raise HTTPException(status_code=404, detail="token not found")
        return {"ok": True}
    finally:
        conn.close()


def _set_challenge(resp: Response, challenge: bytes, kind: str):
    resp.set_cookie(
        auth.CHALLENGE_COOKIE,
        auth.make_challenge_cookie(challenge, kind),
        max_age=auth.CHALLENGE_TTL,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
    )


@app.post("/api/webauthn/register/begin")
def api_register_begin(request: Request):
    _require_admin(request)
    conn = _conn()
    try:
        options_json, challenge = auth.registration_options(conn)
    finally:
        conn.close()
    resp = Response(content=options_json, media_type="application/json")
    _set_challenge(resp, challenge, "reg")
    return resp


@app.post("/api/webauthn/register/finish")
def api_register_finish(request: Request, body: WebAuthnFinish):
    _require_admin(request)
    challenge = auth.read_challenge_cookie(
        request.cookies.get(auth.CHALLENGE_COOKIE), "reg"
    )
    if challenge is None:
        raise HTTPException(status_code=400, detail="registration challenge expired")
    conn = _conn()
    try:
        result = auth.verify_registration(
            conn, body.credential, challenge, body.name or "passkey"
        )
    except Exception as exc:  # noqa: BLE001 - surface verification errors
        raise HTTPException(status_code=400, detail=f"registration failed: {exc}")
    finally:
        conn.close()
    resp = JSONResponse({"ok": True, **result})
    resp.delete_cookie(auth.CHALLENGE_COOKIE)
    return resp


@app.post("/api/webauthn/login/begin")
def api_login_begin():
    conn = _conn()
    try:
        if not auth.has_credentials(conn):
            raise HTTPException(status_code=400, detail="no passkeys registered")
        options_json, challenge = auth.authentication_options(conn)
    finally:
        conn.close()
    resp = Response(content=options_json, media_type="application/json")
    _set_challenge(resp, challenge, "login")
    return resp


@app.post("/api/webauthn/login/finish")
def api_login_finish(request: Request, body: WebAuthnFinish):
    challenge = auth.read_challenge_cookie(
        request.cookies.get(auth.CHALLENGE_COOKIE), "login"
    )
    if challenge is None:
        raise HTTPException(status_code=400, detail="login challenge expired")
    conn = _conn()
    try:
        result = auth.verify_authentication(conn, body.credential, challenge)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"login failed: {exc}")
    finally:
        conn.close()
    resp = JSONResponse({"ok": True, **result})
    resp.delete_cookie(auth.CHALLENGE_COOKIE)
    resp.set_cookie(
        auth.SESSION_COOKIE,
        auth.make_session(f"web:{result['name']}"),
        max_age=auth.SESSION_TTL,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
    )
    return resp


# --- SSE live feed ----------------------------------------------------------


@app.get("/events")
async def events(request: Request):
    """Server-Sent Events stream of change-log entries.

    Tails the ``change_log`` table so updates from *any* process (CLI or web)
    are pushed to connected clients.
    """

    async def gen():
        conn = _conn()
        try:
            last_id = store.latest_change_id(conn)
            # Prompt clients to do an initial load.
            yield _sse("hello", {"last_id": last_id})
            while True:
                if await request.is_disconnected():
                    break
                rows = store.changes_since(conn, last_id)
                if rows:
                    last_id = rows[-1]["id"]
                    yield _sse("change", {"changes": rows, "last_id": last_id})
                else:
                    # Comment line acts as a keep-alive.
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.75)
        finally:
            conn.close()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# --- Static SPA (mounted last so API routes take precedence) ----------------

if STATIC_DIR.exists():

    @app.get("/", include_in_schema=False)
    def _index():
        # Never cache the HTML entry point, so a rebuilt bundle (hashed assets
        # referenced by a fresh index.html) is always picked up on reload.
        return FileResponse(
            str(STATIC_DIR / "index.html"),
            headers={"Cache-Control": "no-store"},
        )

    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
else:

    @app.get("/")
    def _no_build():
        return JSONResponse(
            status_code=200,
            content={
                "message": (
                    "Frontend is not built yet. Run `cd frontend && npm install "
                    "&& npm run build`, or use the API directly. The CLI works "
                    "without the frontend."
                )
            },
        )
