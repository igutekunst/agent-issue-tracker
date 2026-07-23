"""Command-line interface for the agent issue tracker.

Designed to be the primary interface for coding agents. Commands are terse,
output is human-readable by default and JSON-friendly with ``--json``.

The CLI operates on the local SQLite database by default, or against a remote
server when one is configured (``issue login`` / ``ISSUE_TRACKER_SERVER``).
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

from . import FEATURES, __version__, backends, config, db, store

app = typer.Typer(
    help="Hierarchical issue tracker + human-gated knowledge base for agents.",
    no_args_is_help=True,
    add_completion=False,
)
dep_app = typer.Typer(help="Manage dependencies between issues.", no_args_is_help=True)
kb_app = typer.Typer(help="Knowledge base (human-approved key/value store).", no_args_is_help=True)
comment_app = typer.Typer(help="Add and read notes/comments on issues.", no_args_is_help=True)
token_app = typer.Typer(help="Manage API tokens for CLI/agents.", no_args_is_help=True)
app.add_typer(dep_app, name="dep")
app.add_typer(kb_app, name="kb")
app.add_typer(comment_app, name="comment")
app.add_typer(token_app, name="token")

console = Console()
err = Console(stderr=True)


def _version_callback(value: bool):
    if value:
        console.print(f"agent-issue-tracker {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    actor: Optional[str] = typer.Option(
        None,
        "--actor",
        help="Attribute changes to this name in the activity feed, local mode "
        "(defaults to ISSUE_TRACKER_ACTOR; remote mode uses the token's name).",
    ),
):
    """Hierarchical issue tracker + human-gated knowledge base for agents."""
    if actor:
        store.set_actor(actor)


STATUS_STYLE = {
    "open": "white",
    "in_progress": "yellow",
    "blocked": "red",
    "done": "green",
    "cancelled": "dim strike",
}
PRIORITY_STYLE = {"P0": "bold red", "P1": "red", "P2": "yellow", "P3": "dim"}


def _backend():
    return backends.get_backend()


def _fail(msg: str) -> None:
    err.print(f"[bold red]error:[/] {msg}")
    raise typer.Exit(code=1)


def _emit(data, as_json: bool) -> None:
    if as_json:
        console.print_json(jsonlib.dumps(data, default=str))


def _value_or_file(value: Optional[str], file: Optional[str], what: str = "VALUE") -> str:
    """Resolve a body from a positional arg, a --file path, or '-' for stdin."""
    if file is not None:
        if value is not None:
            _fail(f"Pass either {what} or --file, not both")
        try:
            return sys.stdin.read() if file == "-" else Path(file).read_text()
        except OSError as exc:
            _fail(f"Could not read {what.lower()} from {file!r}: {exc}")
    if value is None:
        _fail(f"Provide a {what} argument or --file")
    return value


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
    be = _backend()
    try:
        issue = be.create_issue(
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
            be.add_dependency(blocker, issue["id"])
    except store.StoreError as exc:
        _fail(str(exc))
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
    be = _backend()
    try:
        issues = be.list_issues(status=status, priority=priority)
    except store.StoreError as exc:
        _fail(str(exc))
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
    be = _backend()
    try:
        issue = be.get_issue(issue_id)
    except store.StoreError as exc:
        _fail(str(exc))
    blockers = issue.get("blockers", [])
    blocks = issue.get("blocks", [])
    children = issue.get("children", [])
    comments = issue.get("comments", [])
    if json_out:
        _emit(issue, True)
        return
    console.print(f"[bold]#{issue['id']}[/] {issue['title']}")
    _kv("status", issue["status"], STATUS_STYLE.get(issue["status"], "white"))
    _kv("priority", issue["priority"], PRIORITY_STYLE.get(issue["priority"], "white"))
    if issue.get("parent_id"):
        _kv("parent", f"#{issue['parent_id']}", "white")
    if issue.get("assignee"):
        _kv("assignee", issue["assignee"], "white")
    if issue.get("branch"):
        _kv("branch", issue["branch"], "cyan")
    if issue.get("worktree"):
        _kv("worktree", issue["worktree"], "cyan")
    if blockers:
        _kv("blocked by", ", ".join(f"#{b}" for b in blockers), "red")
    if blocks:
        _kv("blocks", ", ".join(f"#{b}" for b in blocks), "yellow")
    if children:
        _kv("children", ", ".join(f"#{c}" for c in children), "white")
    if issue.get("metadata"):
        _kv("metadata", jsonlib.dumps(issue["metadata"]), "dim")
    if issue.get("description"):
        console.print()
        console.print(issue["description"])
    if comments:
        console.print()
        console.print(f"[dim]── {len(comments)} comment(s) ──[/]")
        _print_comments(comments)


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
    be = _backend()
    try:
        issue = be.update_issue(issue_id, **fields)
    except store.StoreError as exc:
        _fail(str(exc))
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
    be = _backend()
    try:
        be.update_issue(issue_id, status=status)
    except store.StoreError as exc:
        _fail(str(exc))
    console.print(f"Issue [bold]#{issue_id}[/] -> [italic]{status}[/]")


@app.command()
def rm(
    issue_id: int = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete an issue (children become top-level, dependencies removed)."""
    if not yes:
        typer.confirm(f"Delete issue #{issue_id}?", abort=True)
    be = _backend()
    try:
        be.delete_issue(issue_id)
    except store.StoreError as exc:
        _fail(str(exc))
    console.print(f"Deleted issue #{issue_id}")


@app.command()
def tree(json_out: bool = typer.Option(False, "--json")):
    """Show issues as a hierarchy tree."""
    be = _backend()
    try:
        issues = be.list_issues()
    except store.StoreError as exc:
        _fail(str(exc))
    if json_out:
        _emit(issues, True)
        return
    by_parent: dict = {}
    for issue in issues:
        by_parent.setdefault(issue["parent_id"], []).append(issue)

    root = Tree("[bold]Issues[/]")

    def add_children(node, parent_id):
        for issue in by_parent.get(parent_id, []):
            child = node.add(_issue_label(issue))
            add_children(child, issue["id"])

    add_children(root, None)
    console.print(root)


@app.command(name="next")
def next_cmd(json_out: bool = typer.Option(False, "--json")):
    """Show actionable issues: open, unblocked, most important first."""
    be = _backend()
    try:
        data = be.graph()
    except store.StoreError as exc:
        _fail(str(exc))
    actionable = [i for i in data["issues"] if i.get("actionable")]
    if json_out:
        _emit(actionable, True)
        return
    if not actionable:
        console.print("[dim]No actionable issues. Everything is blocked or done.[/]")
        return
    _print_issue_table(actionable)


@app.command()
def activity(
    limit: int = typer.Option(20, "--limit", "-n"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Show a feed of recent changes (who changed what)."""
    be = _backend()
    try:
        rows = be.activity(limit=limit)
    except store.StoreError as exc:
        _fail(str(exc))
    if json_out:
        _emit(rows, True)
        return
    if not rows:
        console.print("[dim]No activity yet.[/]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("when", style="dim")
    table.add_column("actor", style="cyan")
    table.add_column("change")
    for r in rows:
        table.add_row(r["ts"].replace("T", " "), r.get("actor") or "—", r["text"])
    console.print(table)


@app.command()
def changes(
    since: Optional[str] = typer.Option(
        None, "--since", "-s", help="Token (change id) or ISO timestamp to compare against"
    ),
    json_out: bool = typer.Option(False, "--json"),
):
    """Update sentinel: has anything changed since a token/timestamp?"""
    be = _backend()
    try:
        result = be.changes(since=since)
    except store.StoreError as exc:
        _fail(str(exc))
    if json_out:
        _emit(result, True)
        return
    token = result["token"]
    rows = result["changes"]
    if since is None:
        console.print(f"token: [bold]{token}[/]")
        return
    if not rows:
        console.print(f"No changes since {since}. token: [bold]{token}[/]")
        return
    console.print(
        f"[bold]{len(rows)}[/] change(s) since {since}; new token: [bold]{token}[/]"
    )
    table = Table(show_header=True, header_style="bold")
    table.add_column("id", justify="right")
    table.add_column("kind")
    table.add_column("action")
    table.add_column("ref")
    table.add_column("ts", style="dim")
    for r in rows:
        table.add_row(str(r["id"]), r["kind"], r["action"], str(r["ref"]), r["ts"])
    console.print(table)


# --- Remote / auth commands -------------------------------------------------


@app.command()
def login(
    server: str = typer.Option(..., "--server", help="Base URL, e.g. https://issues.example.com"),
    token: str = typer.Option(..., "--token", "-t", help="API token (see `issue token create`)"),
):
    """Point the CLI at a remote tracker and save credentials."""
    server = server.rstrip("/")
    be = backends.RemoteBackend(server, token)
    try:
        who = be.whoami()
    except store.StoreError as exc:
        _fail(f"could not authenticate to {server}: {exc}")
    config.save_config({"server": server, "token": token})
    principal = who.get("principal") or "(server has auth disabled)"
    console.print(f"Logged in to [green]{server}[/] as [cyan]{principal}[/]")
    console.print(f"[dim]Config saved to {config.config_path()}[/]")


@app.command()
def logout():
    """Forget the remote server; revert to the local database."""
    config.clear_config()
    console.print("Logged out. The CLI now uses the local database.")


@app.command()
def whoami():
    """Show whether the CLI is local or remote, and the current identity."""
    server = config.resolve_server()
    if not server:
        console.print(f"[bold]local[/] · db: [cyan]{db.db_path()}[/]")
        return
    be = _backend()
    try:
        who = be.whoami()
    except store.StoreError as exc:
        _fail(str(exc))
    console.print(f"[bold]remote[/] · server: [green]{server}[/]")
    console.print(f"  identity: [cyan]{who.get('principal') or '—'}[/]")
    console.print(f"  admin: {who.get('is_admin')}")


@app.command()
def version(json_out: bool = typer.Option(False, "--json")):
    """Show version, feature flags, and where the CLI is pointed."""
    server = config.resolve_server()
    info = {
        "version": __version__,
        "features": FEATURES,
        "mode": "remote" if server else "local",
        "server": server,
        "db": None if server else str(db.db_path()),
    }
    if json_out:
        _emit(info, True)
        return
    console.print(f"agent-issue-tracker [bold]{__version__}[/]")
    if server:
        console.print(f"  [dim]mode:[/] remote · [green]{server}[/]")
    else:
        console.print(f"  [dim]mode:[/] local · db: [cyan]{db.db_path()}[/]")
    console.print(f"  [dim]features:[/] {', '.join(FEATURES)}")


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
    from . import auth

    console.print(f"Database: [cyan]{db.db_path()}[/]")
    console.print(f"Web UI:   [green]http://{host}:{port}[/]")
    console.print(f"Auth:     {'[green]enabled[/]' if auth.auth_enabled() else '[yellow]disabled (local/open)[/]'}")
    uvicorn.run("issue_tracker.app:app", host=host, port=port, reload=reload)


# --- Dependency commands ----------------------------------------------------


@dep_app.command("add")
def dep_add(
    blocker: int = typer.Argument(..., help="Issue that must finish first"),
    blocked: int = typer.Argument(..., help="Issue that is waiting"),
):
    """Record that BLOCKER must be completed before BLOCKED."""
    be = _backend()
    try:
        be.add_dependency(blocker, blocked)
    except store.StoreError as exc:
        _fail(str(exc))
    console.print(f"#{blocker} now blocks #{blocked}")


@dep_app.command("rm")
def dep_rm(blocker: int = typer.Argument(...), blocked: int = typer.Argument(...)):
    """Remove a dependency edge."""
    be = _backend()
    try:
        be.remove_dependency(blocker, blocked)
    except store.StoreError as exc:
        _fail(str(exc))
    console.print(f"Removed #{blocker} -> #{blocked}")


# --- Comment commands -------------------------------------------------------


@comment_app.command("add")
def comment_add(
    issue_id: int = typer.Argument(...),
    body: Optional[str] = typer.Argument(
        None, help="Comment text; omit and use --file/-f to read a file or stdin"
    ),
    file: Optional[str] = typer.Option(
        None, "--file", "-f", help="Read the comment from this file, or '-' for stdin"
    ),
    author: str = typer.Option("agent", "--author", "-a"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Add a note/comment to an issue. Body may be long and use markdown."""
    body = _value_or_file(body, file, "BODY")
    be = _backend()
    try:
        comment = be.add_comment(issue_id, body=body, author=author)
    except store.StoreError as exc:
        _fail(str(exc))
    if json_out:
        _emit(comment, True)
    else:
        console.print(f"Added comment [bold]#{comment['id']}[/] to issue #{issue_id}")


@comment_app.command("list")
def comment_list(
    issue_id: int = typer.Argument(...),
    json_out: bool = typer.Option(False, "--json"),
):
    """List the comments on an issue."""
    be = _backend()
    try:
        comments = be.list_comments(issue_id)
    except store.StoreError as exc:
        _fail(str(exc))
    if json_out:
        _emit(comments, True)
        return
    _print_comments(comments)


@comment_app.command("rm")
def comment_rm(
    comment_id: int = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y"),
):
    """Delete a comment by its id."""
    if not yes:
        typer.confirm(f"Delete comment #{comment_id}?", abort=True)
    be = _backend()
    try:
        be.delete_comment(comment_id)
    except store.StoreError as exc:
        _fail(str(exc))
    console.print(f"Deleted comment #{comment_id}")


# --- Knowledge base commands ------------------------------------------------


@kb_app.command("get")
def kb_get(key: str = typer.Argument(...), json_out: bool = typer.Option(False, "--json")):
    """Read an approved knowledge value."""
    be = _backend()
    try:
        row = be.kb_get(key)
    except store.StoreError as exc:
        _fail(str(exc))
    if row is None:
        _fail(f"No approved value for key {key!r}")
    if json_out:
        _emit(row, True)
    else:
        console.print(row["value"])


@kb_app.command("list")
def kb_list(json_out: bool = typer.Option(False, "--json")):
    """List all approved knowledge entries."""
    be = _backend()
    try:
        rows = be.kb_all()
    except store.StoreError as exc:
        _fail(str(exc))
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
    """Propose setting KEY=VALUE. Requires human approval in the web UI."""
    value = _value_or_file(value, file, "VALUE")
    be = _backend()
    try:
        proposal = be.kb_propose(key=key, value=value, operation="set", author=author, note=note)
    except store.StoreError as exc:
        _fail(str(exc))
    if json_out:
        _emit(proposal, True)
    else:
        console.print(
            f"Proposed [bold]#{proposal['id']}[/]: set [cyan]{key}[/] "
            f"([yellow]pending human approval[/])"
        )
        _note_superseded(proposal)


@kb_app.command("propose-delete")
def kb_propose_delete(
    key: str = typer.Argument(...),
    note: str = typer.Option("", "--note", "-n"),
    author: str = typer.Option("agent", "--author"),
):
    """Propose deleting KEY. Requires human approval in the web UI."""
    be = _backend()
    try:
        proposal = be.kb_propose(key=key, value=None, operation="delete", author=author, note=note)
    except store.StoreError as exc:
        _fail(str(exc))
    console.print(
        f"Proposed [bold]#{proposal['id']}[/]: delete [cyan]{key}[/] "
        f"([yellow]pending human approval[/])"
    )
    _note_superseded(proposal)


@kb_app.command("pending")
def kb_pending(json_out: bool = typer.Option(False, "--json")):
    """List knowledge changes awaiting human approval."""
    be = _backend()
    try:
        rows = be.list_proposals(status="pending")
    except store.StoreError as exc:
        _fail(str(exc))
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


@kb_app.command("withdraw")
def kb_withdraw(proposal_id: int = typer.Argument(...)):
    """Retract your own pending proposal (an agent's undo; no human needed)."""
    be = _backend()
    try:
        be.withdraw_proposal(proposal_id)
    except store.StoreError as exc:
        _fail(str(exc))
    console.print(f"Withdrew proposal #{proposal_id}")


@kb_app.command("approve")
def kb_approve(proposal_id: int = typer.Argument(...)):
    """Approve a pending proposal (human action)."""
    be = _backend()
    try:
        be.approve_proposal(proposal_id)
    except store.StoreError as exc:
        _fail(str(exc))
    console.print(f"Approved proposal #{proposal_id}")


@kb_app.command("reject")
def kb_reject(proposal_id: int = typer.Argument(...)):
    """Reject a pending proposal (human action)."""
    be = _backend()
    try:
        be.reject_proposal(proposal_id)
    except store.StoreError as exc:
        _fail(str(exc))
    console.print(f"Rejected proposal #{proposal_id}")


# --- Token commands ---------------------------------------------------------


@token_app.command("create")
def token_create(
    name: str = typer.Argument(..., help="A label for this token, e.g. an agent name"),
    admin: bool = typer.Option(False, "--admin", help="Grant admin (token/passkey management)"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Create an API token. The secret is shown once — copy it now."""
    be = _backend()
    try:
        result = be.create_token(name, is_admin=admin)
    except store.StoreError as exc:
        _fail(str(exc))
    if json_out:
        _emit(result, True)
        return
    console.print(f"Created token [bold]#{result['id']}[/] [cyan]{result['name']}[/]"
                  + (" [red](admin)[/]" if result.get("is_admin") else ""))
    console.print(f"\n  [bold yellow]{result['token']}[/]\n")
    console.print("[dim]Store it now — it will not be shown again. Use it with "
                  "`issue login --token ...` or the ISSUE_TRACKER_TOKEN env var.[/]")


@token_app.command("list")
def token_list(json_out: bool = typer.Option(False, "--json")):
    """List API tokens (never shows the secret)."""
    be = _backend()
    try:
        rows = be.list_tokens()
    except store.StoreError as exc:
        _fail(str(exc))
    if json_out:
        _emit(rows, True)
        return
    if not rows:
        console.print("[dim]No tokens.[/]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("name", style="cyan")
    table.add_column("admin")
    table.add_column("created", style="dim")
    table.add_column("last used", style="dim")
    for r in rows:
        table.add_row(
            str(r["id"]),
            r["name"],
            "yes" if r.get("is_admin") else "",
            (r.get("created_at") or "").replace("T", " "),
            (r.get("last_used_at") or "—").replace("T", " "),
        )
    console.print(table)


@token_app.command("revoke")
def token_revoke(token_id: int = typer.Argument(...)):
    """Revoke an API token by id."""
    be = _backend()
    try:
        be.revoke_token(token_id)
    except store.StoreError as exc:
        _fail(str(exc))
    console.print(f"Revoked token #{token_id}")


# --- Rendering helpers ------------------------------------------------------


def _kv(label: str, value: str, style: str) -> None:
    console.print(f"  [dim]{label:>10}[/] [{style}]{value}[/]")


def _note_superseded(proposal: dict) -> None:
    superseded = proposal.get("superseded") or []
    if superseded:
        ids = ", ".join(f"#{i}" for i in superseded)
        console.print(f"  [dim]superseded earlier pending proposal(s): {ids}[/]")


def _print_comments(comments: list[dict]) -> None:
    if not comments:
        console.print("[dim]No comments.[/]")
        return
    for c in comments:
        when = c["created_at"].replace("T", " ")
        console.print(f"[bold]#{c['id']}[/] [cyan]{c['author']}[/] [dim]{when}[/]")
        console.print(c["body"])
        console.print()


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
            issue.get("assignee") or "",
        )
    console.print(table)


if __name__ == "__main__":
    app()
