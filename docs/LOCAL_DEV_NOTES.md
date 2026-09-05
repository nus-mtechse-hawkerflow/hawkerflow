# Local server — implementation notes

Engineering reference for `scripts/local_server.py` and the local-only extras it serves
(`/demo/`, the dashboard, the fake multi-customer auth). For the step-by-step "how do I run
this" walkthrough, see [RUN_LOCALLY.md](RUN_LOCALLY.md) instead — this doc is for whoever
touches `local_server.py` or `apps/demo/` next.

Nothing here ships anywhere: `docs/` is never synced to S3 (`apps/` is, manually, per
SETUP.md Part 4) or deployed via SAM (`infra/` is). `apps/demo/` itself *would* get copied up
by a manual `aws s3 sync apps/ ...`, but it calls `/v1/...` as a relative path and its
`?token=` bypass gets rejected by the real Cognito authorizer — so it rides along harmlessly
inert on a real deployment rather than doing anything. Everything else here (identities,
extra stall, metrics endpoint) only exists inside `local_server.py` and never reaches
`scripts/seed_data.py` or `infra/template.yaml`.

## Local-only additions and where they live

| Addition | Where | Notes |
|---|---|---|
| `/demo/` launcher + live dashboard | `apps/demo/index.html`, served by `local_server.py` | Polls `GET /_local/metrics` every 2s |
| Fake identities `local-customer1..4` | `USERS` dict in `local_server.py` | Alongside the original `local-diner` / `local-owner` |
| 3rd stall "Guo's Satay" | `EXTRA_LOCAL_STALLS` in `local_server.py` | Deliberately kept out of `scripts/seed_data.py` — a real `make seed` against AWS still only creates the original 2 stalls |
| `?token=local-customerN` URL bypass | `apps/diner/index.html`, `apps/stall/index.html` | Reads once on load, stores to `sessionStorage`; no-ops against a real Cognito-backed deploy |
| Checkout payment-method UI | `apps/diner/index.html` | Cosmetic only — adds a `paymentMethod` field the backend ignores; still `SIMULATED_PAID` |
| `/_local/metrics` endpoint | `local_server.py` | In-memory `Counter`s guarded by `METRICS_LOCK` (server is `ThreadingHTTPServer`) — total requests, by-service, by-status, order-by-status, order-by-stall, an order-events feed |
| Order simulator | `apps/demo/index.html` (client-side) | Toggle loop hitting real `POST /v1/orders` in randomized batches of 1-100 orders, fixed 5s cadence (`SIM_BATCH_INTERVAL_MS`); no server-side component, no auto-stop |
| Requests-over-time chart | `apps/demo/index.html` (SVG, drawn client-side) + `timeseries_snapshot()` in `local_server.py` | 60s buckets, 240 buckets = 4h of history, zero-filled for a continuous x-axis; server prunes buckets older than `BUCKET_HISTORY` on every write. Changing `BUCKET_SECONDS`/`BUCKET_HISTORY` changes both the window and the point count sent on every 2s dashboard poll — keep points per poll reasonable (240 is fine; don't drop `BUCKET_SECONDS` back toward single digits without also shrinking the window). |
| Chart x-axis timezone | `metrics_snapshot()` sends `startedAtEpoch` (Unix epoch, UTC); `apps/demo/index.html`'s `formatSGT()` converts each bucket to actual Singapore time (`Intl.DateTimeFormat` with `timeZone: "Asia/Singapore"`) | Deliberately not relative ("-2h") and not the viewer's local timezone — always wall-clock SGT, matching the project's `ap-southeast-1` region, regardless of what machine views the dashboard. |

## Gotchas for anyone touching `local_server.py`

- **`sam` CLI is not required** for `make local` / `make install` / `make lint` / `make test`
  — only for `make deploy-*` (SETUP.md Part 3+). Don't add it as a dependency for local dev.
- **`ruff check .` (no path args) also lints `.venv/`** if a venv lives inside the repo root,
  because the project's ruff `exclude` in `pyproject.toml` only lists `.aws-sam`, not `.venv`.
  Scope commands to real source dirs: `ruff check services scripts tests infra apps`.
- **The server only prints to stdout on pipeline events** (`pipeline -> ...`) — an idle server
  with no log output is normal, not a hang. Note also: Python fully buffers stdout when it's
  *not* a TTY, so redirecting output to a file (`python scripts/local_server.py > out.log &`)
  can delay when lines actually appear — irrelevant when running it directly in a foreground
  terminal (the documented way), only trips up ad hoc background/redirected runs.
- **The server is a `ThreadingHTTPServer`, not a plain `HTTPServer`** — this matters. A plain
  single-threaded server with HTTP/1.1 keep-alive lets one idle held-open connection (a
  browser tab left open, another app's dev tools, etc.) starve every other request
  indefinitely with no error anywhere. That was the original implementation and it broke
  multi-tab use (which `/demo/`'s Customer 1-4 tiles make the normal case) — if this ever
  regresses back to `HTTPServer`, multi-tab demos will silently hang. Test: hold one keep-alive
  connection open, confirm a concurrent request still returns immediately.
- Restarting the server always wipes in-memory data (orders, simulated traffic, etc.) — no
  real DB locally by design (`docs/SETUP.md` explains why: this proves workflow correctness,
  not concurrency isolation, which needs a real deployment — see SETUP.md Part 2b).
