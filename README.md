# secops-dispatcher

Implements a process that monitors for SVM (security vulnerability management) issues in a project
and dispatches those issues for automated remediation in Devin sessions.

The dispatcher watches for GitHub issues labelled `vulnerability` in
[`vandenplas/superset`](https://github.com/vandenplas/superset) and hands each one to a Devin cloud
agent, which opens a remediation PR and keeps the
["Superset SVM" project board](https://github.com/users/vandenplas/projects/2) up to date.

## Status

Built incrementally. This revision contains the service skeleton:

| Capability | State |
| --- | --- |
| HTTP service + configuration + Docker packaging | done |
| GitHub webhook receiver (`vulnerability` label filter) | planned |
| Devin API dispatch with remediation playbook prompt | planned |

## How the workflow will run

```
GitHub issue labelled "vulnerability"
        │  webhook delivery
        ▼
   smee.io channel  ──►  secops-dispatcher (Docker, on your laptop)
                                │  Devin API
                                ▼
                        Devin cloud agent  ──►  PR in vandenplas/superset
                                            └─►  "Superset SVM" project board updates
```

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
| `GITHUB_WEBHOOK_SECRET` | _empty_ | Shared secret used to verify webhook signatures |
| `DEVIN_API_KEY` | _empty_ | Devin API key used to start sessions |
| `DEVIN_API_BASE_URL` | `https://api.devin.ai/v1` | Devin API base URL |

`GITHUB_WEBHOOK_SECRET` and `DEVIN_API_KEY` are unused by the current skeleton and are required once
the webhook and Devin integrations land. `.env` is git-ignored — keep secrets out of commits.

## Running with Docker

```bash
docker compose up --build      # or: make docker-build && make docker-run
curl localhost:8080/healthz    # {"status":"ok"}
curl localhost:8080/config     # effective config, secrets shown only as *_set booleans
```

Stop with `docker compose down`.

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
