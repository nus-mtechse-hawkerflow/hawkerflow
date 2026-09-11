# Order Intake Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the invalid direct API Gateway-to-SQS order submission integration with a deployable authenticated Lambda intake boundary while preserving asynchronous processing.

**Architecture:** `OrderIntakeFunction` receives authenticated `POST /v1/orders` requests, publishes a trusted body-only SQS envelope, and returns 202. `OrderingFunction` consumes that envelope and persists orders asynchronously. The invalid direct API Gateway integration resources are removed.

**Tech Stack:** Python 3.12, AWS Lambda, AWS SAM, API Gateway HTTP API, SQS, pytest, boto3.

**Spec:** `docs/superpowers/specs/2026-09-11-order-intake-boundary.md`

## Global Constraints

- Region remains `ap-southeast-1`; stacks remain `hawkerflow-dev` and `hawkerflow-prod`.
- `POST /v1/orders` remains asynchronous and returns HTTP `202` only after SQS accepts the trusted envelope.
- Only validated JWT context supplies `userSub`; clients cannot supply it in the order body.
- `idempotency-key` is required and blank values are rejected with HTTP `400` before SQS is called.
- Do not deploy, seed data, push, merge, or modify the original checkout during this plan.
- Target Python is exactly 3.12; do not commit `.venv/`, `.aws-sam/`, `build.toml`, credentials, or absolute machine paths.

---

## File Structure

- Create `services/order_intake/src/order_intake_service/handler.py`: validates HTTP input and enqueues the trusted order envelope.
- Create `services/order_intake/src/order_intake_service/__init__.py`: package marker.
- Modify `services/ordering/src/ordering_service/handler.py`: consume the envelope from `record.body`.
- Modify `infra/template.yaml`: attach intake Lambda to API, grant one queue-send permission, and remove invalid integration resources.
- Modify `pyproject.toml`: add intake source root to pytest imports.
- Create `tests/test_order_intake_handler.py`: intake endpoint behaviour tests.
- Modify `tests/test_ordering_sqs_handler.py`: use the new body-only queue contract.

### Task 1: Implement and wire the trusted order intake boundary

**Files:**
- Create: `services/order_intake/src/order_intake_service/__init__.py`
- Create: `services/order_intake/src/order_intake_service/handler.py`
- Modify: `services/ordering/src/ordering_service/handler.py:40-57`
- Modify: `infra/template.yaml:177-231,326-379`
- Modify: `pyproject.toml:5-12`
- Create: `tests/test_order_intake_handler.py`
- Modify: `tests/test_ordering_sqs_handler.py`

**Interfaces:**
- Consumes: HTTP API Lambda event with `routeKey`, JWT claim `sub`, headers, and a JSON body.
- Produces: `lambda_handler(event, context) -> dict`. Valid messages call `sqs.send_message(QueueUrl=ORDER_INGESTION_QUEUE_URL, MessageBody=<envelope JSON>)` and return `resp(202, {"accepted": True})`.
- Produces: a queue body shaped as `{"userSub": str, "idempotencyKey": str, "order": dict}`; `OrderingFunction._process_queue` reads exactly those fields.

- [ ] **Step 1: Write the failing intake tests**

Create `tests/test_order_intake_handler.py`. The valid test monkeypatches `handler.sqs.send_message`, calls an event with JWT subject `diner-sub`, header `idempotency-key: key-1`, and order payload `{"stallId": "stall-1", "items": [{"itemId": "cr", "qty": 1}]}`. Assert status 202 and the exact serialized envelope. A second test sends blank `idempotency-key`, asserts status 400, and monkeypatches `send_message` to raise if called.

- [ ] **Step 2: Run the test to verify RED**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_order_intake_handler.py -q -p no:cacheprovider`

Expected: collection fails because `order_intake_service` does not exist.

- [ ] **Step 3: Write the minimal intake handler**

Create `order_intake_service.handler`. Import `ApiError`, `error`, `header`, `json_body`, `resp`, and `sub` from `shared.http`. For `POST /v1/orders`, reject a missing or blank `header(event, "idempotency-key").strip()` with `ApiError(400, "idempotency-key is required")`. Use `json.dumps` to send exactly `{"userSub": sub(event), "idempotencyKey": idempotency_key, "order": json_body(event)}`. Send through module-level `boto3.client("sqs")` to `os.environ["ORDER_INGESTION_QUEUE_URL"]`, then return `resp(202, {"accepted": True})`. Map `ApiError` and unexpected errors using the merchant handler pattern.

- [ ] **Step 4: Run the intake tests to verify GREEN**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_order_intake_handler.py -q -p no:cacheprovider`

Expected: 2 passed.

- [ ] **Step 5: Change the consumer test, then verify RED**

Update `tests/test_ordering_sqs_handler.py` so a valid SQS `record.body` is JSON for `{"userSub": "diner-sub", "idempotencyKey": "key-1", "order": {"stallId": "stall-1", "items": [{"itemId": "cr", "qty": 1}]}}` and the record has no `messageAttributes`. Retain the malformed raw-body test. Run `.venv\\Scripts\\python.exe -m pytest tests/test_ordering_sqs_handler.py -q -p no:cacheprovider`; the valid test must fail because the consumer still reads `messageAttributes`.

- [ ] **Step 6: Implement the body-only consumer contract and verify GREEN**

In `_process_queue`, parse the body first, then read `envelope["userSub"]`, `envelope["idempotencyKey"]`, and `envelope["order"]`. Pass the order's `stallId` and `items` into the existing repository/domain calls. Preserve existing per-record error and `batchItemFailures` behaviour. Run `.venv\\Scripts\\python.exe -m pytest tests/test_ordering_sqs_handler.py -q -p no:cacheprovider`; expect 2 passed.

- [ ] **Step 7: Replace the invalid API integration in SAM**

Remove `ApiGatewayOrderQueueRole`, `OrderApiAuthorizer`, `OrderQueueIntegration`, and `OrderQueueRoute`. Add `OrderIntakeFunction` before `OrderingFunction` with `CodeUri: ../services/order_intake/src`, `Handler: order_intake_service.handler.lambda_handler`, `ORDER_INGESTION_QUEUE_URL: !Ref OrderIngestionQueue`, SAM's `SQSSendMessagePolicy` scoped to the order queue, and a `HttpApi` event for `POST /v1/orders`. Add `services/order_intake/src` to `pyproject.toml` `pythonpath`. Do not add `Auth: NONE`; the API default Cognito authorizer protects this route.

- [ ] **Step 8: Verify, then commit**

Run each command and require exit code 0: `.venv\\Scripts\\python.exe -m pytest tests/test_order_intake_handler.py tests/test_ordering_sqs_handler.py -q -p no:cacheprovider`; `.venv\\Scripts\\python.exe -m pytest -q -p no:cacheprovider`; `.venv\\Scripts\\python.exe -m ruff check .`; `sam validate -t infra/template.yaml --lint --region ap-southeast-1`; and `sam build -t infra/template.yaml`.

Commit with `git add infra/template.yaml pyproject.toml services/order_intake services/ordering/src/ordering_service/handler.py tests/test_order_intake_handler.py tests/test_ordering_sqs_handler.py docs/superpowers/specs/2026-09-11-order-intake-boundary.md docs/superpowers/plans/2026-09-11-order-intake-boundary.md` followed by `git commit -m "fix: route order intake through Lambda"`.

## Self-Review

- Spec coverage: Task 1 creates the trusted Lambda envelope, validates the required key, removes the invalid integration, limits permissions to queue send, preserves SQS processing, and verifies the complete local deploy contract.
- Placeholder scan: no deferred implementation markers or unspecified interfaces remain.
- Type consistency: producer and consumer use exactly `userSub`, `idempotencyKey`, and `order`.
