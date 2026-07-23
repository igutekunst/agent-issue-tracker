"""CLI configuration: where the tracker lives and the token to reach it.

Resolution order (server and token independently):
  1. environment (ISSUE_TRACKER_SERVER / ISSUE_TRACKER_TOKEN)
  2. the config file (~/.config/agent-issue-tracker/config.json)

When a server is resolved, the CLI talks to it over HTTP; otherwise it operates
on the local SQLite database.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "agent-issue-tracker" / "config.json"


def load_config() -> dict:
    path = config_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(data: dict) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def clear_config() -> None:
    path = config_path()
    if path.exists():
        path.unlink()


def resolve_server() -> str | None:
    server = os.environ.get("ISSUE_TRACKER_SERVER") or load_config().get("server")
    return server.rstrip("/") if server else None


def resolve_token() -> str | None:
    return os.environ.get("ISSUE_TRACKER_TOKEN") or load_config().get("token")


def is_remote() -> bool:
    return resolve_server() is not None
