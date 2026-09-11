# HawkerFlow

Hawker centre food ordering **platform** — the working system behind the SWE5001 practice-module
report. Serverless, pay-per-request, all Python 3.12: idle cost is **$0**, and the lunch-hour spike
is absorbed by Lambda/DynamoDB autoscaling.

**Seed:** one hawker centre's order-ahead app · **Producers:** stall owners (portal) · **Consumers:** diners (web app)

## Architecture (one paragraph)

Static web apps on **S3 + CloudFront** → **Cognito** issues JWTs → **API Gateway (HTTP API)**
validates them and routes to per-service **Lambda** functions → **DynamoDB** single table
(on-demand) is the store → **DynamoDB Streams** feed a dispatcher that publishes domain events to
**SQS** queues (with DLQs) consumed by the notification and analytics functions. Everything is
defined in **AWS SAM** and deployed by **GitHub Actions** via OIDC. Full rationale and trade-offs:
see the project report (AD-01 … AD-10).

## Repository layout

| Path | What lives here |
|---|---|
| `infra/template.yaml` | The entire stack (table, queues, Cognito, API, 6 functions, CloudFront) |
| `services/<name>/src/` | One Lambda service each: `handler.py` (transport) / `domain.py` (pure logic) / `repo.py` (data access) |
| `services/shared/` | Lambda layer with the small shared HTTP helper library |
| `apps/diner`, `apps/stall` | Single-file web apps (static, no build step) |
| `tests/` | pytest: pure domain tests + repository tests against moto-mocked DynamoDB |
| `.github/workflows/` | `ci.yml` (lint, tests, pip-audit, gitleaks, sam validate) and `deploy.yml` (dev → approval → prod) |
| `loadtest/order_flow.js` | k6 model: 70 RPS browse + 30 RPS orders for 10 min |
| `scripts/` | `seed_data.py` (demo users, stalls, menus), `smoke.py` (post-deploy check) |
| `docs/openapi.yaml` | The platform API contract |

## Quickstart (from zero to running system)

> **Full walkthrough — start here if any step below is unfamiliar:** [docs/SETUP.md](docs/SETUP.md)
> covers AWS account creation, the OIDC pipeline, load-test evidence capture and troubleshooting.

Prerequisites: an AWS account (new accounts get **US$100–200 credits**), AWS CLI configured,
[SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html),
Python 3.12.

On Windows, run this preflight from PowerShell:

```powershell
py -3.12 --version
.\scripts\bootstrap.ps1
sam validate -t infra/template.yaml --lint --region ap-southeast-1
sam build -t infra/template.yaml
aws sts get-caller-identity --region ap-southeast-1
```

```bash
# 0. Guardrail FIRST - S$5 budget alarm (email-alert version: docs/SETUP.md Part 1)
aws budgets create-budget --account-id <ACCOUNT_ID> --budget \
  '{"BudgetName":"hawkerflow","BudgetLimit":{"Amount":"5","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}'

# 1. Install dev tooling, run the checks the pipeline runs
make install && make lint && make test

# 2. Deploy the dev stack (~3 min)
make deploy-dev

# 3. Seed demo users + two stalls with menus
make seed        # prints ApiUrl / ClientId and the demo logins

# 4. Wire the apps: paste ApiUrl + ClientId into the CONFIG block of
#    apps/diner/index.html and apps/stall/index.html, then either
#    open them locally...
python -m http.server 8000 --directory apps
#    ...or publish them behind CloudFront:
aws s3 sync apps/ s3://<WebBucketName from outputs>/

# 5. Verify
make smoke
```

Demo logins (created by the seed script): `diner@hawkerflow.demo` and `owner@hawkerflow.demo`,
password `HawkerDemo1!`.

## CI/CD setup (once per repo)

1. Create an IAM role for GitHub OIDC (trust `token.actions.githubusercontent.com`, condition on
   your `org/repo`) with permissions to deploy the stack. No access keys are ever stored.
2. In GitHub: add repo **variable** `AWS_DEPLOY_ROLE_ARN`, and create environments `dev` and
   `production` — add a **required reviewer** on `production` (this is the manual approval gate).
3. Push to `main`: CI runs lint/tests/scans → deploy to dev → smoke + **integration test**
   (full order lifecycle; requires the one-time `make seed` on dev) + **OWASP ZAP baseline** →
   wait for approval → deploy to prod → smoke test → **alarm-gated bake window**.

## Load test (the scalability demonstration)

```bash
# Get a diner IdToken (sign in via the app and copy it, or use scripts in README-notes)
k6 run loadtest/order_flow.js \
  -e API_URL=<ApiUrl> -e ID_TOKEN=<IdToken> -e STALL_ID=ahhock-cr -e ITEM_ID=cr
```

Watch Lambda `ConcurrentExecutions` and API latency in CloudWatch while it runs: scaling is
automatic, thresholds assert p95 ≤ 300 ms (reads) / 500 ms (orders), error rate < 1%.
A 10-minute run at 100 RPS costs roughly **US$3–5** (the only above-free-tier spend in the project).

## Cost guardrails (why this stays ~$0/month)

No always-on resources exist — no NAT gateway, no load balancer, no Kubernetes, no RDS.
Lambda (1M req), DynamoDB (25 GB), SQS (1M req) sit inside AWS **always-free** monthly tiers;
CloudFront within the 1 TB free transfer tier. Log retention is pinned to **14 days in the
template**, and five CloudWatch alarms per stage (API 5xx, both DLQs, ordering and dispatcher
errors) deploy with the stack - within the 10 always-free alarms. Keep the S$5 budget alarm on.

## Tear down

```bash
sam delete --stack-name hawkerflow-dev --region ap-southeast-1
sam delete --stack-name hawkerflow-prod --region ap-southeast-1
```

(Empty the web bucket first if you synced the apps to it.)
