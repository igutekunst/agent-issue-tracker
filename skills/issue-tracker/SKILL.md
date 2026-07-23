---
name: issue-tracker
description: >-
  Track work in this repo's local issue tracker and read/propose entries in its
  human-approved knowledge base. Use whenever you need to record tasks, break
  work into a dependency graph, find the next actionable issue, check project
  facts/conventions, or propose a change to a shared fact. Invoke for phrases
  like "add an issue", "what should I work on next", "mark this done", "what's
  the deploy URL", or "remember that ...".
---

# Issue Tracker

A local-first, hierarchical issue tracker plus a human-gated knowledge base,
driven entirely from the `issue` CLI. Data lives in `.issues/tracker.db`
(git-ignored) at the repo root. A human watches progress and approves knowledge
changes through the web UI (`issue serve`).

## Setup (once)

If `issue` is not on PATH, install it:

```bash
pip install -e .        # from the repo root (or: uv pip install -e .)
```

Verify: `issue list`.

## Core workflow for agents

1. **Before starting work**, find what's actionable (open + unblocked, most
   important first):
   ```bash
   issue next
   ```
2. **Claim it**: mark in-progress and record your branch/worktree so the human
   can see who's doing what.
   ```bash
   issue start 12
   issue update 12 --assignee agent --branch claude/feature-x
   ```
3. **Break big work down** into sub-issues and dependencies as you learn more.
4. **When done**: `issue done 12`.

Always prefer `--json` when you need to parse output programmatically.

## Issue commands

```bash
issue add "Title" -d "Description" -p P1            # create (priority P0..P3)
issue add "Subtask" --parent 3 --depends-on 2       # child of #3, blocked by #2
issue list [--status open] [--priority P0] [--json] # list, most important first
issue next [--json]                                 # actionable: open & unblocked
issue tree                                          # hierarchy view
issue show 3 [--json]                               # detail incl. blockers/children
issue update 3 --status in_progress --assignee agent --branch b --meta '{"pr":42}'
issue start 3 | issue done 3 | issue block 3        # status shortcuts
issue rm 3 -y                                        # delete
```

Dependencies (`BLOCKER` must finish before `BLOCKED`):

```bash
issue dep add 2 5     # #2 blocks #5  (i.e. #5 depends on #2)
issue dep rm 2 5
```

Statuses: `open`, `in_progress`, `blocked`, `done`, `cancelled`.
Priorities: `P0` (highest) .. `P3`.

## Identify yourself (so the human sees who changed what)

Set the `ISSUE_TRACKER_ACTOR` environment variable to your agent name (or pass
`issue --actor <name> ...`). Every change you make is then attributed to you in
the human's activity feed and live notifications.

```bash
export ISSUE_TRACKER_ACTOR=claude-worker-1
issue done 12            # shows up as "Updated issue #12 — claude-worker-1"
issue activity           # recent changes: who changed what, newest first
```

## Local vs remote

By default the CLI uses the local SQLite database. To use a shared/remote
server, either run `issue login --server <url> --token <token>` once, or set:

```bash
export ISSUE_TRACKER_SERVER=https://issues.example.com
export ISSUE_TRACKER_TOKEN=it_...      # your API token
```

Everything below works the same in either mode. On a remote server with auth
enabled, your **token's name is used as the actor** automatically (no need to set
`ISSUE_TRACKER_ACTOR`). If you get an authentication error, your token is missing
or revoked — ask the human for a new one (`issue token create <name>`).

## Checking the build and polling for changes

```bash
issue version --json      # {version, features[], db} — confirm a capability is present
issue changes --json      # {token, ...} — grab the current update token
issue changes --since 42  # what changed since token 42 (or an ISO timestamp) + new token
issue activity --json     # recent change feed with actor + human-readable text
```

Use `issue changes` as an update sentinel when you'd rather poll than watch the
web UI: keep the returned `token` and pass it back as `--since` later to see
whether (and what) changed. Use `issue version` to verify the build has a
feature (e.g. the `features` list contains `kb-withdraw`) before depending on it.

**Fields worth setting for coordination:** `--assignee`, `--branch`,
`--worktree`, and freeform `--meta '<json>'` (e.g. PR number, links). These let
the human — and other agents — see who owns what and where the work lives.

## Knowledge base (human-approved facts)

A key/value store of durable project facts (conventions, URLs, decisions).
Agents **read freely** but **cannot change** it directly — every write is queued
until a human approves it in the web UI.

```bash
issue kb list [--json]                 # all approved facts
issue kb get deploy.url                 # read one value
issue kb propose deploy.url "https://..." -n "why this change"   # queue a change
issue kb propose-delete stale.key -n "no longer true"
issue kb pending [--json]               # see what's awaiting approval
issue kb withdraw 7                      # retract your own pending proposal #7
```

**One pending proposal per key.** Proposing again for a key that already has a
pending proposal *supersedes* the earlier one (it won't stack duplicates in the
human's queue) — so just re-propose to fix a mistake. You can also
`issue kb withdraw <id>` to retract a pending proposal yourself without needing
a human to reject it. (`withdraw` is your own undo; `approve`/`reject` are the
human's decision.)

**Values may be long and use markdown** (headings, lists, tables, code fences,
links) — they render as formatted markdown in the web UI. For multi-line values,
avoid shell-quoting pain by reading the value from a file or stdin:

```bash
issue kb propose runbook.deploy --file NOTES.md -n "deploy runbook"
issue kb propose runbook.deploy -f - -n "deploy runbook" <<'EOF'
# Deploy runbook
1. Tag the release
2. Run the pipeline
EOF
```

**Do not assume a proposed value is live.** After `kb propose`, the value only
takes effect once a human approves it. If you need a fact that isn't approved
yet, tell the human it's pending rather than acting on the proposed value.

Use the KB for things that should outlive a single task and that a human should
sign off on: "the prod database is X", "we deploy via Y", "the API base path is
Z". Use issues (not the KB) for work items.

## Web interface

`issue serve` starts the dependency-graph view, issue board, and the approval
queue at http://127.0.0.1:8000. The human uses this to watch the graph update
live (SSE) and to approve/reject knowledge proposals. You generally don't need
to run it, but you can point the human at it.
