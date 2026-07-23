# Deploying the tracker (DigitalOcean + HTTPS)

This runs the tracker on a VPS behind [Caddy](https://caddyserver.com), which
gets and renews a Let's Encrypt certificate automatically. Auth is **on** in
this setup: agents authenticate with API tokens, and you sign in to the web UI
with a passkey.

Target used in the examples: `issues.supercortex.io`.

## 1. DNS

Point the domain at your droplet before starting (Caddy validates over HTTP):

```
A    issues.supercortex.io    ->  <droplet IPv4>
AAAA issues.supercortex.io    ->  <droplet IPv6>   # if you have one
```

Open ports **80** and **443** (DigitalOcean firewall + the droplet).

## 2. Install Docker on the droplet

```bash
curl -fsSL https://get.docker.com | sh
```

## 3. Get the code and configure

```bash
git clone https://github.com/igutekunst/agent-issue-tracker.git
cd agent-issue-tracker
cp .env.example .env
# edit .env so DOMAIN=issues.supercortex.io
```

## 4. Launch

```bash
docker compose up -d --build
```

Caddy will obtain the TLS certificate within a minute or so. Visit
`https://issues.supercortex.io` — you'll see the login screen.

## 5. Bootstrap: your first token and passkey

On first start (auth enabled, no admin token) the app mints a one-time **admin
bootstrap token**. Retrieve it:

```bash
docker compose exec app cat /data/bootstrap-token.txt
```

Then:

- **Web UI** — on the login screen choose to enroll, paste the bootstrap token,
  and register your device. You're now signed in with a passkey; the token is no
  longer needed for the browser.
- **CLI / agents** — mint a named token per agent and log in:

  ```bash
  # from your laptop, using the bootstrap token once:
  issue login --server https://issues.supercortex.io --token <bootstrap-token>
  issue token create my-laptop-agent          # prints a token, shown once
  # give each agent its own token via env:
  export ISSUE_TRACKER_SERVER=https://issues.supercortex.io
  export ISSUE_TRACKER_TOKEN=it_...            # the agent's token
  export ISSUE_TRACKER_ACTOR=my-laptop-agent   # optional; token name is used by default
  issue list
  ```

Keep the bootstrap token somewhere safe — it's your recovery path if you lose
your passkey device. You can also `issue token revoke <id>` it and rely on a
fresh admin token later.

## Migrating existing local issues to the server

If you already have issues in a local `.issues/tracker.db`, push them up in one
step from the project directory (needs an **admin** token for the target):

```bash
issue login --server https://issues.supercortex.io --token <admin-token>
issue migrate            # reads the local db, imports it into the server
```

`migrate` always reads the local database regardless of the configured server,
so it works even while you're logged in to the remote. Ids and timestamps are
preserved when the server has no colliding issues; otherwise everything is
reinserted under fresh ids with all parent/dependency/comment references
remapped.

For a portable dump (backup, or moving between two servers) use the underlying
commands directly — `export`/`import` operate on whichever tracker the CLI is
pointed at:

```bash
issue export -o backup.json      # dump the active tracker to JSON
issue import backup.json         # load a dump into the active tracker
```

## Everyday operations

```bash
docker compose logs -f app          # app logs
docker compose pull && docker compose up -d --build   # update to latest
docker compose down                 # stop (data persists in the named volume)
```

Data (SQLite DB, signing secret, bootstrap token) lives in the `data` Docker
volume. Back it up with:

```bash
docker compose exec app sqlite3 /data/tracker.db ".backup /data/backup.db"
docker compose cp app:/data/backup.db ./backup-$(date +%F).db
```

## Configuration reference

| Env var | Purpose | Set by compose to |
| --- | --- | --- |
| `ISSUE_TRACKER_AUTH` | Require auth on all data endpoints | `1` |
| `ISSUE_TRACKER_DB` | SQLite path | `/data/tracker.db` |
| `ISSUE_TRACKER_RP_ID` | WebAuthn Relying Party ID (your domain) | `${DOMAIN}` |
| `ISSUE_TRACKER_ORIGIN` | Expected web origin | `https://${DOMAIN}` |
| `ISSUE_TRACKER_RP_NAME` | Name shown in the passkey prompt | `${RP_NAME}` |

## Notes

- **Passkeys need HTTPS** and the origin must match `ISSUE_TRACKER_ORIGIN`. That's
  why the domain + Caddy are required (localhost is the only http exception, for
  dev).
- **SSE** (`/events`) is proxied unbuffered by Caddy so the live graph/feed
  update in real time.
- To run a second environment on a different subdomain, copy this directory with
  a different `DOMAIN`.
