// k6 load model for the capacity demonstration (report sections 4.1 and 6).
//
//   k6 run loadtest/order_flow.js \
//     -e API_URL=https://xxx.execute-api.ap-southeast-1.amazonaws.com/dev \
//     -e ID_TOKEN=<diner IdToken> -e STALL_ID=ahhock-cr -e ITEM_ID=cr
//
// 100 RPS total for 10 minutes: 70 RPS browsing (public reads), 30 RPS order placement.
import http from "k6/http";
import { check } from "k6";
import { uuidv4 } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

const BASE = __ENV.API_URL;
const TOKEN = __ENV.ID_TOKEN;
const STALL = __ENV.STALL_ID || "ahhock-cr";
const ITEM = __ENV.ITEM_ID || "cr";
const CENTRE = __ENV.CENTRE_ID || "maxwell";
const RATE = Number(__ENV.RATE || 100);           // total RPS, split 70/30 browse/order

export const options = {
  thresholds: {
    "http_req_duration{scenario:browse}": ["p(95)<300"],
    "http_req_duration{scenario:order}": ["p(95)<500"],
    http_req_failed: ["rate<0.01"],
  },
  scenarios: {
    browse: {
      executor: "constant-arrival-rate", exec: "browse",
      rate: Math.round(RATE * 0.7), timeUnit: "1s", duration: "10m",
      preAllocatedVUs: 60, maxVUs: 200,
    },
    order: {
      executor: "constant-arrival-rate", exec: "order",
      rate: Math.round(RATE * 0.3), timeUnit: "1s", duration: "10m",
      preAllocatedVUs: 40, maxVUs: 200,
    },
  },
};

export function browse() {
  const stalls = http.get(`${BASE}/v1/centres/${CENTRE}/stalls`, { tags: { scenario: "browse" } });
  const menu = http.get(`${BASE}/v1/stalls/${STALL}/menu`, { tags: { scenario: "browse" } });
  check(stalls, { "stalls 200": (r) => r.status === 200 });
  check(menu, { "menu 200": (r) => r.status === 200 });
}

export function order() {
  const res = http.post(
    `${BASE}/v1/orders`,
    JSON.stringify({ stallId: STALL, items: [{ itemId: ITEM, qty: 1 }] }),
    {
      headers: {
        "content-type": "application/json",
        authorization: TOKEN,
        "idempotency-key": uuidv4(),
      },
      tags: { scenario: "order" },
    },
  );
  check(res, { "order 201": (r) => r.status === 201 });
}
