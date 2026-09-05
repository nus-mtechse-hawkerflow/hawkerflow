# Project Proposal — HawkerFlow

**Submission for SWE5001 Practice Module · due 3 Aug 2026**
*(Paste into the proposal template/Canvas as required; placeholders marked [like this].)*

## 1. Project Title
HawkerFlow — a serverless food-ordering platform that grows the hawker-centre ecosystem.

## 2. Project Sponsor
[Name, title, contact — or "Not company-sponsored"]

## 3. Project Members
[Member 1], [Member 2], [Member 3], [Member 4], [Member 5] — Team [Number]

## 4. Overview
Hawker stalls are cash-and-queue micro-businesses: diners queue 15–30 minutes at lunch,
stalls lose walk-away customers, and commercial delivery platforms' 25–30% commissions are
unviable at S$4–6 price points, so most stalls stay offline. HawkerFlow solves this with a
**shared, multi-tenant order-ahead platform** whose running cost per stall is cents:
diners order ahead and collect when ready; stalls get a digital channel and daily analytics
they have never had. The business problem is therefore two-sided: reduce peak-hour friction
for consumers while giving producers an affordable digital presence — and do it on a
platform that new centres join at marginal cost.

## 5. General Architecture
A reusable **platform core** (identity, merchant onboarding, catalog, ordering,
notification, analytics) exposes versioned REST APIs and publishes domain events; thin
applications consume them. Physically: static web apps on **S3 + CloudFront**; **Cognito**
JWTs verified at **API Gateway (HTTP API)**; one **Lambda** (Python 3.12) service per
bounded context; a **DynamoDB** single table (on-demand) whose **Streams** act as a
transactional outbox feeding **SQS** queues (with DLQs) consumed by notification and
analytics. All infrastructure is **AWS SAM**; deployment is **GitHub Actions** via OIDC.
Region: ap-southeast-1. (Architecture diagrams: report Figures 1–2.)

## 6. Scope of Work
**Platform components:**
- **Seed:** the [Centre Name] order-ahead application (diner web app).
- **Producers:** stall owners — self-onboarding, menu management, order queue (stall portal).
- **Consumers:** diners — browse, order with simulated payment, live status, history.
- **Platform core:** the six services above, multi-tenant by data partitioning, so future
  seeds (coffee shops, canteens, food courts) onboard as tenant data + configuration.

**Use cases in scope:** browse stalls/menus; place order (idempotent); stall
accept/reject/prepare/ready/collect lifecycle; diner cancel (pre-preparation); status
notifications; per-stall daily analytics; stall onboarding and menu CRUD.
**Out of scope:** real payment (simulated; PCI excluded), delivery logistics, native apps,
promotions/reviews, multi-region DR.

**How the implementation demonstrates each requirement:**
- **Scalability** — a workload model (≈40 RPS burst at seed scale) proven by stepped k6
  load tests (25/50/100 RPS) with Lambda auto-scaling evidence and a USL fit for headroom.
- **Cloud native** — exclusively managed services with elasticity built in; no servers
  or VPC to operate; multi-AZ availability inherited and composed per Module 5.
- **DevOps** — trunk-based Git, CI (lint, 35 unit/repo tests, gitleaks, pip-audit,
  sam validate), CD to dev with integration tests + OWASP ZAP gate, manual approval to
  prod, alarm-gated bake window; everything as code.
- **Platform engineering** — versioned /v1 APIs (OpenAPI), domain events as published
  contracts (e.g., OrderReady for future delivery partners), tenant-based multi-tenancy,
  per-stall analytics.

## 7. Effort Estimates (~50 man-days, 5 members × ~10 days)
| WBS task | Owner | Est. (md) |
|---|---|---|
| Proposal, requirements, solution architecture | All | 6 |
| AWS account, IaC baseline, CI/CD skeleton | [M1] | 5 |
| Identity & access (Cognito) + Merchant service | [M2] | 6 |
| Catalog service + stall portal | [M3] | 6 |
| Ordering service + event pipeline (Streams/SQS/DLQ) | [M4] | 7 |
| Diner web application | [M5] | 7 |
| Notification + Analytics + dashboard | [M2] | 4 |
| Load testing, security hardening, observability | [M1] | 4 |
| Report and presentation | All | 5 |

Fortnightly progress reports will be submitted per the module schedule
(docs/PROGRESS_REPORT_TEMPLATE.md).
