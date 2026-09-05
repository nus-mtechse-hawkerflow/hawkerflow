# Q&A Preparation & Glossary — own every line of this before 24 Oct

## The 60-second order-flow script (every member memorises this)
"The diner posts an order with an Idempotency-Key. API Gateway checks the Cognito JWT and
invokes the Ordering Lambda, which re-prices the cart against the server-side catalog and
does a **conditional put** keyed by a UUID derived from (user, idempotency-key) — a retry
returns the original order instead of a duplicate. DynamoDB **Streams** emits the committed
change; a dispatcher Lambda turns it into an OrderPlaced event on two SQS queues — that's
the **transactional outbox**: the order can't exist without its event. The notification
consumer updates the stall's queue view; the stall's PATCH carries the expected current
status as a condition, so concurrent transitions fail safely with a 409. On collection,
the analytics consumer folds the event into the stall's daily aggregate, deduped by a
marker item because SQS is **at-least-once**."

## Ownership map (fill in — every artefact needs a defender)
| Area | Owner | Backup |
|---|---|---|
| Infra/template.yaml, alarms, pipeline | [M1] | [M4] |
| Identity, Merchant, Analytics services | [M2] | [M3] |
| Catalog + stall portal | [M3] | [M5] |
| Ordering + dispatcher (state machine, outbox) | [M4] | [M1] |
| Diner app + load test + evidence | [M5] | [M2] |

## Likely Q&A (with the answers)

**Q1. Why uuid5 for the order ID instead of a random UUID?**
uuid5 is deterministic: hash(namespace, user+idempotency-key) always yields the same ID, so
a client retry maps to the *same* DynamoDB partition key and the conditional put
(`attribute_not_exists(PK)`) makes creation exactly-once from the client's perspective.

**Q2. Why publish events from DynamoDB Streams instead of the Ordering Lambda calling SQS?**
Dual-write problem: if the Lambda wrote the order *then* crashed before sending to SQS, the
event is lost forever. Streams publishes from the committed change log, so persistence and
publication can't diverge — the outbox pattern with zero extra infrastructure.

**Q3. SQS is at-least-once — how do you avoid double effects?**
Idempotent consumers: notifications are keyed by (order, status) so a redelivery overwrites
itself; analytics writes a conditional marker item per order before folding, so a replay
is a no-op. Order transitions are guarded by expected-status conditions.

**Q4. Why DynamoDB and not a relational database?**
Every access pattern was known up front (menu by stall, queue by stall+status, history by
user, aggregate by stall+date) — so key-based access buys single-digit-ms latency at any
scale, 25 GB always-free, and no VPC/NAT tax. The price is ad-hoc SQL, which we route to
stream-fed aggregates now and S3+Athena export later (AISS-04).

**Q5. Your availability target is 99.9% but the SLA math says 99.69% — explain.**
Exactly — series composition (M5) of CloudFront×APIGW×Lambda×DynamoDB×Cognito ≈ 99.69%.
That's why the target is *scoped*: the dominant read path is served from the CloudFront
edge and doesn't traverse the chain, and the write path holds an explicit 43-min/month
error budget backed by retries and DLQs. We caught our own claim with the course's formula.

**Q6. What stops a malicious client paying $0.01 for chicken rice?**
The server never trusts client prices: the Ordering domain re-reads the catalog and
recomputes totals; the client's price fields are ignored (tested in test_ordering_domain).

**Q7. How is this a *platform* and not just an app?**
Apps hold zero business rules; the core exposes versioned APIs and published event
contracts. A new centre onboards as tenant data + branding; a delivery partner subscribes
to OrderReady without any change to the core. Two apps already consume it identically.

**Q8. (only if asked) What does the platform cost to run?**
Nothing is provisioned per-hour — no NAT, ALB, EKS, RDS. Lambda/SQS/DynamoDB-storage sit
inside always-free tiers; the only real bill is API Gateway (~US$1/M requests) and cents of
DynamoDB on-demand requests.

**Q9. Why on-demand DynamoDB when 25 provisioned RCU/WCU is free forever?**
25 RCU throttles the 100 RPS load test. On-demand costs cents at seed volume and absorbs
the spike — we bought the demonstration with pocket change and documented the trade-off.

**Q10. Cold starts?**
Python 3.12 on arm64, 256 MB: ~200–400 ms occasionally on first invocation; irrelevant for
event consumers, acceptable for a food-ordering UX, and amortised away under load
(warm containers). Mitigation if ever needed: provisioned concurrency — rejected on cost.

**Q11. Why one AWS account and AdministratorAccess on the deploy role?**
Documented accepted risks for a 5-person course project: stage-separated stacks + tags give
logical isolation (AD-10); the deploy role's *trust policy* is pinned to our repo, and OIDC
means no long-lived keys exist. Production would use AWS Organizations + scoped policies.

**Q12. What happens if the notification consumer keeps failing?**
Three receives → message parks in the DLQ → CloudWatch alarm fires → visible in the bake
window. The order itself is unaffected — that's the point of decoupling the write path.

**Q13. How do you know it scales beyond 100 RPS?**
Soft quotas are the next ceiling (1,000 concurrent Lambdas, 10,000 RPS API Gateway) — a
quota raise, not a redesign. The USL fit from stepped runs estimates where contention
would bite; DynamoDB on-demand and SQS scale independently of us.

**Q14. Security testing beyond scans?**
Authz is unit-tested (owner checks, role gates, illegal-transition 409s), gitleaks +
pip-audit gate every merge, ZAP baseline runs against dev before promotion, and the risk
assessment (report §4.3) maps STRIDE scenarios to these controls.

**Q15. What would you do differently with more time?**
Real payments behind a Payment service consuming OrderPlaced; WebSocket push replacing
polling; multi-account setup; SonarQube quality gate; and canary deployments instead of a
bake window.

## Glossary (exam-ready)
| Term | Meaning here |
|---|---|
| AD / AISS | Architectural Decision / Architecturally Significant Issue (limitation with owner+plan) |
| At-least-once | SQS may deliver a message more than once → consumers must be idempotent |
| Conditional write | DynamoDB write that succeeds only if a condition holds (e.g. expected status) — optimistic concurrency |
| DLQ | Dead-letter queue: parking lot for messages that failed max retries; alarmed |
| GSI | Global Secondary Index — alternate key for query patterns (stall queue, user history) |
| Idempotency | Same request repeated ⇒ same effect once; via idempotency-key → deterministic ID → conditional put |
| IaC / SAM | Infrastructure as Code / AWS Serverless Application Model (CloudFormation dialect) |
| JWT | Signed token from Cognito; API Gateway verifies issuer/audience per request |
| M/M/c | Queueing model: Poisson arrivals, exponential service, c servers; R ≈ S/(1−ρᶜ) |
| OIDC (CI) | GitHub↔AWS federation issuing short-lived credentials; no stored keys |
| Outbox pattern | Publish events from the committed DB change stream to avoid dual-write loss |
| PITR | Point-in-time recovery — 35-day continuous DynamoDB backup |
| p95 | 95th-percentile latency — our SLO metric (targets: 300 ms reads / 500 ms orders) |
| Seed / Producer / Consumer | First app proving the platform / supply side (stalls) / demand side (diners) |
| Series availability | A = A₁×A₂×…: chain is weaker than its weakest link (M5) |
| STRIDE / DREAD | Threat taxonomy / qualitative risk scoring (likelihood × impact) |
| TTL | DynamoDB per-item expiry (orders 90 days, via SSM-configurable parameter) |
| USL | Universal Scalability Law — fits contention (σ) and crosstalk (κ) from stepped load tests |
