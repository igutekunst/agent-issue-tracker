#!/usr/bin/env bash
# One-command deploy on a VPS. Run this ON the droplet after cloning the repo:
#
#   git clone https://github.com/igutekunst/agent-issue-tracker.git
#   cd agent-issue-tracker
#   ./deploy.sh issues.supercortex.io
#
# DNS for the domain must already point at this droplet and ports 80/443 be open
# (Caddy needs them to obtain a Let's Encrypt certificate).
set -euo pipefail
cd "$(dirname "$0")"

DOMAIN="${1:-${DOMAIN:-}}"
if [ -z "$DOMAIN" ]; then
  echo "usage: ./deploy.sh <domain>    e.g. ./deploy.sh issues.supercortex.io"
  exit 1
fi

echo "==> Deploying for domain: $DOMAIN"

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker ..."
  curl -fsSL https://get.docker.com | sh
fi

# docker compose (plugin) vs docker-compose (legacy)
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "!! docker compose not found after install" >&2
  exit 1
fi

if [ ! -f .env ]; then
  printf 'DOMAIN=%s\nRP_NAME=Agent Issue Tracker\n' "$DOMAIN" > .env
  echo "==> Wrote .env"
fi

echo "==> Building and starting (this can take a few minutes the first time) ..."
$DC up -d --build

echo "==> Waiting for the app to come up ..."
for _ in $(seq 1 20); do
  if $DC exec -T app test -f /data/bootstrap-token.txt 2>/dev/null; then break; fi
  sleep 2
done

echo ""
echo "==> Done. https://$DOMAIN should be live once Caddy finishes issuing TLS (~1 min)."
echo ""
echo "Your one-time admin bootstrap token (enroll a passkey / mint agent tokens with it):"
echo "-------------------------------------------------------------------------------"
$DC exec -T app cat /data/bootstrap-token.txt 2>/dev/null \
  || echo "(not ready yet — run: $DC exec app cat /data/bootstrap-token.txt)"
echo "-------------------------------------------------------------------------------"
echo "Keep it safe: it is your recovery path if you lose your passkey device."
