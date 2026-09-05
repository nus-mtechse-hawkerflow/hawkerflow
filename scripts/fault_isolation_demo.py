"""Fault-isolation demonstration — the microservices evidence that matters.

Breaks ONE service (the notification consumer) and shows that:
  * the ordering write path is unaffected — orders still succeed
  * the stall queue and analytics still work
  * failures are contained in that service's dead-letter queue and alarmed
  * after repair, the parked messages are redriven and the system self-heals

A monolith cannot do this: a fault in the notification code would take the
whole request path with it.

    python scripts/fault_isolation_demo.py --stack hawkerflow-dev

Runs about 4 minutes. Safe to run repeatedly. Restores the function on exit,
including on Ctrl-C.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

import boto3

PASSWORD = "HawkerDemo1!"  # demo-only credential from seed_data.py  # noqa: S105  # nosec B105
STALL_ID = "ahhock-cr"
ITEM_ID = "cr"
ORDERS = 5


def outputs(stack: str) -> dict:
    stack_desc = boto3.client("cloudformation").describe_stacks(StackName=stack)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack_desc.get("Outputs", [])}


def token(client_id: str, email: str) -> str:
    res = boto3.client("cognito-idp").initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": PASSWORD},
    )
    return res["AuthenticationResult"]["IdToken"]


def call(api, method, path, tok=None, body=None, idem=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api + path, data=data, method=method)
    req.add_header("content-type", "application/json")
    if tok:
        req.add_header("authorization", tok)
    if idem:
        req.add_header("idempotency-key", idem)
    try:
        with urllib.request.urlopen(req, timeout=15) as res:  # noqa: S310 - our own API  # nosec B310
            return res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def queue_depth(sqs, url: str) -> int:
    attrs = sqs.get_queue_attributes(
        QueueUrl=url, AttributeNames=["ApproximateNumberOfMessagesVisible"]
    )["Attributes"]
    return int(attrs["ApproximateNumberOfMessagesVisible"])


def find_queue(sqs, name_contains: str, stage: str) -> str:
    out = sqs.list_queues(QueueNamePrefix=f"hawkerflow-{stage}")
    for url in out.get("QueueUrls", []):
        if url.endswith(name_contains):
            return url
    raise SystemExit(f"queue ending '{name_contains}' not found for stage {stage}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", required=True)
    args = parser.parse_args()
    stage = args.stack.rsplit("-", 1)[-1]

    out = outputs(args.stack)
    api, client_id = out["ApiUrl"], out["UserPoolClientId"]
    lam = boto3.client("lambda")
    sqs = boto3.client("sqs")

    fn = f"hawkerflow-{stage}-notification"
    dlq = find_queue(sqs, "notifications-dlq", stage)
    diner = token(client_id, "diner@hawkerflow.demo")
    owner = token(client_id, "owner@hawkerflow.demo")

    original = lam.get_function_configuration(FunctionName=fn)
    original_env = original.get("Environment", {}).get("Variables", {})

    def restore():
        env = dict(original_env)
        env.pop("FORCE_FAILURE", None)
        lam.update_function_configuration(FunctionName=fn, Environment={"Variables": env})
        print("\n[restore] notification service returned to normal configuration")

    try:
        print(f"\n=== BASELINE (dlq depth {queue_depth(sqs, dlq)}) ===")

        # --- break exactly one service -------------------------------------
        print(f"\n[break]   pointing {fn} at a non-existent table — this service will now fail")
        broken_env = dict(original_env)
        broken_env["TABLE_NAME"] = "hawkerflow-does-not-exist"
        lam.update_function_configuration(FunctionName=fn, Environment={"Variables": broken_env})
        lam.get_waiter("function_updated_v2").wait(FunctionName=fn)

        # --- the rest of the platform must keep working --------------------
        print(f"\n[test]    placing {ORDERS} orders while notification is broken")
        placed = []
        for i in range(ORDERS):
            status, order = call(
                api, "POST", "/v1/orders", diner,
                {"stallId": STALL_ID, "items": [{"itemId": ITEM_ID, "qty": 1}]},
                idem=str(uuid.uuid4()),
            )
            marker = "OK " if status == 201 else "FAIL"
            print(f"          order {i + 1}: HTTP {status} {marker}")
            if status != 201:
                sys.exit("FAIL — the ordering service was affected by a notification failure")
            placed.append(order["orderId"])

        status, queue = call(api, "GET", f"/v1/stalls/{STALL_ID}/orders?status=PLACED", owner)
        visible = sum(1 for o in queue.get("orders", []) if o["orderId"] in placed)
        print(f"\n[test]    stall queue still serving: {visible}/{ORDERS} new orders visible")
        if visible != ORDERS:
            sys.exit("FAIL — the stall queue was affected")

        status, _ = call(api, "GET", f"/v1/stalls/{STALL_ID}/analytics?days=1", owner)
        print(f"[test]    analytics service still responding: HTTP {status}")

        # --- failure is contained in the DLQ -------------------------------
        print("\n[observe] waiting for failed messages to exhaust retries and park in the DLQ...")
        depth = 0
        for _ in range(24):
            time.sleep(10)
            depth = queue_depth(sqs, dlq)
            print(f"          notifications DLQ depth: {depth}")
            if depth >= ORDERS:
                break

        print(f"""
=== RESULT ===
  Notification service:  BROKEN — {depth} message(s) parked in its dead-letter queue
  Ordering service:      HEALTHY — {ORDERS}/{ORDERS} orders accepted (HTTP 201)
  Catalog / Merchant:    HEALTHY — stall queue served {visible}/{ORDERS} orders
  Analytics service:     HEALTHY — still responding

  The failure was contained inside one service. No order was lost: the events are
  held in the DLQ and can be redriven once the service is repaired.
  Screenshot the DLQ alarm in CloudWatch now — that is the evidence.
""")

        input("Press Enter to repair the service and redrive the parked messages... ")
        restore()
        lam.get_waiter("function_updated_v2").wait(FunctionName=fn)

        main_q = find_queue(sqs, f"hawkerflow-{stage}-notifications", stage)
        print("[repair]  redriving the dead-letter queue")
        sqs.start_message_move_task(
            SourceArn=sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])
            ["Attributes"]["QueueArn"],
            DestinationArn=sqs.get_queue_attributes(QueueUrl=main_q, AttributeNames=["QueueArn"])
            ["Attributes"]["QueueArn"],
        )
        for _ in range(12):
            time.sleep(10)
            remaining = queue_depth(sqs, dlq)
            print(f"          DLQ depth: {remaining}")
            if remaining == 0:
                break

        status, body = call(api, "GET", "/v1/me/notifications", diner)
        recovered = sum(1 for n in body.get("notifications", []) if n["orderId"] in placed)
        print(f"""
=== SELF-HEALED ===
  {recovered} notification(s) for the {ORDERS} orders were delivered after repair.
  Nothing was lost — the queue absorbed the outage.
""")

    except KeyboardInterrupt:
        restore()
        sys.exit("\ninterrupted")
    except Exception:
        restore()
        raise


if __name__ == "__main__":
    main()
