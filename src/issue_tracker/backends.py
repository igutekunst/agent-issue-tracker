"""Backend abstraction: the CLI operates either on the local SQLite database or
against a remote API server, behind one interface returning plain dicts.

Both backends raise ``store.StoreError`` on validation / not-found / auth errors
so the CLI can render them uniformly.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from . import config, db, store


def get_backend():
    server = config.resolve_server()
    if server:
        return RemoteBackend(server, config.resolve_token())
    return LocalBackend()


# --- Local (direct SQLite) --------------------------------------------------


class LocalBackend:
    remote = False
    location = None  # set to db path lazily

    def _do(self, fn):
        conn = db.connect()
        try:
            return fn(conn)
        finally:
            conn.close()

    # issues
    def create_issue(self, **fields):
        return self._do(lambda c: store.create_issue(c, **fields))

    def get_issue(self, issue_id):
        def go(c):
            issue = store.get_issue(c, issue_id)
            if issue is None:
                raise store.StoreError(f"Issue #{issue_id} not found")
            issue["blockers"] = store.blockers_for(c, issue_id)
            issue["blocks"] = store.blocked_by_for(c, issue_id)
            issue["children"] = [i["id"] for i in store.list_issues(c, parent_id=issue_id)]
            issue["comments"] = store.list_comments(c, issue_id)
            return issue

        return self._do(go)

    def list_issues(self, status=None, priority=None):
        return self._do(lambda c: store.list_issues(c, status=status, priority=priority))

    def update_issue(self, issue_id, **fields):
        return self._do(lambda c: store.update_issue(c, issue_id, **fields))

    def delete_issue(self, issue_id):
        return self._do(lambda c: store.delete_issue(c, issue_id))

    def graph(self):
        return self._do(store.graph)

    # dependencies
    def add_dependency(self, blocker, blocked):
        return self._do(lambda c: store.add_dependency(c, blocker, blocked))

    def remove_dependency(self, blocker, blocked):
        return self._do(lambda c: store.remove_dependency(c, blocker, blocked))

    # comments
    def add_comment(self, issue_id, body, author="agent"):
        return self._do(lambda c: store.add_comment(c, issue_id, body=body, author=author))

    def list_comments(self, issue_id):
        return self._do(lambda c: store.list_comments(c, issue_id))

    def delete_comment(self, comment_id):
        return self._do(lambda c: store.delete_comment(c, comment_id))

    # knowledge base
    def kb_all(self):
        return self._do(store.kb_all)

    def kb_get(self, key):
        return self._do(lambda c: store.kb_get(c, key))

    def kb_propose(self, key, value, operation="set", author="agent", note=""):
        return self._do(
            lambda c: store.kb_propose(
                c, key, value, operation=operation, author=author, note=note
            )
        )

    def list_proposals(self, status="pending"):
        return self._do(lambda c: store.list_proposals(c, status=status))

    def approve_proposal(self, pid):
        return self._do(lambda c: store.approve_proposal(c, pid))

    def reject_proposal(self, pid):
        return self._do(lambda c: store.reject_proposal(c, pid))

    def withdraw_proposal(self, pid):
        return self._do(lambda c: store.withdraw_proposal(c, pid))

    # activity / meta
    def activity(self, limit=20):
        return self._do(lambda c: store.activity(c, limit=limit))

    def changes(self, since=None):
        def go(c):
            token = store.latest_change_id(c)
            rows = store.changes_since_any(c, since) if since is not None else []
            return {
                "token": token,
                "since": since,
                "changed": bool(rows),
                "count": len(rows),
                "changes": rows,
            }

        return self._do(go)

    def whoami(self):
        return {"principal": None, "is_admin": True, "mode": "local"}

    # export / import
    def export(self):
        return self._do(store.export_all)

    def import_bundle(self, bundle):
        return self._do(lambda c: store.import_bundle(c, bundle))

    # tokens (local admin: operate directly)
    def list_tokens(self):
        from . import auth

        return self._do(auth.list_tokens)

    def create_token(self, name, is_admin=False):
        from . import auth

        def go(c):
            plaintext, row = auth.create_token(c, name, is_admin=is_admin)
            return {"token": plaintext, **row}

        return self._do(go)

    def revoke_token(self, token_id):
        from . import auth

        def go(c):
            if not auth.revoke_token(c, token_id):
                raise store.StoreError(f"Token #{token_id} not found")
            return {"ok": True}

        return self._do(go)


# --- Remote (HTTP API) ------------------------------------------------------


class RemoteBackend:
    remote = True

    def __init__(self, server: str, token: str | None):
        self.server = server.rstrip("/")
        self.token = token
        self.location = self.server

    def _request(self, method, path, body=None, params=None):
        url = self.server + path
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.reason
            try:
                payload = json.loads(exc.read())
                detail = payload.get("detail", detail)
            except (json.JSONDecodeError, ValueError, OSError):
                pass
            if exc.code == 401:
                detail = "authentication failed — run `issue login` or check your token"
            elif exc.code == 403:
                detail = "forbidden — an admin token is required for this action"
            raise store.StoreError(str(detail))
        except urllib.error.URLError as exc:
            raise store.StoreError(f"cannot reach {self.server}: {exc.reason}")

    # issues
    def create_issue(self, **fields):
        return self._request("POST", "/api/issues", body=fields)

    def get_issue(self, issue_id):
        return self._request("GET", f"/api/issues/{issue_id}")

    def list_issues(self, status=None, priority=None):
        return self._request(
            "GET", "/api/issues", params={"status": status, "priority": priority}
        )

    def update_issue(self, issue_id, **fields):
        return self._request("PATCH", f"/api/issues/{issue_id}", body=fields)

    def delete_issue(self, issue_id):
        return self._request("DELETE", f"/api/issues/{issue_id}")

    def graph(self):
        return self._request("GET", "/api/graph")

    # dependencies
    def add_dependency(self, blocker, blocked):
        return self._request(
            "POST", "/api/dependencies", body={"blocker_id": blocker, "blocked_id": blocked}
        )

    def remove_dependency(self, blocker, blocked):
        return self._request(
            "DELETE", "/api/dependencies",
            params={"blocker_id": blocker, "blocked_id": blocked},
        )

    # comments
    def add_comment(self, issue_id, body, author="agent"):
        return self._request(
            "POST", f"/api/issues/{issue_id}/comments",
            body={"body": body, "author": author},
        )

    def list_comments(self, issue_id):
        return self._request("GET", f"/api/issues/{issue_id}/comments")

    def delete_comment(self, comment_id):
        return self._request("DELETE", f"/api/comments/{comment_id}")

    # knowledge base
    def kb_all(self):
        return self._request("GET", "/api/knowledge")

    def kb_get(self, key):
        for row in self.kb_all() or []:
            if row["key"] == key:
                return row
        return None

    def kb_propose(self, key, value, operation="set", author="agent", note=""):
        return self._request(
            "POST", "/api/knowledge/proposals",
            body={"key": key, "value": value, "operation": operation,
                  "author": author, "note": note},
        )

    def list_proposals(self, status="pending"):
        return self._request(
            "GET", "/api/knowledge/proposals", params={"status": status}
        )

    def approve_proposal(self, pid):
        return self._request("POST", f"/api/knowledge/proposals/{pid}/approve")

    def reject_proposal(self, pid):
        return self._request("POST", f"/api/knowledge/proposals/{pid}/reject")

    def withdraw_proposal(self, pid):
        return self._request("POST", f"/api/knowledge/proposals/{pid}/withdraw")

    # activity / meta
    def activity(self, limit=20):
        return self._request("GET", "/api/activity", params={"limit": limit})

    def changes(self, since=None):
        return self._request("GET", "/api/changes", params={"since": since})

    def whoami(self):
        return self._request("GET", "/api/whoami")

    # export / import
    def export(self):
        return self._request("GET", "/api/export")

    def import_bundle(self, bundle):
        return self._request("POST", "/api/import", body=bundle)

    # tokens
    def list_tokens(self):
        return self._request("GET", "/api/tokens")

    def create_token(self, name, is_admin=False):
        return self._request(
            "POST", "/api/tokens", body={"name": name, "is_admin": is_admin}
        )

    def revoke_token(self, token_id):
        return self._request("DELETE", f"/api/tokens/{token_id}")
