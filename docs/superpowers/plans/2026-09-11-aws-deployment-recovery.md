# AWS Deployment Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Make HawkerFlow reproducibly buildable, deployable, and verifiable from a clean environment while preserving asynchronous order ingestion.

**Architecture:** The existing SAM stack stays intact: API Gateway queues orders to SQS and \`OrderingFunction\` consumes them. Remove machine-generated files from Git, establish a Python 3.12 bootstrap path, add an SQS event contract test, then validate AWS credentials and a no-execute CloudFormation change set before deployment.

**Tech Stack:** Python 3.12, AWS SAM CLI, AWS CLI v2, CloudFormation, pytest, boto3/moto, GitHub Actions.

**Spec:** \`docs/SETUP.md\`, \`infra/template.yaml\`, and the 2026-09-11 deployment audit.

## Global Constraints

- Target Python is exactly 3.12, matching the Lambda runtime and CI.
- Region remains \`ap-southeast-1\`; stacks remain \`hawkerflow-dev\` and \`hawkerflow-prod\`.
- Do not deploy until \`aws sts get-caller-identity\` proves the intended account.
- Preserve asynchronous \`POST /v1/orders\`: acceptance precedes persistence.
- Do not commit \`.venv/\`, \`.aws-sam/\`, \`build.toml\`, credentials, or absolute machine paths.

---

## File Structure

- Modify \`.gitignore\`: ignore \`.venv/\` and \`build.toml\`.
- Delete from the Git index: root \`build.toml\` and tracked \`.venv/\`.
- Create \`scripts/bootstrap.ps1\`: create a clean Python 3.12 virtual environment and install dev tools.
- Modify \`Makefile\`, \`README.md\`, and \`docs/SETUP.md\`: use/configure an explicit Python executable and publish a tested Windows preflight.
- Create \`tests/test_ordering_sqs_handler.py\`: prove the exact queue event shape the order Lambda consumes.
- Modify \`infra/template.yaml\` only after an AWS no-execute change set identifies a concrete CloudFormation error.

### Task 1: Remove generated and non-portable files

**Files:**

- Modify: \`.gitignore\`
- Delete from Git index: \`build.toml\`, \`.venv/\`

**Interfaces:**

- Produces: a clean checkout whose setup is not inherited from another developer's computer.

- [ ] **Step 1: Verify the files are tracked and machine-specific**

Run: \`git ls-files build.toml .venv | Measure-Object; Get-Content build.toml -TotalCount 12\`

Expected: root \`build.toml\` is tracked, \`.venv\` has thousands of tracked files, and the TOML contains a foreign absolute path.

- [ ] **Step 2: Add ignore rules**

Add these exact lines to \`.gitignore\`:

\`\`\`gitignore
.venv/
build.toml
\`\`\`

- [ ] **Step 3: Remove only generated files from Git**

Run:

\`\`\`powershell
git rm --cached build.toml
git rm -r --cached .venv
git ls-files build.toml .venv
\`\`\`

Expected: Git stages removal but leaves local files in place; the final command has no output.

- [ ] **Step 4: Commit**

\`\`\`bash
git add .gitignore
git commit -m "chore: stop tracking local Python and SAM build artifacts"
\`\`\`

### Task 2: Make local setup portable

**Files:**

- Create: \`scripts/bootstrap.ps1\`
- Modify: \`Makefile\`, \`docs/SETUP.md\`
- Test: \`tests/test_bootstrap_contract.py\`

**Interfaces:**

- Consumes: Python Launcher with Python 3.12 and \`requirements-dev.txt\`.
- Produces: \`.venv\\Scripts\\python.exe\`, usable by the documented checks.

- [ ] **Step 1: Write the failing contract test**

Create \`tests/test_bootstrap_contract.py\`:

\`\`\`python
from pathlib import Path


def test_windows_bootstrap_requires_python_312_and_requirements_file():
    script = Path("scripts/bootstrap.ps1").read_text(encoding="utf-8")
    assert "py -3.12" in script
    assert ".venv" in script
    assert "requirements-dev.txt" in script
\`\`\`

- [ ] **Step 2: Verify it fails**

Run: \`.venv\\Scripts\\python.exe -m pytest tests/test_bootstrap_contract.py -q\`

Expected: FAIL because \`scripts/bootstrap.ps1\` is absent.

- [ ] **Step 3: Add the bootstrap script**

Create \`scripts/bootstrap.ps1\`:

\`\`\`powershell
$ErrorActionPreference = "Stop"
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python Launcher was not found. Install Python 3.12 and its launcher."
}
py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12)"
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m ruff check .
\`\`\`

- [ ] **Step 4: Make Python selection explicit**

At the top of \`Makefile\`, add:

\`\`\`make
PYTHON ?= python
\`\`\`

Replace each \`pip\` call with \`$(PYTHON) -m pip\` and each \`python scripts/...\` call with \`$(PYTHON) scripts/...\`.

- [ ] **Step 5: Add tested Windows instructions**

Add this preflight to \`docs/SETUP.md\` and \`README.md\`:

\`\`\`powershell
py -3.12 --version
.\scripts\bootstrap.ps1
sam validate -t infra/template.yaml --lint --region ap-southeast-1
sam build -t infra/template.yaml
aws sts get-caller-identity --region ap-southeast-1
\`\`\`

- [ ] **Step 6: Verify and commit**

Run: \`.venv\\Scripts\\python.exe -m pytest -q; .venv\\Scripts\\python.exe -m ruff check .\`

Expected: both pass.

\`\`\`bash
git add Makefile scripts/bootstrap.ps1 docs/SETUP.md README.md tests/test_bootstrap_contract.py
git commit -m "docs: add portable Python 3.12 bootstrap"
\`\`\`

### Task 3: Add the SQS order-ingestion contract test

**Files:**

- Create: \`tests/test_ordering_sqs_handler.py\`
- Modify: \`services/ordering/src/ordering_service/handler.py\` only if the new test proves a defect.

**Interfaces:**

- Consumes: an SQS record with \`body\`, \`messageId\`, \`messageAttributes.userSub.stringValue\`, and \`messageAttributes.idempotencyKey.stringValue\`.
- Produces: \`{"batchItemFailures": []}\` for valid messages or the record's \`messageId\` in \`batchItemFailures\` for malformed messages.

- [ ] **Step 1: Write the valid-message test**

\`\`\`python
import json

from ordering_service import handler


def _event(body, message_id="message-1"):
    return {"Records": [{"messageId": message_id, "body": json.dumps(body),
        "messageAttributes": {
            "userSub": {"stringValue": "diner-sub"},
            "idempotencyKey": {"stringValue": "key-1"},
        }}]}


def test_queue_message_creates_an_order(monkeypatch, stall, menu):
    monkeypatch.setattr(handler.repo, "get_stall_and_menu", lambda _: (stall, menu))
    created = []
    monkeypatch.setattr(handler.repo, "create_order", lambda order: created.append(order) or (order, True))

    result = handler.lambda_handler(
        _event({"stallId": "stall-1", "items": [{"itemId": "cr", "qty": 1}]}), None
    )

    assert result == {"batchItemFailures": []}
    assert created[0]["userSub"] == "diner-sub"
\`\`\`

- [ ] **Step 2: Write the malformed-message test**

\`\`\`python
def test_invalid_queue_message_is_reported_for_retry(monkeypatch):
    monkeypatch.setattr(handler.repo, "get_stall_and_menu", lambda _: (_ for _ in ()).throw(AssertionError()))

    result = handler.lambda_handler(
        {"Records": [{"messageId": "bad-1", "body": "not-json", "messageAttributes": {}}]}, None
    )

    assert result == {"batchItemFailures": [{"itemIdentifier": "bad-1"}]}
\`\`\`

- [ ] **Step 3: Run the focused test**

Run: \`.venv\\Scripts\\python.exe -m pytest tests/test_ordering_sqs_handler.py -q\`

Expected: PASS. If it fails, change only \`_process_queue\` to honor this event contract.

- [ ] **Step 4: Run all tests and commit**

\`\`\`bash
.venv\Scripts\python.exe -m pytest -q
git add tests/test_ordering_sqs_handler.py services/ordering/src/ordering_service/handler.py
git commit -m "test: cover SQS order ingestion contract"
\`\`\`

### Task 4: Validate AWS before deployment

**Files:**

- Modify: \`.github/workflows/ci.yml\`, \`README.md\`, and \`docs/SETUP.md\` only as required by the evidence.

**Interfaces:**

- Consumes: clean Python 3.12 tooling, SAM CLI, AWS CLI v2, and a role authorized for CloudFormation change sets.
- Produces: offline build evidence followed by an AWS-side validation that does not execute a stack update.

- [ ] **Step 1: Verify offline build**

Run:

\`\`\`powershell
sam validate -t infra/template.yaml --lint --region ap-southeast-1
sam build -t infra/template.yaml
\`\`\`

Expected: valid template and successful build.

- [ ] **Step 2: Verify AWS identity**

Run: \`aws sts get-caller-identity --region ap-southeast-1\`

Expected: intended team account and role/user ARN. Stop if the CLI is not found or identity is unexpected.

- [ ] **Step 3: Create—but do not execute—a dev change set**

Run:

\`\`\`powershell
sam deploy --config-file infra/samconfig.toml --config-env dev --no-execute-changeset --no-fail-on-empty-changeset
\`\`\`

Expected: a CloudFormation change set is created/validated with no stack update. Record the full AWS error if it fails; change \`infra/template.yaml\` only in response to that evidence.

- [ ] **Step 4: Keep the CI safety gates**

Ensure CI continues to run:

\`\`\`yaml
- run: pytest -q
- run: sam validate -t infra/template.yaml --lint --region ap-southeast-1
- run: sam build -t infra/template.yaml
\`\`\`

- [ ] **Step 5: Commit**

\`\`\`bash
git add .github/workflows/ci.yml README.md docs/SETUP.md
git commit -m "docs: add AWS deployment preflight"
\`\`\`

### Task 5: Deploy and prove the asynchronous flow

**Files:**

- Modify only after a concrete failure: \`infra/template.yaml\`, \`services/ordering/src/ordering_service/handler.py\`, \`scripts/integration_test.py\`, or the affected app.

**Interfaces:**

- Consumes: reviewed change set and dev credentials.
- Produces: a dev stack where an accepted order is consumed from SQS, visible to the stall owner, and completes notification and analytics processing.

- [ ] **Step 1: Deploy dev**

Run: \`sam deploy --config-file infra/samconfig.toml --config-env dev --no-fail-on-empty-changeset\`

Expected: \`Successfully created/updated stack - hawkerflow-dev\`.

- [ ] **Step 2: Seed and test dev**

\`\`\`powershell
.\.venv\Scripts\python.exe scripts/seed_data.py --stack hawkerflow-dev
.\.venv\Scripts\python.exe scripts/smoke.py --stack hawkerflow-dev
.\.venv\Scripts\python.exe scripts/integration_test.py --stack hawkerflow-dev
\`\`\`

Expected: smoke passes and integration reports queue acceptance, asynchronous creation, lifecycle transitions, notification, and analytics success.

- [ ] **Step 3: Triage with the failing component boundary**

For a 4xx/5xx on submission, inspect the API Gateway route/integration. For accepted-but-missing orders, inspect the order queue, its DLQ, and \`/aws/lambda/hawkerflow-dev-ordering\`. Capture the first error, add a focused test, then apply one fix.

- [ ] **Step 4: Commit only a verified repair**

\`\`\`bash
git add infra/template.yaml services/ordering/src/ordering_service/handler.py scripts/integration_test.py apps
git commit -m "fix: resolve verified dev deployment issue"
\`\`\`

## Self-Review

- Coverage: Tasks 1–2 resolve the observed non-portable checkout; Task 3 closes the untested SQS boundary; Tasks 4–5 establish cloud-side validation and full-flow evidence.
- Placeholder scan: no deferred-work markers or unspecified targets remain.
- Interface consistency: the test's SQS attribute names and response shape match \`_process_queue\` in the existing ordering handler.
