"""Run the whole HawkerFlow backend locally - no AWS account, no Docker.

    python scripts/local_server.py          # then open http://localhost:8000

What it does:
  * starts an in-process mocked DynamoDB (moto) with the real table schema
  * seeds the demo stalls and menus
  * serves the real service handlers behind the same routes as API Gateway
  * fakes the Cognito JWT authorizer (sign in as the demo diner or stall owner)
  * runs the event pipeline synchronously after each order write, through the
    real dispatcher -> notification/analytics consumer code
  * serves the diner app and stall portal, pre-pointed at this server

Everything is in memory: restart the server and you are back to seed data.
This is for development and demos. The integration test
(scripts/integration_test.py) is what verifies real AWS behaviour.
"""
import copy
import json
import os
import sys
import threading
import time
from collections import Counter, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("PORT", "8000"))
TABLE = "hawkerflow-local"

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-southeast-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")
os.environ["TABLE_NAME"] = TABLE
os.environ["STAGE"] = "local"
os.environ["ORDER_TTL_DAYS"] = "90"          # avoids any SSM lookup
os.environ.pop("ORDER_TTL_PARAM", None)
os.environ.setdefault("NOTIF_QUEUE_URL", "local://notifications")
os.environ.setdefault("ANALYTICS_QUEUE_URL", "local://analytics")

for path in ("services/shared/python", "services/merchant/src", "services/catalog/src",
             "services/ordering/src", "services/dispatcher/src",
             "services/notification/src", "services/analytics/src", "scripts"):
    sys.path.insert(0, str(ROOT / path))

import boto3  # noqa: E402
from boto3.dynamodb.types import TypeSerializer  # noqa: E402
from moto import mock_aws  # noqa: E402

MOCK = mock_aws()
MOCK.start()

from analytics_service import handler as analytics  # noqa: E402
from catalog_service import handler as catalog  # noqa: E402
from dispatcher_service import handler as dispatcher  # noqa: E402
from merchant_service import handler as merchant  # noqa: E402
from notification_service import handler as notification  # noqa: E402
from ordering_service import handler as ordering  # noqa: E402
from ordering_service import repo as ordering_repo  # noqa: E402
from seed_data import STALLS  # noqa: E402

# Demo identities - stand in for Cognito-issued JWTs
USERS = {
    "local-diner": {"sub": "local-diner-sub", "email": "diner@hawkerflow.demo", "groups": []},
    "local-owner": {"sub": "local-owner-sub", "email": "owner@hawkerflow.demo",
                    "groups": ["stall-owner"]},
}
for _n in range(1, 5):
    USERS[f"local-customer{_n}"] = {
        "sub": f"local-customer{_n}-sub", "email": f"customer{_n}@hawkerflow.demo", "groups": [],
    }
OWNER_SUB = USERS["local-owner"]["sub"]

# Extra stall for local demo variety only - not part of the deployed seed data
# in scripts/seed_data.py, so `make seed` against a real stack is unaffected.
EXTRA_LOCAL_STALLS = [
    {
        "stallId": "guo-satay", "name": "Guo's Satay", "centreId": "maxwell",
        "status": "OPEN", "description": "Charcoal-grilled, peanut sauce made daily.",
        "menu": [
            {"itemId": "satay-chicken", "name": "Chicken satay (10 sticks)", "priceCents": 800,
             "available": True},
            {"itemId": "satay-mutton", "name": "Mutton satay (10 sticks)", "priceCents": 900,
             "available": True},
            {"itemId": "ketupat", "name": "Ketupat (4 pcs)", "priceCents": 200, "available": True},
        ],
    },
]

# (method, path template, routeKey, service, public?)
ROUTES = [
    ("GET", "/v1/centres/{centreId}/stalls", catalog, True),
    ("GET", "/v1/stalls/{stallId}", catalog, True),
    ("GET", "/v1/stalls/{stallId}/menu", catalog, True),
    ("PUT", "/v1/stalls/{stallId}/menu/{itemId}", catalog, False),
    ("POST", "/v1/stalls", merchant, False),
    ("GET", "/v1/me/stalls", merchant, False),
    ("PATCH", "/v1/stalls/{stallId}", merchant, False),
    ("POST", "/v1/orders", ordering, False),
    ("GET", "/v1/orders/{orderId}", ordering, False),
    ("GET", "/v1/me/orders", ordering, False),
    ("GET", "/v1/stalls/{stallId}/orders", ordering, False),
    ("PATCH", "/v1/orders/{orderId}", ordering, False),
    ("GET", "/v1/me/notifications", notification, False),
    ("GET", "/v1/stalls/{stallId}/analytics", analytics, False),
]

SERIALIZER = TypeSerializer()


def create_table():
    ddb = boto3.resource("dynamodb")
    ddb.create_table(
        TableName=TABLE,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"} for n in
                              ("PK", "SK", "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK")],
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"},
                   {"AttributeName": "SK", "KeyType": "RANGE"}],
        GlobalSecondaryIndexes=[
            {"IndexName": "GSI1",
             "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"},
                           {"AttributeName": "GSI1SK", "KeyType": "RANGE"}],
             "Projection": {"ProjectionType": "ALL"}},
            {"IndexName": "GSI2",
             "KeySchema": [{"AttributeName": "GSI2PK", "KeyType": "HASH"},
                           {"AttributeName": "GSI2SK", "KeyType": "RANGE"}],
             "Projection": {"ProjectionType": "ALL"}},
        ],
    )


def seed():
    table = boto3.resource("dynamodb").Table(TABLE)
    for raw in copy.deepcopy(STALLS) + copy.deepcopy(EXTRA_LOCAL_STALLS):
        menu = raw.pop("menu")
        table.put_item(Item={
            "PK": f"STALL#{raw['stallId']}", "SK": "PROFILE",
            "GSI1PK": f"CENTRE#{raw['centreId']}", "GSI1SK": f"STALL#{raw['stallId']}",
            "GSI2PK": f"OWNER#{OWNER_SUB}", "GSI2SK": f"STALL#{raw['stallId']}",
            "type": "STALL", "ownerSub": OWNER_SUB, **raw,
        })
        for item in menu:
            table.put_item(Item={"PK": f"STALL#{raw['stallId']}",
                                 "SK": f"ITEM#{item['itemId']}",
                                 "type": "MENU_ITEM", **item})
    print(f"seeded {len(STALLS) + len(EXTRA_LOCAL_STALLS)} stalls owned by "
          f"{USERS['local-owner']['email']}")


def match_route(method, path):
    """Return (service, routeKey, pathParameters) or (None, None, None)."""
    parts = [p for p in path.split("/") if p]
    for r_method, template, service, public in ROUTES:
        if r_method != method:
            continue
        t_parts = [p for p in template.split("/") if p]
        if len(t_parts) != len(parts):
            continue
        params, ok = {}, True
        for tp, ap in zip(t_parts, parts, strict=True):
            if tp.startswith("{") and tp.endswith("}"):
                params[tp[1:-1]] = ap
            elif tp != ap:
                ok = False
                break
        if ok:
            return service, f"{r_method} {template}", params, public
    return None, None, None, None


def to_image(order: dict) -> dict:
    """Serialise an order into the DynamoDB stream image shape."""
    item = {"PK": f"ORDER#{order['orderId']}", "SK": "META", **order}
    return {k: SERIALIZER.serialize(v) for k, v in item.items()}


# Fault-injection state, so the isolation demo can be rehearsed locally.
BROKEN = set()          # service names currently forced to fail
DLQ = {"notification": [], "analytics": []}
CONSUMERS = {"notification": notification, "analytics": analytics}
MAX_RECEIVE = 3         # mirrors the SQS redrive policy in infra/template.yaml

# Request metrics, for the /demo/ dashboard. Guarded by a lock since
# ThreadingHTTPServer handles requests concurrently.
SERVICE_NAMES = {
    catalog: "catalog", merchant: "merchant", ordering: "ordering",
    notification: "notification", analytics: "analytics",
}
METRICS_LOCK = threading.Lock()
STARTED_AT = time.time()
BUCKET_SECONDS = 60         # 1-minute resolution
BUCKET_HISTORY = 240        # 240 x 1min = 4 hours of history
METRICS = {
    "total": 0,
    "by_service": Counter(),
    "by_status": Counter(),
    "by_route": Counter(),
    "recent": deque(maxlen=30),   # newest first
    "buckets": {},                 # bucket index -> {"total": int, "ok": int, "err": int}
}


def record_request(method: str, path: str, service_name: str, status: int):
    with METRICS_LOCK:
        METRICS["total"] += 1
        METRICS["by_service"][service_name] += 1
        METRICS["by_status"][status] += 1
        METRICS["by_route"][f"{method} {path}"] += 1
        METRICS["recent"].appendleft({
            "t": round(time.time() - STARTED_AT, 1),
            "method": method, "path": path, "service": service_name, "status": status,
        })

        idx = int((time.time() - STARTED_AT) // BUCKET_SECONDS)
        bucket = METRICS["buckets"].setdefault(idx, {"total": 0, "ok": 0, "err": 0})
        bucket["total"] += 1
        bucket["ok" if status < 400 else "err"] += 1
        oldest_kept = idx - BUCKET_HISTORY
        for old_idx in [k for k in METRICS["buckets"] if k < oldest_kept]:
            del METRICS["buckets"][old_idx]


def timeseries_snapshot() -> list:
    """Requests-per-bucket for the last BUCKET_HISTORY buckets, zero-filled - so the
    dashboard's line chart has a continuous, evenly-spaced x-axis even through idle gaps."""
    with METRICS_LOCK:
        now_idx = int((time.time() - STARTED_AT) // BUCKET_SECONDS)
        buckets = dict(METRICS["buckets"])
    start_idx = now_idx - BUCKET_HISTORY + 1
    return [{
        "t": idx * BUCKET_SECONDS,
        "total": buckets.get(idx, {}).get("total", 0),
        "ok": buckets.get(idx, {}).get("ok", 0),
        "err": buckets.get(idx, {}).get("err", 0),
    } for idx in range(start_idx, now_idx + 1)]


def metrics_snapshot() -> dict:
    with METRICS_LOCK:
        return {
            "uptimeSeconds": round(time.time() - STARTED_AT, 1),
            "startedAtEpoch": STARTED_AT,   # Unix epoch (UTC) - frontend converts to SGT for display
            "totalRequests": METRICS["total"],
            "byService": dict(METRICS["by_service"]),
            "byStatus": {str(k): v for k, v in METRICS["by_status"].items()},
            "recent": list(METRICS["recent"]),
        }


def orders_summary() -> dict:
    """Current snapshot of all orders in the table: totals by status and by stall."""
    table = boto3.resource("dynamodb").Table(TABLE)
    resp = table.scan()
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items += resp.get("Items", [])

    by_status = Counter()
    by_stall = {}   # stallId -> {"name": ..., "total": n, "byStatus": {...}}
    for item in items:
        if item.get("SK") != "META" or not item.get("PK", "").startswith("ORDER#"):
            continue
        status = item.get("status", "UNKNOWN")
        by_status[status] += 1
        stall_id = item.get("stallId", "unknown")
        entry = by_stall.setdefault(stall_id, {
            "name": item.get("stallName", stall_id), "total": 0, "byStatus": Counter(),
        })
        entry["total"] += 1
        entry["byStatus"][status] += 1

    return {
        "byStatus": dict(by_status),
        "byStall": {k: {"name": v["name"], "total": v["total"], "byStatus": dict(v["byStatus"])}
                    for k, v in by_stall.items()},
    }


# Order lifecycle events (placed / status changes), newest first - the dashboard's
# "orders coming in" feed. Separate from the raw HTTP request log above.
ORDER_EVENTS = deque(maxlen=50)


def record_order_event(payload: dict, kind: str):
    with METRICS_LOCK:
        ORDER_EVENTS.appendleft({
            "t": round(time.time() - STARTED_AT, 1),
            "kind": kind,                                  # "placed" | "updated"
            "orderId": payload.get("orderId", "")[:8],
            "stallName": payload.get("stallName", "?"),
            "status": payload.get("status", "?"),
            "totalCents": payload.get("totalCents", 0),
            "items": ", ".join(f"{line['qty']}x {line['name']}" for line in payload.get("lines", [])),
        })


def deliver(service: str, event: dict):
    """One consumer delivery with retries, then park in the local dead-letter queue."""
    module = CONSUMERS[service]
    payload = {"Records": [{"body": json.dumps(event)}]}
    for attempt in range(1, MAX_RECEIVE + 1):
        try:
            if service in BROKEN:
                raise RuntimeError(f"{service} service is broken (fault injection)")
            module.lambda_handler(payload, None)
            return True
        except Exception as exc:  # noqa: BLE001 - mirrors SQS retry behaviour
            if attempt == MAX_RECEIVE:
                DLQ[service].append(event)
                print(f"    !! {service} failed {MAX_RECEIVE}x -> parked in DLQ "
                      f"(depth {len(DLQ[service])}): {exc}")
                return False
    return False


def run_pipeline(record: dict):
    """Real dispatcher -> real consumers, synchronously (stands in for Streams + SQS)."""
    event = dispatcher.to_event(record)
    if not event:
        return
    results = {name: deliver(name, event) for name in CONSUMERS}
    delivered = [n for n, okay in results.items() if okay]
    print(f"    pipeline -> {event['type']} ({event['orderId'][:8]}) "
          f"delivered to {delivered or 'nobody'}")


def redrive(service: str) -> int:
    """Re-deliver everything parked in a local DLQ (mirrors an SQS message-move task)."""
    parked, DLQ[service] = DLQ[service], []
    for event in parked:
        deliver(service, event)
    return len(parked)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # we print our own, quieter lines

    # ---------- helpers ----------
    def send_json(self, status, body, extra_headers=None):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("access-control-allow-origin", "*")
        self.send_header("content-length", str(len(raw)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def send_file(self, path: Path, ctype: str, rewrite=False):
        if not path.exists():
            return self.send_json(404, {"error": "not found"})
        data = path.read_bytes()
        if rewrite:
            text = data.decode()
            text = text.replace('"REPLACE_WITH_ApiUrl"', f'"http://localhost:{PORT}"')
            text = text.replace('"REPLACE_WITH_UserPoolClientId"', '"LOCAL"')
            data = text.encode()
        self.send_response(200)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def identity(self):
        raw = (self.headers.get("authorization") or "").replace("Bearer ", "").strip()
        return USERS.get(raw)

    # ---------- verbs ----------
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-headers", "*")
        self.send_header("access-control-allow-methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
        self.send_header("content-length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            return self.send_json(200, {
                "service": "HawkerFlow local",
                "demo_launcher": f"http://localhost:{PORT}/demo/",
                "diner_app": f"http://localhost:{PORT}/diner/",
                "stall_portal": f"http://localhost:{PORT}/stall/",
                "tokens": {"diner": "local-diner", "owner": "local-owner",
                           "customers": [f"local-customer{n}" for n in range(1, 5)]},
            })
        if parsed.path in ("/diner", "/diner/"):
            return self.send_file(ROOT / "apps/diner/index.html", "text/html", rewrite=True)
        if parsed.path in ("/stall", "/stall/"):
            return self.send_file(ROOT / "apps/stall/index.html", "text/html", rewrite=True)
        if parsed.path in ("/demo", "/demo/"):
            return self.send_file(ROOT / "apps/demo/index.html", "text/html")
        if parsed.path == "/_local/status":
            return self.send_json(200, {
                "broken": sorted(BROKEN),
                "dlq_depth": {k: len(v) for k, v in DLQ.items()},
            })
        if parsed.path == "/_local/metrics":
            snap = metrics_snapshot()
            snap["timeseries"] = timeseries_snapshot()
            snap["bucketSeconds"] = BUCKET_SECONDS
            summary = orders_summary()
            snap["ordersByStatus"] = summary["byStatus"]
            snap["ordersByStall"] = summary["byStall"]
            with METRICS_LOCK:
                snap["orderEvents"] = list(ORDER_EVENTS)
            snap["broken"] = sorted(BROKEN)
            snap["dlqDepth"] = {k: len(v) for k, v in DLQ.items()}
            return self.send_json(200, snap)
        return self.api("GET")

    def do_POST(self):
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        service = query.get("service", "notification")
        if parsed.path == "/_local/break":
            if service not in CONSUMERS:
                return self.send_json(400, {"error": f"unknown service {service}"})
            BROKEN.add(service)
            print(f"[fault]   {service} service BROKEN")
            return self.send_json(200, {"broken": sorted(BROKEN)})
        if parsed.path == "/_local/repair":
            BROKEN.discard(service)
            print(f"[fault]   {service} service repaired")
            return self.send_json(200, {"broken": sorted(BROKEN)})
        if parsed.path == "/_local/redrive":
            moved = redrive(service)
            print(f"[fault]   redrove {moved} message(s) for {service}")
            return self.send_json(200, {"redriven": moved,
                                        "dlq_depth": len(DLQ[service])})
        return self.api("POST")

    def do_PUT(self):
        return self.api("PUT")

    def do_PATCH(self):
        return self.api("PATCH")

    # ---------- API bridge ----------
    def api(self, method):
        parsed = urlparse(self.path)
        service, route_key, params, public = match_route(method, parsed.path)
        if service is None:
            return self.send_json(404, {"error": f"no route for {method} {parsed.path}"})

        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length).decode() if length else None

        user = self.identity()
        if not public and user is None:
            return self.send_json(401, {
                "error": "send header 'authorization: local-diner' or 'local-owner'"})

        claims = {}
        if user:
            claims = {"sub": user["sub"], "email": user["email"]}
            if user["groups"]:
                claims["cognito:groups"] = user["groups"]

        event = {
            "routeKey": route_key,
            "rawPath": parsed.path,
            "pathParameters": params,
            "queryStringParameters": {k: v[0] for k, v in parse_qs(parsed.query).items()},
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": body,
            "isBase64Encoded": False,
            "requestContext": {"authorizer": {"jwt": {"claims": claims}}},
        }

        # capture pre-state so a transition can produce a MODIFY record
        before = None
        if route_key == "PATCH /v1/orders/{orderId}":
            try:
                before = ordering_repo.get_order(params["orderId"])
            except Exception:
                before = None

        result = service.lambda_handler(event, None)
        status = result["statusCode"]
        payload = json.loads(result.get("body") or "{}")
        print(f"  {method} {parsed.path} -> {status}")
        record_request(method, parsed.path, SERVICE_NAMES.get(service, "unknown"), status)

        # simulate Streams -> dispatcher -> SQS -> consumers
        if route_key == "POST /v1/orders" and status == 201:
            record_order_event(payload, "placed")
            run_pipeline({"eventName": "INSERT", "dynamodb": {"NewImage": to_image(payload)}})
        elif route_key == "PATCH /v1/orders/{orderId}" and status == 200 and before:
            record_order_event(payload, "updated")
            run_pipeline({"eventName": "MODIFY", "dynamodb": {
                "OldImage": to_image(before), "NewImage": to_image(payload)}})

        return self.send_json(status, payload)


def main():
    create_table()
    seed()
    print(f"""
HawkerFlow running locally on http://localhost:{PORT}

  Demo launcher http://localhost:{PORT}/demo/    <- start here, one click per persona
  Diner app     http://localhost:{PORT}/diner/
  Stall portal  http://localhost:{PORT}/stall/

  API auth      send header 'authorization: local-diner'  (consumer)
                            'authorization: local-owner'  (producer)

  Fault demo    POST /_local/break?service=notification   then place an order
                GET  /_local/status                        broken services + DLQ depth
                POST /_local/repair?service=notification
                POST /_local/redrive?service=notification

  Dashboard     GET  /_local/metrics    request counts by service/status, order counts, DLQ depth

  In-memory only - restart resets to seed data. Ctrl-C to stop.
""")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()  # local dev server  # nosec B104


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        MOCK.stop()
