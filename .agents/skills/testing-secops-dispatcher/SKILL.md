---
name: testing-secops-dispatcher
description: How to run and end-to-end test the secops-dispatcher FastAPI service locally (Docker Compose, /healthz, /config, /docs Swagger UI, signed GitHub webhooks, smee.io relay, lint/tests).
---

# Testing secops-dispatcher

## Running the service

Docker (primary path, matches README):

```bash
cp .env.example .env            # optional; compose declares .env as required: false
docker compose up --build -d    # image secops-dispatcher:local, published on :8080
docker compose ps               # STATUS should reach "Up ... (healthy)"
docker compose down             # teardown
```

The Dockerfile has a `HEALTHCHECK` that polls `/healthz` inside the container; it usually flips to
`healthy` within the 5 s start period. Check it with:

```bash
docker inspect --format '{{.State.Health.Status}}' secops-dispatcher-dispatcher-1
```

Without Docker: the repo ships a Python 3.12 `.venv` (created by the blueprint via
`uv venv --python 3.12 .venv && uv pip install -p .venv -e ".[dev]"`). Recreate it with those
commands if missing. `PORT=8081 .venv/bin/secops-dispatcher` is handy when 8080 is already taken by
the container — the `PORT` env var is honoured and reflected in `/config`.

Gotchas:
- `make lint` / `make test` invoke bare `ruff` / `pytest`, so they fail with
  `No such file or directory` unless the venv is activated (`source .venv/bin/activate`) or you call
  `.venv/bin/ruff` / `.venv/bin/pytest` directly.
- `python -m venv .venv` with a system Python older than 3.11 does not fail fast against
  `requires-python = ">=3.11"`; pip backtracks for many minutes. Always create the venv with a 3.12
  interpreter (`uv python find 3.12`).

## Endpoints

- `GET /healthz` → `{"status":"ok"}`
- `GET /config` → redacted config from `Settings.redacted()` in `src/secops_dispatcher/config.py`
- `GET /docs` → Swagger UI (the only in-app UI); GET operations are executable via "Try it out" → "Execute"
- `POST /webhooks/github` → GitHub `issues` webhook receiver (HMAC-SHA256 signed)

## Testing the webhook receiver

Generate a real secret (`openssl rand -hex 32`) into `.env` as `GITHUB_WEBHOOK_SECRET`, restart the
container, then sign the **exact bytes** you POST — signing a re-serialized payload will not match:

```bash
set -a; source .env; set +a
sign() { printf '%s' "$1" | openssl dgst -sha256 -hmac "$GITHUB_WEBHOOK_SECRET" | awk '{print "sha256="$2}'; }
BODY='{"action":"opened","repository":{"full_name":"vandenplas/superset"},"issue":{"number":1,"title":"t","state":"open","html_url":"u","labels":[{"name":"vulnerability"}]}}'
curl -s -o /tmp/o.json -w '%{http_code}\n' localhost:8080/webhooks/github \
  -H 'Content-Type: application/json' -H 'X-GitHub-Event: issues' \
  -H "X-Hub-Signature-256: $(sign "$BODY")" -d "$BODY"
```

Use a **distinct issue number per case** — the in-memory `DispatchLedger` is at-most-once per
`repo#number` for the container's lifetime, so reusing a number yields `{"status":"duplicate"}` and
silently masks whatever you meant to test. `docker compose restart dispatcher` clears the ledger.

Adversarial cases worth keeping (a broken receiver passes the naive ones):
- Sign body A, POST body B (both individually valid, different issue numbers) → must be `401`.
  Catches verification against a parsed/re-serialized payload.
- Right label but a non-target `repository.full_name` → `ignored`, not `dispatched`.
- `action=labeled` with `label.name` = some other label on an issue that already carries the
  vulnerability label → `ignored`. A "does the issue have the label?" check wrongly dispatches.
- Empty `GITHUB_WEBHOOK_SECRET` → `503` (not `401`), so 401-everything implementations are caught.

Dispatch is only observable in logs until the Devin integration lands:
`docker compose logs dispatcher | grep 'would dispatch'`. The 502-and-release-the-claim path is not
reachable from outside the container while `LoggingDispatcher` is wired in — don't claim it as
tested from HTTP alone.

## Testing the smee.io relay (no GitHub changes needed)

Do NOT create webhooks on the target repo to test the relay. Instead create a personal channel:

1. Browse to https://smee.io/new — it redirects to `https://smee.io/<channel>`; that page lists
   deliveries live and is the UI worth recording.
2. Put it in `.env` as `SMEE_URL=https://smee.io/<channel>`, then
   `docker compose --profile smee up --build -d`. Wait for
   `Forwarding ... to http://dispatcher:8080/webhooks/github` / `Connected` in
   `docker compose logs smee`.
3. `curl` a signed payload at the **channel URL** (not localhost) with `X-GitHub-Event`,
   `X-GitHub-Delivery` and `X-Hub-Signature-256`; smee forwards headers, so the signature survives.
4. Evidence: the channel page shows the delivery, `docker compose logs smee` shows
   `POST http://dispatcher:8080/webhooks/github - 200`, and the dispatcher logs the dispatch.

The channel page's **Redeliver** button (circular-arrow icon on an expanded delivery) is a free way
to exercise retry/duplicate handling exactly as GitHub would. Posting an *unsigned* body to the
public channel is a realistic attacker test — expect `- 401` in the smee logs.

Requires egress to smee.io and registry.npmjs.org (the sidecar `npx`-installs `smee-client` on
start); verify with `curl -sI https://smee.io/new` and `docker run --rm node:22-alpine npm ping`.

## Testing the secret-redaction contract

`/config` must never echo `DEVIN_API_KEY` / `GITHUB_WEBHOOK_SECRET`, only `devin_api_key_set` /
`github_webhook_secret_set` booleans. Test it adversarially with unique sentinel values so a leak is
greppable, and check the container logs too (startup logs the config):

```bash
printf 'DEVIN_API_KEY=devin-LEAKCANARY-AAA111\nGITHUB_WEBHOOK_SECRET=hook-LEAKCANARY-BBB222\n' >> .env
docker compose up --build -d
curl -s localhost:8080/config | grep -c LEAKCANARY          # must be 0
docker compose logs dispatcher | grep -c LEAKCANARY         # must be 0
curl -s localhost:8080/config | python3 -m json.tool        # *_set must be true
```

Run the app once with no `.env` as a negative control: the booleans should be `false`. Without that
control, a hard-coded `false` would look identical to correct redaction.

Delete the sentinel `.env` afterwards — it is git-ignored but pollutes later runs.

## Lint / tests

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .   # not run by CI, so drift is possible
.venv/bin/pytest -q
```

A `StarletteDeprecationWarning` from `fastapi.testclient` is expected noise, not a failure.

## Devin Secrets Needed

None so far. `GITHUB_WEBHOOK_SECRET` can be self-generated with `openssl rand -hex 32` — it only has
to match between whoever signs the request and the container, so no user-provided secret is needed
unless you are testing against a webhook that GitHub itself signs. `SMEE_URL` is self-service at
https://smee.io/new. The Devin dispatch step will need a real `DEVIN_API_KEY`; until then a fake
sentinel value is enough.
