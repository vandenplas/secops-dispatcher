# secops-dispatcher

Implements a process that monitors for SVM (security vulnerability management) issues in a project
and dispatches those issues for automated remediation in Devin sessions.

The dispatcher watches for GitHub issues labelled `vulnerability` in
[`vandenplas/superset`](https://github.com/vandenplas/superset) and hands each one to a Devin cloud
agent, which opens a remediation PR and keeps the
["Superset SVM" project board](https://github.com/users/vandenplas/projects/2) up to date.

## Status

Built incrementally:

| Capability | State |
| --- | --- |
| HTTP service + configuration + Docker packaging | done |
| GitHub webhook receiver (`vulnerability` label filter) | done |
| Devin API dispatch with remediation playbook prompt | planned |

Until the Devin integration lands, an eligible issue is logged as `would dispatch <repo>#<n>`
instead of starting a session.

## How the workflow will run

```
GitHub issue labelled "vulnerability"
        │  webhook delivery (issues event)
        ▼
   smee.io channel  ──►  POST /webhooks/github  (dispatcher in Docker, on your laptop)
                                │  Devin API
                                ▼
                        Devin cloud agent  ──►  PR in vandenplas/superset
                                            └─►  "Superset SVM" project board updates
```

An `issues` delivery is dispatched only when **all** of these hold, and is otherwise answered
`200 {"status": "ignored", "reason": ...}` so GitHub doesn't retry:

- the signature in `X-Hub-Signature-256` matches `GITHUB_WEBHOOK_SECRET` (otherwise `401`);
- `repository.full_name` equals `TARGET_REPO`;
- the action is `opened`, `reopened`, or `labeled` — and for `labeled`, the label just added is the
  `VULNERABILITY_LABEL` (so adding `priority` to an already-labelled issue doesn't re-dispatch);
- the issue is open and carries the `VULNERABILITY_LABEL`.

Each issue is dispatched at most once per container lifetime, so webhook retries and label churn
are answered `{"status": "duplicate"}`. The ledger is in memory: restarting the container forgets
which issues were dispatched.

## Requirements

- Docker (and Docker Compose) on the machine running the dispatcher.
- Python 3.11+ only if you want to run it outside Docker.
- Access to the `vandenplas` GitHub resources:
  - **admin** on `vandenplas/superset` — needed to create the webhook that feeds the dispatcher.
  - **write** on `vandenplas/superset` — the Devin agent pushes branches and opens PRs there.
  - **write** on the `Superset SVM` user project (project #2) — the agent moves issues between
    `In Progress` and `In Review`.
- A Devin API key (`DEVIN_API_KEY`) from https://app.devin.ai/settings/api-keys, used to start
  remediation sessions. See the [Devin API reference](https://docs.devin.ai/api-reference/overview).

## Connecting GitHub to the dispatcher via smee.io

GitHub cannot reach a container on your laptop, so deliveries are relayed through a
[smee.io](https://smee.io) channel.

1. Open https://smee.io/new and copy the channel URL, then put it in `.env` as
   `SMEE_URL=https://smee.io/<channel>`.
2. Generate a webhook secret and add it to `.env` as `GITHUB_WEBHOOK_SECRET`:
   ```bash
   openssl rand -hex 32
   ```
3. In `vandenplas/superset` → **Settings → Webhooks → Add webhook** (needs repo admin):
   - **Payload URL**: the smee.io channel URL from step 1
   - **Content type**: `application/json`
   - **Secret**: the value from step 2
   - **Events**: *Let me select individual events* → **Issues** only
4. Start the dispatcher together with the relay:
   ```bash
   docker compose --profile smee up --build
   ```
   The `smee` service runs `smee-client` and forwards each delivery to
   `http://dispatcher:8080/webhooks/github`.
5. Confirm the wiring: GitHub's webhook page → **Recent Deliveries** shows the `ping` event, and the
   dispatcher answers `{"status": "pong"}`. Then label an issue `vulnerability` and watch the logs:
   ```bash
   docker compose logs -f dispatcher
   ```

The smee.io channel URL is effectively public — anyone with it can post payloads. The signature
check is what makes this safe, so never run the dispatcher with an empty `GITHUB_WEBHOOK_SECRET`
(deliveries are refused with `503` if you do).

## Configuration

All configuration comes from environment variables (a local `.env` file is read automatically).
Start from the template:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Bind address of the HTTP server |
| `PORT` | `8080` | Bind port |
| `LOG_LEVEL` | `INFO` | Python log level |
| `TARGET_REPO` | `vandenplas/superset` | Repository whose issues are dispatched |
| `VULNERABILITY_LABEL` | `vulnerability` | Only issues with this label are dispatched |
| `GITHUB_PROJECT_URL` | project #2 URL | Project board the agent updates |
| `SMEE_URL` | _empty_ | smee.io channel relayed by the optional `smee` compose profile |
| `GITHUB_WEBHOOK_SECRET` | _empty_ | Shared secret used to verify webhook signatures |
| `DEVIN_API_KEY` | _empty_ | Devin API key used to start sessions |
| `DEVIN_API_BASE_URL` | `https://api.devin.ai/v1` | Devin API base URL |

`DEVIN_API_KEY` is unused until the Devin integration lands. `.env` is git-ignored — keep secrets out
of commits.

## Running with Docker

```bash
docker compose up --build              # dispatcher only
docker compose --profile smee up --build   # dispatcher + smee.io relay
curl localhost:8080/healthz            # {"status":"ok"}
curl localhost:8080/config             # effective config, secrets shown only as *_set booleans
```

Stop with `docker compose down`.

### Sending a webhook by hand

Useful for testing without touching GitHub — the signature must be computed over the exact bytes
posted:

```bash
BODY='{"action":"labeled","label":{"name":"vulnerability"},"repository":{"full_name":"vandenplas/superset"},"issue":{"number":1,"title":"CVE-2025-0001 in urllib3","state":"open","html_url":"https://github.com/vandenplas/superset/issues/1","body":"Upgrade urllib3","labels":[{"name":"vulnerability"}]}}'
SIG="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$GITHUB_WEBHOOK_SECRET" | awk '{print $2}')"
curl -s localhost:8080/webhooks/github \
  -H 'Content-Type: application/json' \
  -H 'X-GitHub-Event: issues' \
  -H "X-Hub-Signature-256: $SIG" \
  -d "$BODY"
# {"status":"dispatched","issue":"vandenplas/superset#1","session_id":null}
```

## Running locally without Docker

Requires Python 3.11+. Name the interpreter explicitly — creating the venv from an older
`python3` makes dependency resolution backtrack for minutes instead of failing fast.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
make install                   # pip install -e ".[dev]"
make run                       # serves on $HOST:$PORT
```

## Development

Activate the venv first (`source .venv/bin/activate`), otherwise these targets can't find the tools:

```bash
make lint                      # ruff check + ruff format --check
make fmt                       # ruff format (rewrites files)
make test                      # pytest
```

CI runs the same lint and test steps plus a Docker build on every pull request.
