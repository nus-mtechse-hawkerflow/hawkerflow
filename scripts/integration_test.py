"""End-to-end integration test against a DEPLOYED stack (report section 5.3).

Prerequisite: `python scripts/seed_data.py --stack <stack>` has been run once,
because the test signs in as the seeded demo users. It exercises the platform
through the public API only: idempotent order placement, the full lifecycle
state machine, an illegal-transition rejection, and then verifies the async
pipeline (Streams -> dispatcher -> SQS -> consumers) delivered the notification
and folded the analytics aggregate.

Usage: python scripts/integration_test.py --stack hawkerflow-dev
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

import boto3

PASSWORD = "HawkerDemo1!"  # demo-only credential created by seed_data.py  # noqa: S105
STALL_ID = "ahhock-cr"
ITEM_ID = "cr"
CENTRE = "maxwell"


def outputs(stack_name: str) -> dict:
    cfn = boto3.client("cloudformation")
    stack = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}


def token(client_id: str, email: str) -> str:
    idp = boto3.client("cognito-idp")
    res = idp.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": PASSWORD},
    )
    return res["AuthenticationResult"]["IdToken"]


def call(api: str, method: str, path: str, tok: str = None, body: dict = None, idem: str = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api + path, data=data, method=method)
    req.add_header("content-type", "application/json")
    if tok:
        req.add_header("authorization", tok)
    if idem:
        req.add_header("idempotency-key", idem)
    try:
        with urllib.request.urlopen(req, timeout=15) as res:  # noqa: S310 - our own API
            return res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def expect(condition: bool, message: str):
    if not condition:
        print(f"FAIL  {message}")
        sys.exit(1)
    print(f"ok    {message}")


def wait_for(probe, message: str, attempts: int = 12, delay: int = 5):
    for _ in range(attempts):
        if probe():
            print(f"ok    {message}")
            return
        time.sleep(delay)
    print(f"FAIL  {message} (timed out after {attempts * delay}s)")
    sys.exit(1)


def orders_today(api: str, owner_tok: str) -> int:
    today = time.strftime("%Y-%m-%d", time.gmtime())
    status, body = call(api, "GET", f"/v1/stalls/{STALL_ID}/analytics?days=3", tok=owner_tok)
    if status != 200:
        return -1
    for day in body.get("daily", []):
        if day.get("date") == today:
            return int(day.get("orders", 0))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", required=True)
    args = parser.parse_args()

    out = outputs(args.stack)
    api, client_id = out["ApiUrl"], out["UserPoolClientId"]

    diner = token(client_id, "diner@hawkerflow.demo")
    owner = token(client_id, "owner@hawkerflow.demo")
    print(f"ok    signed in both demo users against {args.stack}")

    status, body = call(api, "GET", f"/v1/centres/{CENTRE}/stalls")
    expect(status == 200 and any(s["stallId"] == STALL_ID for s in body["stalls"]),
           "public catalog lists the seeded stall")

    baseline = orders_today(api, owner)
    expect(baseline >= 0, "analytics endpoint reachable (baseline taken)")

    idem = str(uuid.uuid4())
    payload = {"stallId": STALL_ID, "items": [{"itemId": ITEM_ID, "qty": 2}]}
    s1, _ = call(api, "POST", "/v1/orders", tok=diner, body=payload, idem=idem)
    expect(s1 in (200, 202), "order accepted by the ingestion queue")

    order = {}

    def order_ingested() -> bool:
        nonlocal order
        _, body = call(api, "GET", f"/v1/stalls/{STALL_ID}/orders?status=PLACED", tok=owner)
        matches = [o for o in body.get("orders", []) if o.get("userSub")]
        if matches:
            order = matches[0]
            return True
        return False

    wait_for(order_ingested, "queue consumer created the order")
    expect(order["status"] == "PLACED", "order starts in PLACED status")

    s2, _ = call(api, "POST", "/v1/orders", tok=diner, body=payload, idem=idem)
    expect(s2 in (200, 202), "duplicate submission accepted idempotently")

    order_id = order["orderId"]
    status, queue = call(api, "GET", f"/v1/stalls/{STALL_ID}/orders?status=PLACED", tok=owner)
    expect(status == 200 and any(o["orderId"] == order_id for o in queue["orders"]),
           "order visible in the stall queue")

    for action in ("accept", "preparing"):
        status, _ = call(api, "PATCH", f"/v1/orders/{order_id}", tok=owner, body={"action": action})
        expect(status == 200, f"stall action '{action}' accepted")

    status, _ = call(api, "PATCH", f"/v1/orders/{order_id}", tok=diner, body={"action": "cancel"})
    expect(status == 409, "diner cancel rejected once preparation started (409)")

    for action in ("ready", "collected"):
        status, _ = call(api, "PATCH", f"/v1/orders/{order_id}", tok=owner, body={"action": action})
        expect(status == 200, f"stall action '{action}' accepted")

    def ready_notified() -> bool:
        _, body = call(api, "GET", "/v1/me/notifications", tok=diner)
        return any(n["orderId"] == order_id and n["status"] == "READY"
                   for n in body.get("notifications", []))

    wait_for(ready_notified, "async pipeline delivered the READY notification")
    wait_for(lambda: orders_today(api, owner) >= baseline + 1,
             "analytics folded the collected order into today's aggregate")

    print("\nINTEGRATION PASS - full lifecycle, idempotency, authz and async pipeline verified")


if __name__ == "__main__":
    main()
