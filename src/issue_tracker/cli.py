"""Command-line interface for the agent issue tracker.

Designed to be the primary interface for coding agents. Commands are terse,
output is human-readable by default and JSON-friendly with ``--json``.
"""

from __future__ import annotations

import json as jsonlib
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from . import db, store

app = typer.Typer(
    help="Hierarchical issue tracker + human-gated knowledge base for agents.",
    no_args_is_help=True,
    add_completion=False,
)
dep_app = typer.Typer(help="Manage dependencies between issues.", no_args_is_help=True)
kb_app = typer.Typer(help="Knowledge base (human-approved key/value store).", no_args_is_help=True)
app.add_typer(dep_app, name="dep")
app.add_typer(kb_app, name="kb")

console = Console()
err = Console(stderr=True)

STATUS_STYLE = {
    "open": "white",
    "in_progress": "yellow",
    "blocked": "red",
    "done": "green",
    "cancelled": "dim strike",
}
PRIORITY_STYLE = {"P0": "bold red", "P1": "red", "P2": "yellow", "P3": "dim"}


def _conn():
    return db.connect()


def _fail(msg: str) -> None:
    err.print(f"[bold red]error:[/] {msg}")
    raise typer.Exit(code=1)


def _emit(data, as_json: bool) -> None:
    if as_json:
        console.print_json(jsonlib.dumps(data, default=str))


# --- Issue commands ---------------------------------------------------------


@app.command()
def add(
    title: str = typer.Argument(..., help="Issue title"),
    description: str = typer.Option("", "--description", "-d"),
    priority: str = typer.Option("P2", "--priority", "-p", help="P0|P1|P2|P3"),
    status: str = typer.Option("open", "--status", "-s"),
    parent: Optional[int] = typer.Option(None, "--parent", help="Parent issue id"),
    branch: Optional[str] = typer.Option(None, "--branch"),
    worktree: Optional[str] = typer.Option(None, "--worktree"),
    assignee: Optional[str] = typer.Option(None, "--assignee", "-a"),
    depends_on: list[int] = typer.Option(
        None, "--depends-on", help="Issue id this new issue is blocked by (repeatable)"
    ),
    json_out: bool = typer.Option(False, "--json"),
):
    """Create a new issue."""
    conn = _conn()
    try:
        issue = store.create_issue(
            conn,
            title=title,
            description=description,
            priority=priority,
            status=status,
            parent_id=parent,
            branch=branch,
            worktree=worktree,
            assignee=assignee,
        )
        for blocker in depends_on or []:
            store.add_dependency(conn, blocker_id=blocker, blocked_id=issue["id"])
    except store.StoreError as exc:
        _fail(str(exc))
    finally:
        conn.close()
    if json_out:
        _emit(issue, True)
    else:
        console.print(f"Created issue [bold]#{issue['id']}[/]: {issue['title']}")


@app.command(name="list")
def list_cmd(
    status: Optional[str] = typer.Option(None, "--status", "-s"),
    priority: Optional[str] = typer.Option(None, "--priority", "-p"),
    json_out: bool = typer.Option(False, "--json"),
):
    """List issues (most important first)."""
    conn = _conn()
    try:
        issues = store.list_issues(conn, status=status, priority=priority)
    finally:
        conn.close()
    if json_out:
        _emit(issues, True)
        return
    _print_issue_table(issues)


@app.command()
def show(
    issue_id: int = typer.Argument(...),
    json_out: bool = typer.Option(False, "--json"),
):
    """Show a single issue with its relationships."""
    conn = _conn()
    try:
        issue = store.get_issue(conn, issue_id)
        if issue is None:
            _fail(f"Issue #{issue_id} not found")
        blockers = store.blockers_for(conn, issue_id)
        blocks = store.blocked_by_for(conn, issue_id)
        children = [c["id"] for c in store.list_issues(conn, parent_id=issue_id)]
    finally:
        conn.close()
    if json_out:
        _emit({**issue, "blockers": blockers, "blocks": blocks, "children": children}, True)
        return
    console.print(f"[bold]#{issue['id']}[/] {issue['title']}")
    _kv("status", issue["status"], STATUS_STYLE.get(issue["status"], "white"))
    _kv("priority", issue["priority"], PRIORITY_STYLE.get(issue["priority"], "white"))
    if issue["parent_id"]:
        _kv("parent", f"#{issue['parent_id']}", "white")
    if issue["assignee"]:
        _kv("assignee", issue["assignee"], "white")
    if issue["branch"]:
        _kv("branch", issue["branch"], "cyan")
    if issue["worktree"]:
        _kv("worktree", issue["worktree"], "cyan")
    if blockers:
        _kv("blocked by", ", ".join(f"#{b}" for b in blockers), "red")
    if blocks:
        _kv("blocks", ", ".join(f"#{b}" for b in blocks), "yellow")
    if children:
        _kv("children", ", ".join(f"#{c}" for c in children), "white")
    if issue["metadata"]:
        _kv("metadata", jsonlib.dumps(issue["metadata"]), "dim")
    if issue["description"]:
        console.print()
        console.print(issue["description"])


@app.command()
def update(
    issue_id: int = typer.Argument(...),
    title: Optional[str] = typer.Option(None, "--title", "-t"),
    description: Optional[str] = typer.Option(None, "--description", "-d"),
    status: Optional[str] = typer.Option(None, "--status", "-s"),
    priority: Optional[str] = typer.Option(None, "--priority", "-p"),
    parent: Optional[int] = typer.Option(None, "--parent"),
    branch: Optional[str] = typer.Option(None, "--branch"),
    worktree: Optional[str] = typer.Option(None, "--worktree"),
    assignee: Optional[str] = typer.Option(None, "--assignee", "-a"),
    meta: Optional[str] = typer.Option(
        None, "--meta", help='JSON object merged into metadata, e.g. \'{"pr": 42}\''
    ),
    json_out: bool = typer.Option(False, "--json"),
):
    """Update fields on an issue."""
    fields = {}
    for key, value in dict(
        title=title,
        description=description,
        status=status,
        priority=priority,
        parent_id=parent,
        branch=branch,
        worktree=worktree,
        assignee=assignee,
    ).items():
        if value is not None:
            fields[key] = value
    if meta is not None:
        try:
            fields["metadata"] = jsonlib.loads(meta)
        except jsonlib.JSONDecodeError as exc:
            _fail(f"--meta must be valid JSON: {exc}")
    if not fields:
        _fail("Nothing to update; pass at least one field")
    conn = _conn()
    try:
        issue = store.update_issue(conn, issue_id, **fields)
    except store.StoreError as exc:
        _fail(str(exc))
    finally:
        conn.close()
    if json_out:
        _emit(issue, True)
    else:
        console.print(f"Updated issue [bold]#{issue['id']}[/]")


@app.command()
def start(issue_id: int = typer.Argument(...)):
    """Shortcut: mark an issue as in_progress."""
    _quick_status(issue_id, "in_progress")


@app.command()
def done(issue_id: int = typer.Argument(...)):
    """Shortcut: mark an issue as done."""
    _quick_status(issue_id, "done")


@app.command()
def block(issue_id: int = typer.Argument(...)):
    """Shortcut: mark an issue as blocked."""
    _quick_status(issue_id, "blocked")


def _quick_status(issue_id: int, status: str) -> None:
    conn = _conn()
    try:
        store.update_issue(conn, issue_id, status=status)
    except store.StoreError as exc:
        _fail(str(exc))
    finally:
        conn.close()
    console.print(f"Issue [bold]#{issue_id}[/] -> [italic]{status}[/]")


@app.command()
def rm(
    issue_id: int = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete an issue (children become top-level, dependencies removed)."""
    if not yes:
        typer.confirm(f"Delete issue #{issue_id}?", abort=True)
    conn = _conn()
    try:
        store.delete_issue(conn, issue_id)
    except store.StoreError as exc:
        _fail(str(exc))
    finally:
        conn.close()
    console.print(f"Deleted issue #{issue_id}")


@app.command()
def tree(json_out: bool = typer.Option(False, "--json")):
    """Show issues as a hierarchy tree."""
    conn = _conn()
    try:
        issues = store.list_issues(conn)
    finally:
        conn.close()
    if json_out:
        _emit(issues, True)
        return
    by_parent: dict = {}
    for issue in issues:
        by_parent.setdefault(issue["parent_id"], []).append(issue)

    root = Tree("[bold]Issues[/]")

    def add_children(node, parent_id):
        for issue in by_parent.get(parent_id, []):
            label = _issue_label(issue)
            child = node.add(label)
            add_children(child, issue["id"])

    add_children(root, None)
    console.print(root)


@app.command(name="next")
def next_cmd(json_out: bool = typer.Option(False, "--json")):
    """Show actionable issues: open, unblocked, most important first."""
    conn = _conn()
    try:
        data = store.graph(conn)
    finally:
        conn.close()
    actionable = [i for i in data["issues"] if i.get("actionable")]
    if json_out:
        _emit(actionable, True)
        return
    if not actionable:
        console.print("[dim]No actionable issues. Everything is blocked or done.[/]")
        return
    _print_issue_table(actionable)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
):
    """Run the web interface (API + dependency graph + approval UI)."""
    try:
        import uvicorn
    except ImportError:
        _fail("uvicorn is not installed; run `pip install -e .`")
    path = db.db_path()
    console.print(f"Database: [cyan]{path}[/]")
    console.print(f"Web UI:   [green]http://{host}:{port}[/]")
    uvicorn.run("issue_tracker.app:app", host=host, port=port, reload=reload)


# --- Dependency commands ----------------------------------------------------


@dep_app.command("add")
def dep_add(
    blocker: int = typer.Argument(..., help="Issue that must finish first"),
    blocked: int = typer.Argument(..., help="Issue that is waiting"),
):
    """Record that BLOCKER must be completed before BLOCKED."""
    conn = _conn()
    try:
        store.add_dependency(conn, blocker_id=blocker, blocked_id=blocked)
    except store.StoreError as exc:
        _fail(str(exc))
    finally:
        conn.close()
    console.print(f"#{blocker} now blocks #{blocked}")


@dep_app.command("rm")
def dep_rm(
    blocker: int = typer.Argument(...),
    blocked: int = typer.Argument(...),
):
    """Remove a dependency edge."""
    conn = _conn()
    try:
        store.remove_dependency(conn, blocker_id=blocker, blocked_id=blocked)
    finally:
        conn.close()
    console.print(f"Removed #{blocker} -> #{blocked}")


# --- Knowledge base commands ------------------------------------------------


@kb_app.command("get")
def kb_get(key: str = typer.Argument(...), json_out: bool = typer.Option(False, "--json")):
    """Read an approved knowledge value."""
    conn = _conn()
    try:
        row = store.kb_get(conn, key)
    finally:
        conn.close()
    if row is None:
        _fail(f"No approved value for key {key!r}")
    if json_out:
        _emit(row, True)
    else:
        console.print(row["value"])


@kb_app.command("list")
def kb_list(json_out: bool = typer.Option(False, "--json")):
    """List all approved knowledge entries."""
    conn = _conn()
    try:
        rows = store.kb_all(conn)
    finally:
        conn.close()
    if json_out:
        _emit(rows, True)
        return
    if not rows:
        console.print("[dim]Knowledge base is empty.[/]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("key", style="cyan")
    table.add_column("value")
    for row in rows:
        table.add_row(row["key"], row["value"])
    console.print(table)


@kb_app.command("propose")
def kb_propose(
    key: str = typer.Argument(...),
    value: Optional[str] = typer.Argument(
        None, help="Value; omit and use --file/-f to read from a file or stdin"
    ),
    file: Optional[str] = typer.Option(
        None, "--file", "-f", help="Read the value from this file, or '-' for stdin"
    ),
    note: str = typer.Option("", "--note", "-n", help="Why this change?"),
    author: str = typer.Option("agent", "--author"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Propose setting KEY=VALUE. Requires human approval in the web UI.

    Values may be long and use markdown. For multi-line values, pass --file
    (or '-f -' to read from stdin) instead of a shell-quoted argument.
    """
    if file is not None:
        if value is not None:
            _fail("Pass either VALUE or --file, not both")
        try:
            if file == "-":
                value = sys.stdin.read()
            else:
                value = Path(file).read_text()
        except OSError as exc:
            _fail(f"Could not read value from {file!r}: {exc}")
    if value is None:
        _fail("Provide a VALUE argument or --file")
    conn = _conn()
    try:
        proposal = store.kb_propose(
            conn, key=key, value=value, operation="set", author=author, note=note
        )
    except store.StoreError as exc:
        _fail(str(exc))
    finally:
        conn.close()
    if json_out:
        _emit(proposal, True)
    else:
        console.print(
            f"Proposed [bold]#{proposal['id']}[/]: set [cyan]{key}[/] "
            f"([yellow]pending human approval[/])"
        )


@kb_app.command("propose-delete")
def kb_propose_delete(
    key: str = typer.Argument(...),
    note: str = typer.Option("", "--note", "-n"),
    author: str = typer.Option("agent", "--author"),
):
    """Propose deleting KEY. Requires human approval in the web UI."""
    conn = _conn()
    try:
        proposal = store.kb_propose(
            conn, key=key, value=None, operation="delete", author=author, note=note
        )
    except store.StoreError as exc:
        _fail(str(exc))
    finally:
        conn.close()
    console.print(
        f"Proposed [bold]#{proposal['id']}[/]: delete [cyan]{key}[/] "
        f"([yellow]pending human approval[/])"
    )


@kb_app.command("pending")
def kb_pending(json_out: bool = typer.Option(False, "--json")):
    """List knowledge changes awaiting human approval."""
    conn = _conn()
    try:
        rows = store.list_proposals(conn, status="pending")
    finally:
        conn.close()
    if json_out:
        _emit(rows, True)
        return
    if not rows:
        console.print("[dim]No pending proposals.[/]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="bold")
    table.add_column("op")
    table.add_column("key", style="cyan")
    table.add_column("current")
    table.add_column("proposed")
    table.add_column("note", style="dim")
    for row in rows:
        table.add_row(
            str(row["id"]),
            row["operation"],
            row["key"],
            row["current_value"] or "",
            row["proposed_value"] or "",
            row["note"] or "",
        )
    console.print(table)


@kb_app.command("approve")
def kb_approve(proposal_id: int = typer.Argument(...)):
    """Approve a pending proposal (human action)."""
    conn = _conn()
    try:
        store.approve_proposal(conn, proposal_id)
    except store.StoreError as exc:
        _fail(str(exc))
    finally:
        conn.close()
    console.print(f"Approved proposal #{proposal_id}")


@kb_app.command("reject")
def kb_reject(proposal_id: int = typer.Argument(...)):
    """Reject a pending proposal (human action)."""
    conn = _conn()
    try:
        store.reject_proposal(conn, proposal_id)
    except store.StoreError as exc:
        _fail(str(exc))
    finally:
        conn.close()
    console.print(f"Rejected proposal #{proposal_id}")


# --- Rendering helpers ------------------------------------------------------


def _kv(label: str, value: str, style: str) -> None:
    console.print(f"  [dim]{label:>10}[/] [{style}]{value}[/]")


def _issue_label(issue: dict) -> str:
    pstyle = PRIORITY_STYLE.get(issue["priority"], "white")
    sstyle = STATUS_STYLE.get(issue["status"], "white")
    return (
        f"[{pstyle}]{issue['priority']}[/] "
        f"[bold]#{issue['id']}[/] {issue['title']} "
        f"[{sstyle}]({issue['status']})[/]"
    )


def _print_issue_table(issues: list[dict]) -> None:
    if not issues:
        console.print("[dim]No issues.[/]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", justify="right", style="bold")
    table.add_column("pri")
    table.add_column("status")
    table.add_column("title")
    table.add_column("assignee", style="dim")
    for issue in issues:
        table.add_row(
            str(issue["id"]),
            f"[{PRIORITY_STYLE.get(issue['priority'], 'white')}]{issue['priority']}[/]",
            f"[{STATUS_STYLE.get(issue['status'], 'white')}]{issue['status']}[/]",
            issue["title"],
            issue["assignee"] or "",
        )
    console.print(table)


if __name__ == "__main__":
    app()
