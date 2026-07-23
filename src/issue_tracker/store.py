"""Data-access layer for issues, dependencies, and the knowledge base.

All mutations record an entry in ``change_log`` so live viewers get updates.
This module contains no framework code — it is used by both the CLI and the
web API.
"""

from __future__ import annotations

import contextvars
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from . import db

# Who is making changes, used to attribute entries in the change feed. The web
# server sets this per request (X-Actor header); CLI/agent processes can set the
# ISSUE_TRACKER_ACTOR environment variable.
_actor: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "actor", default=None
)


def set_actor(actor: str | None) -> None:
    _actor.set(actor or None)


def _current_actor() -> str | None:
    return _actor.get() or os.environ.get("ISSUE_TRACKER_ACTOR") or None

# --- Vocabulary -------------------------------------------------------------

STATUSES = ["open", "in_progress", "blocked", "done", "cancelled"]
PRIORITIES = ["P0", "P1", "P2", "P3"]
OPEN_STATUSES = {"open", "in_progress", "blocked"}


class StoreError(Exception):
    """Raised for validation / integrity problems (cycles, bad values, etc.)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log(conn: sqlite3.Connection, kind: str, action: str, ref: Any) -> None:
    conn.execute(
        "INSERT INTO change_log (kind, action, ref, actor, ts) VALUES (?, ?, ?, ?, ?)",
        (kind, action, str(ref), _current_actor(), _now()),
    )


# --- Issues -----------------------------------------------------------------


def _row_to_issue(row: sqlite3.Row) -> dict:
    d = dict(row)
    try:
        d["metadata"] = json.loads(d.get("metadata") or "{}")
    except (json.JSONDecodeError, TypeError):
        d["metadata"] = {}
    return d


def create_issue(
    conn: sqlite3.Connection,
    title: str,
    description: str = "",
    status: str = "open",
    priority: str = "P2",
    parent_id: int | None = None,
    branch: str | None = None,
    worktree: str | None = None,
    assignee: str | None = None,
    metadata: dict | None = None,
) -> dict:
    title = (title or "").strip()
    if not title:
        raise StoreError("Issue title must not be empty")
    if status not in STATUSES:
        raise StoreError(f"Invalid status {status!r}; must be one of {STATUSES}")
    if priority not in PRIORITIES:
        raise StoreError(f"Invalid priority {priority!r}; must be one of {PRIORITIES}")
    if parent_id is not None and get_issue(conn, parent_id) is None:
        raise StoreError(f"Parent issue #{parent_id} does not exist")

    now = _now()
    cur = conn.execute(
        """INSERT INTO issues
           (title, description, status, priority, parent_id, branch, worktree,
            assignee, metadata, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            title,
            description or "",
            status,
            priority,
            parent_id,
            branch,
            worktree,
            assignee,
            json.dumps(metadata or {}),
            now,
            now,
        ),
    )
    issue_id = cur.lastrowid
    _log(conn, "issue", "created", issue_id)
    conn.commit()
    return get_issue(conn, issue_id)


def get_issue(conn: sqlite3.Connection, issue_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
    return _row_to_issue(row) if row else None


_UPDATABLE = {
    "title",
    "description",
    "status",
    "priority",
    "parent_id",
    "branch",
    "worktree",
    "assignee",
}


def update_issue(conn: sqlite3.Connection, issue_id: int, **fields: Any) -> dict:
    issue = get_issue(conn, issue_id)
    if issue is None:
        raise StoreError(f"Issue #{issue_id} does not exist")

    metadata_update = fields.pop("metadata", None)
    unknown = set(fields) - _UPDATABLE
    if unknown:
        raise StoreError(f"Cannot update unknown field(s): {sorted(unknown)}")

    if "status" in fields and fields["status"] not in STATUSES:
        raise StoreError(f"Invalid status {fields['status']!r}")
    if "priority" in fields and fields["priority"] not in PRIORITIES:
        raise StoreError(f"Invalid priority {fields['priority']!r}")
    if "parent_id" in fields and fields["parent_id"] is not None:
        _check_parent(conn, issue_id, fields["parent_id"])

    sets = []
    values: list[Any] = []
    for key, value in fields.items():
        sets.append(f"{key} = ?")
        values.append(value)

    if metadata_update is not None:
        merged = {**issue["metadata"], **metadata_update}
        sets.append("metadata = ?")
        values.append(json.dumps(merged))

    if not sets:
        return issue

    sets.append("updated_at = ?")
    values.append(_now())
    values.append(issue_id)
    conn.execute(f"UPDATE issues SET {', '.join(sets)} WHERE id = ?", values)
    _log(conn, "issue", "updated", issue_id)
    conn.commit()
    return get_issue(conn, issue_id)


def _check_parent(conn: sqlite3.Connection, issue_id: int, parent_id: int) -> None:
    if parent_id == issue_id:
        raise StoreError("An issue cannot be its own parent")
    if get_issue(conn, parent_id) is None:
        raise StoreError(f"Parent issue #{parent_id} does not exist")
    # Walk up the proposed parent chain to ensure we don't create a cycle.
    seen = set()
    cursor = parent_id
    while cursor is not None:
        if cursor == issue_id:
            raise StoreError("Setting this parent would create a hierarchy cycle")
        if cursor in seen:
            break
        seen.add(cursor)
        row = conn.execute(
            "SELECT parent_id FROM issues WHERE id = ?", (cursor,)
        ).fetchone()
        cursor = row["parent_id"] if row else None


def delete_issue(conn: sqlite3.Connection, issue_id: int) -> None:
    if get_issue(conn, issue_id) is None:
        raise StoreError(f"Issue #{issue_id} does not exist")
    conn.execute("DELETE FROM issues WHERE id = ?", (issue_id,))
    _log(conn, "issue", "deleted", issue_id)
    conn.commit()


def list_issues(
    conn: sqlite3.Connection,
    status: str | None = None,
    priority: str | None = None,
    parent_id: int | None = None,
) -> list[dict]:
    clauses = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if priority:
        clauses.append("priority = ?")
        params.append(priority)
    if parent_id is not None:
        clauses.append("parent_id = ?")
        params.append(parent_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM issues {where} "
        "ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 "
        "WHEN 'P2' THEN 2 ELSE 3 END, id",
        params,
    ).fetchall()
    return [_row_to_issue(r) for r in rows]


# --- Dependencies -----------------------------------------------------------


def add_dependency(conn: sqlite3.Connection, blocker_id: int, blocked_id: int) -> None:
    """Record that ``blocker_id`` must be completed before ``blocked_id``."""
    if blocker_id == blocked_id:
        raise StoreError("An issue cannot depend on itself")
    if get_issue(conn, blocker_id) is None:
        raise StoreError(f"Issue #{blocker_id} does not exist")
    if get_issue(conn, blocked_id) is None:
        raise StoreError(f"Issue #{blocked_id} does not exist")
    if _creates_cycle(conn, blocker_id, blocked_id):
        raise StoreError(
            f"Adding this dependency would create a cycle "
            f"(#{blocked_id} already blocks #{blocker_id}, directly or transitively)"
        )
    conn.execute(
        "INSERT OR IGNORE INTO dependencies (blocker_id, blocked_id) VALUES (?, ?)",
        (blocker_id, blocked_id),
    )
    _log(conn, "dependency", "created", f"{blocker_id}->{blocked_id}")
    conn.commit()


def remove_dependency(
    conn: sqlite3.Connection, blocker_id: int, blocked_id: int
) -> None:
    conn.execute(
        "DELETE FROM dependencies WHERE blocker_id = ? AND blocked_id = ?",
        (blocker_id, blocked_id),
    )
    _log(conn, "dependency", "deleted", f"{blocker_id}->{blocked_id}")
    conn.commit()


def _creates_cycle(conn: sqlite3.Connection, blocker_id: int, blocked_id: int) -> bool:
    """True if adding blocker->blocked would create a cycle.

    A cycle appears if ``blocked_id`` can already reach ``blocker_id`` by
    following blocker->blocked edges.
    """
    stack = [blocked_id]
    seen = set()
    while stack:
        node = stack.pop()
        if node == blocker_id:
            return True
        if node in seen:
            continue
        seen.add(node)
        rows = conn.execute(
            "SELECT blocked_id FROM dependencies WHERE blocker_id = ?", (node,)
        ).fetchall()
        stack.extend(r["blocked_id"] for r in rows)
    return False


def dependencies_of(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT blocker_id, blocked_id FROM dependencies"
    ).fetchall()
    return [dict(r) for r in rows]


def blockers_for(conn: sqlite3.Connection, issue_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT blocker_id FROM dependencies WHERE blocked_id = ?", (issue_id,)
    ).fetchall()
    return [r["blocker_id"] for r in rows]


def blocked_by_for(conn: sqlite3.Connection, issue_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT blocked_id FROM dependencies WHERE blocker_id = ?", (issue_id,)
    ).fetchall()
    return [r["blocked_id"] for r in rows]


def graph(conn: sqlite3.Connection) -> dict:
    """Return nodes and edges for the web dependency graph."""
    issues = list_issues(conn)
    deps = dependencies_of(conn)
    # An issue is "actionable" if it is open and has no incomplete blockers.
    status_by_id = {i["id"]: i["status"] for i in issues}
    incomplete_blockers: dict[int, int] = {}
    for edge in deps:
        if status_by_id.get(edge["blocker_id"]) in OPEN_STATUSES:
            incomplete_blockers[edge["blocked_id"]] = (
                incomplete_blockers.get(edge["blocked_id"], 0) + 1
            )
    comment_counts = {
        row["issue_id"]: row["n"]
        for row in conn.execute(
            "SELECT issue_id, COUNT(*) AS n FROM comments GROUP BY issue_id"
        ).fetchall()
    }
    for issue in issues:
        issue["blocked_count"] = incomplete_blockers.get(issue["id"], 0)
        issue["actionable"] = (
            issue["status"] in OPEN_STATUSES and issue["blocked_count"] == 0
        )
        issue["comment_count"] = comment_counts.get(issue["id"], 0)
    return {"issues": issues, "dependencies": deps}


# --- Comments ---------------------------------------------------------------


def add_comment(
    conn: sqlite3.Connection,
    issue_id: int,
    body: str,
    author: str = "agent",
) -> dict:
    body = (body or "").strip()
    if not body:
        raise StoreError("Comment body must not be empty")
    if get_issue(conn, issue_id) is None:
        raise StoreError(f"Issue #{issue_id} does not exist")
    cur = conn.execute(
        "INSERT INTO comments (issue_id, author, body, created_at) "
        "VALUES (?, ?, ?, ?)",
        (issue_id, author or "agent", body, _now()),
    )
    comment_id = cur.lastrowid
    _log(conn, "comment", "created", issue_id)
    conn.commit()
    return get_comment(conn, comment_id)


def get_comment(conn: sqlite3.Connection, comment_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM comments WHERE id = ?", (comment_id,)
    ).fetchone()
    return dict(row) if row else None


def list_comments(conn: sqlite3.Connection, issue_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM comments WHERE issue_id = ? ORDER BY id", (issue_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def delete_comment(conn: sqlite3.Connection, comment_id: int) -> None:
    comment = get_comment(conn, comment_id)
    if comment is None:
        raise StoreError(f"Comment #{comment_id} does not exist")
    conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    _log(conn, "comment", "deleted", comment["issue_id"])
    conn.commit()


# --- Knowledge base ---------------------------------------------------------


def kb_get(conn: sqlite3.Connection, key: str) -> dict | None:
    row = conn.execute("SELECT * FROM knowledge WHERE key = ?", (key,)).fetchone()
    return dict(row) if row else None


def kb_all(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM knowledge ORDER BY key").fetchall()
    return [dict(r) for r in rows]


def kb_propose(
    conn: sqlite3.Connection,
    key: str,
    value: str | None,
    operation: str = "set",
    author: str = "agent",
    note: str = "",
) -> dict:
    """Queue a change to the knowledge base for human approval.

    Nothing in ``knowledge`` changes until a human approves the proposal.
    """
    key = (key or "").strip()
    if not key:
        raise StoreError("Knowledge key must not be empty")
    if operation not in ("set", "delete"):
        raise StoreError("operation must be 'set' or 'delete'")
    if operation == "set" and value is None:
        raise StoreError("A 'set' proposal requires a value")

    existing = kb_get(conn, key)
    if operation == "delete" and existing is None:
        raise StoreError(f"Cannot propose deletion of unknown key {key!r}")

    now = _now()
    # A key may have only one live pending proposal: supersede any earlier ones
    # rather than stacking duplicates in the approval queue.
    stale = conn.execute(
        "SELECT id FROM knowledge_proposals WHERE key = ? AND status = 'pending'",
        (key,),
    ).fetchall()
    superseded = [row["id"] for row in stale]
    for old_id in superseded:
        conn.execute(
            "UPDATE knowledge_proposals SET status = 'superseded', resolved_at = ? "
            "WHERE id = ?",
            (now, old_id),
        )
        _log(conn, "proposal", "superseded", old_id)

    current_value = existing["value"] if existing else None
    cur = conn.execute(
        """INSERT INTO knowledge_proposals
           (key, operation, proposed_value, current_value, author, note,
            status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (key, operation, value, current_value, author, note, now),
    )
    proposal_id = cur.lastrowid
    _log(conn, "proposal", "created", proposal_id)
    conn.commit()
    result = get_proposal(conn, proposal_id)
    result["superseded"] = superseded
    return result


def get_proposal(conn: sqlite3.Connection, proposal_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM knowledge_proposals WHERE id = ?", (proposal_id,)
    ).fetchone()
    return dict(row) if row else None


def list_proposals(
    conn: sqlite3.Connection, status: str | None = "pending"
) -> list[dict]:
    if status:
        rows = conn.execute(
            "SELECT * FROM knowledge_proposals WHERE status = ? ORDER BY id DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM knowledge_proposals ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def approve_proposal(conn: sqlite3.Connection, proposal_id: int) -> dict:
    """Apply a pending proposal to the knowledge base. Human action only."""
    proposal = get_proposal(conn, proposal_id)
    if proposal is None:
        raise StoreError(f"Proposal #{proposal_id} does not exist")
    if proposal["status"] != "pending":
        raise StoreError(
            f"Proposal #{proposal_id} is already {proposal['status']}"
        )

    now = _now()
    if proposal["operation"] == "set":
        conn.execute(
            """INSERT INTO knowledge (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
               updated_at = excluded.updated_at""",
            (proposal["key"], proposal["proposed_value"], now),
        )
    else:  # delete
        conn.execute("DELETE FROM knowledge WHERE key = ?", (proposal["key"],))

    conn.execute(
        "UPDATE knowledge_proposals SET status = 'approved', resolved_at = ? "
        "WHERE id = ?",
        (now, proposal_id),
    )
    _log(conn, "knowledge", "approved", proposal["key"])
    _log(conn, "proposal", "resolved", proposal_id)
    conn.commit()
    return get_proposal(conn, proposal_id)


def withdraw_proposal(conn: sqlite3.Connection, proposal_id: int) -> dict:
    """Retract a pending proposal (the author's own undo; not a human decision)."""
    proposal = get_proposal(conn, proposal_id)
    if proposal is None:
        raise StoreError(f"Proposal #{proposal_id} does not exist")
    if proposal["status"] != "pending":
        raise StoreError(
            f"Proposal #{proposal_id} is already {proposal['status']}"
        )
    conn.execute(
        "UPDATE knowledge_proposals SET status = 'withdrawn', resolved_at = ? "
        "WHERE id = ?",
        (_now(), proposal_id),
    )
    _log(conn, "proposal", "resolved", proposal_id)
    conn.commit()
    return get_proposal(conn, proposal_id)


def reject_proposal(conn: sqlite3.Connection, proposal_id: int) -> dict:
    proposal = get_proposal(conn, proposal_id)
    if proposal is None:
        raise StoreError(f"Proposal #{proposal_id} does not exist")
    if proposal["status"] != "pending":
        raise StoreError(
            f"Proposal #{proposal_id} is already {proposal['status']}"
        )
    conn.execute(
        "UPDATE knowledge_proposals SET status = 'rejected', resolved_at = ? "
        "WHERE id = ?",
        (_now(), proposal_id),
    )
    _log(conn, "proposal", "resolved", proposal_id)
    conn.commit()
    return get_proposal(conn, proposal_id)


# --- Change feed ------------------------------------------------------------


def changes_since(conn: sqlite3.Connection, last_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM change_log WHERE id > ? ORDER BY id", (last_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def latest_change_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM change_log").fetchone()
    return int(row["m"])


def _issue_title(conn: sqlite3.Connection, ref: Any) -> str | None:
    try:
        row = conn.execute(
            "SELECT title FROM issues WHERE id = ?", (int(ref),)
        ).fetchone()
    except (TypeError, ValueError):
        return None
    return row["title"] if row else None


def _proposal_key(conn: sqlite3.Connection, ref: Any) -> str | None:
    try:
        row = conn.execute(
            "SELECT key FROM knowledge_proposals WHERE id = ?", (int(ref),)
        ).fetchone()
    except (TypeError, ValueError):
        return None
    return row["key"] if row else None


def _label(conn: sqlite3.Connection, c: dict) -> str:
    kind, action, ref = c["kind"], c["action"], c["ref"]
    if kind == "issue":
        title = _issue_title(conn, ref)
        suffix = f": {title}" if title else ""
        if action == "created":
            return f"New issue #{ref}{suffix}"
        if action == "updated":
            return f"Updated issue #{ref}{suffix}"
        if action == "deleted":
            return f"Deleted issue #{ref}"
    if kind == "comment":
        title = _issue_title(conn, ref)
        suffix = f": {title}" if title else ""
        if action == "created":
            return f"New comment on #{ref}{suffix}"
        if action == "deleted":
            return f"Comment removed on #{ref}{suffix}"
    if kind == "dependency":
        verb = "added" if action == "created" else "removed"
        return f"Dependency {verb} ({ref})"
    if kind == "knowledge":
        return f"Knowledge approved: {ref}"
    if kind == "proposal":
        key = _proposal_key(conn, ref)
        suffix = f": {key}" if key else ""
        if action == "created":
            return f"Knowledge change proposed{suffix}"
        if action == "superseded":
            return f"Proposal #{ref} superseded"
        if action == "resolved":
            return f"Proposal #{ref} resolved"
    return f"{kind} {action} {ref}"


# Change-feed entries that duplicate another, more descriptive entry for the same
# event, so the activity feed / notifications don't fire twice per action.
_ACTIVITY_NOISE = {("proposal", "resolved"), ("proposal", "superseded")}


def activity(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    """Recent change-feed entries, newest first, each with a human-readable text."""
    rows = conn.execute(
        "SELECT * FROM change_log ORDER BY id DESC LIMIT ?", (max(1, limit),)
    ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        if (d["kind"], d["action"]) in _ACTIVITY_NOISE:
            continue
        d["text"] = _label(conn, d)
        out.append(d)
    return out


def changes_since_ts(conn: sqlite3.Connection, ts: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM change_log WHERE ts > ? ORDER BY id", (ts,)
    ).fetchall()
    return [dict(r) for r in rows]


def changes_since_any(conn: sqlite3.Connection, since: str | int) -> list[dict]:
    """Return changes since a sentinel that is either a numeric token (change id)
    or an ISO-8601 timestamp string."""
    token = str(since).strip()
    if token.isdigit():
        return changes_since(conn, int(token))
    return changes_since_ts(conn, token)


# --- Export / import --------------------------------------------------------

EXPORT_FORMAT = "agent-issue-tracker-export"
EXPORT_VERSION = 1

# Issue columns carried by an export, in the order the raw insert expects.
_ISSUE_COLUMNS = (
    "id", "title", "description", "status", "priority", "parent_id",
    "branch", "worktree", "assignee", "metadata", "created_at", "updated_at",
)


def export_all(conn: sqlite3.Connection) -> dict:
    """Serialise the whole tracker (issues, deps, comments, KB) into a plain
    dict suitable for JSON. Original ids and timestamps are preserved so the
    document can be re-imported with full fidelity."""
    issues = [
        dict(r) for r in conn.execute(
            "SELECT id, title, description, status, priority, parent_id, branch, "
            "worktree, assignee, metadata, created_at, updated_at "
            "FROM issues ORDER BY id"
        ).fetchall()
    ]
    for it in issues:
        try:
            it["metadata"] = json.loads(it.get("metadata") or "{}")
        except (json.JSONDecodeError, TypeError):
            it["metadata"] = {}
    deps = [
        dict(r) for r in conn.execute(
            "SELECT blocker_id, blocked_id FROM dependencies "
            "ORDER BY blocker_id, blocked_id"
        ).fetchall()
    ]
    comments = [
        dict(r) for r in conn.execute(
            "SELECT id, issue_id, author, body, created_at FROM comments ORDER BY id"
        ).fetchall()
    ]
    knowledge = [
        dict(r) for r in conn.execute(
            "SELECT key, value, updated_at FROM knowledge ORDER BY key"
        ).fetchall()
    ]
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exported_at": _now(),
        "counts": {
            "issues": len(issues),
            "dependencies": len(deps),
            "comments": len(comments),
            "knowledge": len(knowledge),
        },
        "issues": issues,
        "dependencies": deps,
        "comments": comments,
        "knowledge": knowledge,
    }


def _order_parents_first(issues: list[dict]) -> list[dict]:
    """Return issues ordered so every parent precedes its children (needed to
    satisfy the parent_id foreign key on insert). Issues whose parent is not in
    the set are treated as roots."""
    by_id = {it["id"]: it for it in issues}
    ordered: list[dict] = []
    placed: set = set()

    def place(it: dict, stack: set) -> None:
        iid = it["id"]
        if iid in placed:
            return
        if iid in stack:  # defensive: parent cycle should never happen
            return
        parent = it.get("parent_id")
        if parent is not None and parent in by_id and parent not in placed:
            place(by_id[parent], stack | {iid})
        ordered.append(it)
        placed.add(iid)

    for it in issues:
        place(it, set())
    return ordered


def import_bundle(conn: sqlite3.Connection, bundle: dict) -> dict:
    """Insert an exported bundle into this database, preserving timestamps.

    Original ids are kept verbatim when none of them collide with existing
    issues (the clean-migration case); otherwise every issue is reinserted
    under a fresh id and parent/dependency/comment references are remapped.
    Returns a stats dict describing what happened."""
    fmt = bundle.get("format")
    if fmt != EXPORT_FORMAT:
        raise StoreError(
            f"Not an issue-tracker export (format={fmt!r}); expected {EXPORT_FORMAT!r}"
        )
    if bundle.get("version") != EXPORT_VERSION:
        raise StoreError(
            f"Unsupported export version {bundle.get('version')!r}; "
            f"this build reads version {EXPORT_VERSION}"
        )

    issues = list(bundle.get("issues") or [])
    for it in issues:
        if not (it.get("title") or "").strip():
            raise StoreError(f"Issue #{it.get('id')} has an empty title")
        if it.get("status") not in STATUSES:
            raise StoreError(f"Issue #{it.get('id')} has invalid status {it.get('status')!r}")
        if it.get("priority") not in PRIORITIES:
            raise StoreError(
                f"Issue #{it.get('id')} has invalid priority {it.get('priority')!r}"
            )

    existing = {r["id"] for r in conn.execute("SELECT id FROM issues").fetchall()}
    incoming = {it["id"] for it in issues}
    keep_ids = existing.isdisjoint(incoming)

    id_map: dict[int, int] = {}
    now = _now()
    for it in _order_parents_first(issues):
        old_id = it["id"]
        parent = it.get("parent_id")
        new_parent = id_map.get(parent) if parent is not None else None
        metadata = it.get("metadata")
        if isinstance(metadata, (dict, list)):
            metadata = json.dumps(metadata)
        elif metadata is None:
            metadata = "{}"
        values = (
            it.get("description") or "",
            it["status"],
            it["priority"],
            new_parent,
            it.get("branch"),
            it.get("worktree"),
            it.get("assignee"),
            metadata,
            it.get("created_at") or now,
            it.get("updated_at") or it.get("created_at") or now,
        )
        if keep_ids:
            cur = conn.execute(
                "INSERT INTO issues (id, title, description, status, priority, "
                "parent_id, branch, worktree, assignee, metadata, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (old_id, it["title"], *values),
            )
        else:
            cur = conn.execute(
                "INSERT INTO issues (title, description, status, priority, "
                "parent_id, branch, worktree, assignee, metadata, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (it["title"], *values),
            )
        id_map[old_id] = old_id if keep_ids else cur.lastrowid

    dep_count = 0
    for dep in bundle.get("dependencies") or []:
        b, d = id_map.get(dep.get("blocker_id")), id_map.get(dep.get("blocked_id"))
        if b is None or d is None:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO dependencies (blocker_id, blocked_id) VALUES (?, ?)",
            (b, d),
        )
        dep_count += 1

    comment_count = 0
    for c in bundle.get("comments") or []:
        target = id_map.get(c.get("issue_id"))
        if target is None or not (c.get("body") or "").strip():
            continue
        conn.execute(
            "INSERT INTO comments (issue_id, author, body, created_at) "
            "VALUES (?, ?, ?, ?)",
            (target, c.get("author") or "agent", c["body"], c.get("created_at") or now),
        )
        comment_count += 1

    kb_count = 0
    for k in bundle.get("knowledge") or []:
        key = (k.get("key") or "").strip()
        if not key:
            continue
        conn.execute(
            "INSERT INTO knowledge (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at",
            (key, k.get("value") or "", k.get("updated_at") or now),
        )
        kb_count += 1

    _log(conn, "import", "completed", len(id_map))
    conn.commit()
    return {
        "id_mode": "preserved" if keep_ids else "remapped",
        "issues": len(id_map),
        "dependencies": dep_count,
        "comments": comment_count,
        "knowledge": kb_count,
        "id_map": id_map,
    }
