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
| Devin API dispatch with remediation playbook prompt | done |

## How the workflow runs

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
which issues were dispatched, so an issue re-labelled after a restart starts a second session.

A successful dispatch answers with the session that will do the work:

```json
{"status": "dispatched", "issue": "vandenplas/superset#42", "session_id": "devin-abc123"}
```

If the Devin API rejects or cannot be reached, the delivery gets `502` and the issue is un-claimed,
so GitHub's retry (or re-labelling) tries again.

## The remediation playbook

Every dispatch sends a structured prompt built from
[`src/secops_dispatcher/prompts/remediation.md`](src/secops_dispatcher/prompts/remediation.md),
with `{{placeholders}}` filled in from the issue and configuration. It instructs the agent to:

1. comment `Starting remediation` on the issue and move it to **In Progress** in the project;
2. branch from `TARGET_BASE_BRANCH` (`master` in `vandenplas/superset`);
3. upgrade the vulnerable package(s) to the lowest version that fixes the vulnerability;
4. follow `AGENTS.md` in the target repo for pre-commit checks and tests — unless the issue also
   carries the `DEMO_LABEL`, see [Demo mode](#demo-mode);
5. open a PR and move the issue to **In Review**, verifying the item's `Status` afterwards;
6. comment the resolution on the issue and link it to the PR.

Step 4 comes from a second file, [`verify_full.md`](src/secops_dispatcher/prompts/verify_full.md) or
[`verify_fast.md`](src/secops_dispatcher/prompts/verify_fast.md), chosen by the demo label.

Edit that markdown file to change the instructions — no code change needed. To preview the exact
prompt for an issue without spending ACUs, run with `DRY_RUN=true`: the dispatcher logs the rendered
prompt and skips the API call.

The session is created against `TARGET_REPO`, titled `Remediate <repo>#<n>: <issue title>`, and
tagged `secops-dispatcher` / `vulnerability`, so dispatched work is easy to find in the Devin UI. Set
`DEVIN_PLAYBOOK_ID` to additionally attach a saved Devin playbook, and `DEVIN_MAX_ACU_LIMIT` to cap
the spend of each session.

### Demo mode

Verification dominates the wall clock: pip-compiling Superset's requirement files and running its
unit suite take most of an hour, so a remediation PR normally appears ~25-60 minutes after the issue
is labelled. That is right for real operation but too slow to watch live.

Label an issue **both** `vulnerability` and `demo` and the prompt swaps step 4 for a fast path: bump
the pinned versions in place, no pip-compile, no test suite, at most `pre-commit run --files` on what
changed. Expect a PR in a few minutes, and the board to move to In Progress almost immediately.

The agent is required to open the PR description with

> Tests were skipped: dispatched with the demo label. Not verified — do not merge.

and to repeat that in the resolution comment, so a demo PR cannot be mistaken for a verified one.
Rename the label with `DEMO_LABEL`, or set `DEMO_LABEL=` to remove the fast path entirely.

## Requirements

- Docker (and Docker Compose) on the machine running the dispatcher.
- Python 3.11+ only if you want to run it outside Docker.
- Access to the `vandenplas` GitHub resources:
  - **admin** on `vandenplas/superset` — needed to create the webhook that feeds the dispatcher.
  - **write** on `vandenplas/superset` — the Devin agent pushes branches and opens PRs there.
  - **write** on the `Superset SVM` user project (project #2) — the agent moves issues between
    `In Progress` and `In Review`. This one cannot come from the agent's own GitHub credentials:
    the Devin GitHub app cannot write ProjectV2 fields (`updateProjectV2ItemFieldValue` fails with
    `FORBIDDEN: Resource not accessible by integration`), so the dispatcher forwards a PAT instead —
    see [Project board access](#project-board-access).
- Devin API access, used to start remediation sessions:
  - `DEVIN_API_KEY` — a service-user API key from https://app.devin.ai/settings/api-keys;
  - `DEVIN_ORG_ID` — your organization id (`org-…`), because sessions are created through the
    org-scoped v3 endpoint `POST /v3/organizations/{org_id}/sessions`.

  See the [Devin API reference](https://docs.devin.ai/api-reference/overview). Sessions are
  attributed to the service user; set `DEVIN_CREATE_AS_USER_ID` to attribute them to a human
  instead (needs the `ImpersonateOrgSessions` permission on the service user's role).
- The Devin agent needs its own GitHub access to `vandenplas/superset` — the dispatcher only starts
  the session, it never touches GitHub itself.

### Project board access

Set `GITHUB_PROJECT_TOKEN` to a PAT that can write the project, either

- a **classic** token (https://github.com/settings/tokens/new) with the `project` scope and nothing
  else — the token is only used for board moves; or
- a **fine-grained** token with **Account permissions → Projects: Read and write**. That section only
  appears when the token's resource owner is the user who owns the project, so classic is usually the
  quicker route.

The dispatcher forwards it to each session as a session-scoped secret named `GITHUB_PROJECT_TOKEN`,
and the prompt tells the agent to use it (via `GH_TOKEN`) for the two `updateProjectV2ItemFieldValue`
mutations. Leave it unset and the dispatcher still works, but the agent is told upfront that it
probably cannot move the item and must report the step as not done rather than assume it worked —
the board's own automation rules can move items on "item added" or "PR linked", which looks
identical to the agent having done it.

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
   `http://dispatcher:8080/webhooks/github`. It exits with
   `SMEE_URL is not set` if you skipped step 1.
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
| `TARGET_BASE_BRANCH` | `master` | Default branch of `TARGET_REPO`, branched from for the fix |
| `VULNERABILITY_LABEL` | `vulnerability` | Only issues with this label are dispatched |
| `DEMO_LABEL` | `demo` | Issues also carrying this label skip the target repo's tests (see [Demo mode](#demo-mode)); set empty to disable |
| `GITHUB_PROJECT_URL` | project #2 URL | Project board the agent updates |
| `GITHUB_PROJECT_NAME` | `Superset SVM` | Project board name used in the prompt |
| `SMEE_URL` | _empty_ | smee.io channel relayed by the optional `smee` compose profile |
| `GITHUB_WEBHOOK_SECRET` | _empty_ | Shared secret used to verify webhook signatures |
| `GITHUB_PROJECT_TOKEN` | _empty_ | GitHub PAT with project write access, passed to the session for the board moves |
| `DEVIN_API_KEY` | _empty_ | Devin service-user API key used to start sessions |
| `DEVIN_ORG_ID` | _empty_ | Devin organization id (`org-…`) the sessions belong to |
| `DEVIN_API_BASE_URL` | `https://api.devin.ai` | Devin API base URL |
| `DEVIN_REQUEST_TIMEOUT_SECONDS` | `30` | Timeout for Devin API requests |
| `DEVIN_PLAYBOOK_ID` | _empty_ | Optional saved Devin playbook to attach to each session |
| `DEVIN_MAX_ACU_LIMIT` | _empty_ | Optional ACU cap per session |
| `DEVIN_CREATE_AS_USER_ID` | _empty_ | Optional user (`user-…`) to attribute sessions to |
| `DRY_RUN` | `false` | Log the rendered prompt instead of calling the Devin API |

Without `DEVIN_API_KEY` and `DEVIN_ORG_ID` the dispatcher still starts, but degrades to dry-run mode
so health checks and webhook wiring can be verified before the credentials are in place;
`GET /config` reports which mode is active as `dispatch_mode`. `.env` is git-ignored — keep secrets out of commits.

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
# {"status":"dispatched","issue":"vandenplas/superset#1","session_id":"devin-abc123"}
```

Run with `DRY_RUN=true` to see the prompt that would be sent (`session_id` comes back `null`).

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
