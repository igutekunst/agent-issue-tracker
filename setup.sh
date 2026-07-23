#!/usr/bin/env bash
# One-shot setup: install the `issue` CLI onto your PATH and build the web UI.
set -euo pipefail
cd "$(dirname "$0")"

BIN=""      # directory the `issue` executable landed in

echo "==> Installing the 'issue' CLI ..."
if command -v uv >/dev/null 2>&1; then
  # `uv tool install` gives an isolated, globally-available executable.
  uv tool install --force --editable .
  BIN="$(uv tool dir 2>/dev/null)/../bin" || true
  # uv places executables in ~/.local/bin by default.
  [ -x "$HOME/.local/bin/issue" ] && BIN="$HOME/.local/bin"
elif command -v pipx >/dev/null 2>&1; then
  pipx install --force -e .
  BIN="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || echo "$HOME/.local/bin")"
else
  # Fall back to a plain pip install. Prefer --user so it lands in ~/.local/bin.
  python3 -m pip install --user -e . || python3 -m pip install -e .
  BIN="$(python3 -c 'import sysconfig; print(sysconfig.get_path("scripts", "posix_user"))' 2>/dev/null || true)"
fi

echo "==> Building the web frontend ..."
if command -v npm >/dev/null 2>&1; then
  (cd frontend && npm install && npm run build)
  echo "    Web UI built."
else
  echo "!! npm not found — skipping frontend build (the CLI still works)."
  echo "   Install Node, then run: cd frontend && npm run build"
fi

echo ""
if command -v issue >/dev/null 2>&1; then
  echo "==> Success. 'issue' is on your PATH. Try:  issue add \"My first issue\""
else
  echo "==> 'issue' installed but not on your PATH yet."
  [ -n "$BIN" ] && echo "    It's in: $BIN"
  echo ""
  echo "    bash/zsh:  export PATH=\"\$HOME/.local/bin:\$PATH\"   # add to ~/.bashrc or ~/.zshrc"
  echo "    fish:      fish_add_path ~/.local/bin"
  if command -v uv >/dev/null 2>&1; then
    echo "    (or let uv fix your shell PATH automatically:  uv tool update-shell )"
  fi
  echo ""
  echo "    No-PATH fallback that always works:  python3 -m issue_tracker.cli --help"
fi
