# Order Intake Boundary Design

## Problem

CloudFormation rejects the direct `AWS::ApiGatewayV2::Integration` for `SQS-SendMessage` because the template supplies nested `MessageAttributes.*` request parameters. The `POST /v1/orders` route therefore prevents the stack from deploying.

## Decision

Replace the direct API Gateway-to-SQS integration with `OrderIntakeFunction`. API Gateway continues to authenticate the Cognito JWT and invokes this function. The function reads the JWT subject and `idempotency-key` header, parses the order body, and sends one trusted JSON envelope to `OrderIngestionQueue`.

## Message contract

```json
{
  "userSub": "Cognito subject",
  "idempotencyKey": "HTTP idempotency-key header",
  "order": {"stallId": "stall-1", "items": [{"itemId": "cr", "qty": 1}]}
}
```

`OrderingFunction` reads this envelope from `record.body`; it no longer reads user identity or idempotency data from SQS message attributes.

## Behaviour and security

- A valid request returns HTTP `202` after SQS accepts the envelope.
- A missing or blank `idempotency-key`, invalid JSON, or non-object body returns the existing structured HTTP `400` response and sends no message.
- The user subject is always read from the validated JWT context, never from the client body.
- `OrderIntakeFunction` receives only `sqs:SendMessage` access to `OrderIngestionQueue`.
- The queue, `OrderingFunction`, DynamoDB stream dispatcher, notification queue, and analytics queue remain asynchronous and otherwise unchanged.

## Infrastructure

Delete the direct-integration role, authorizer, integration, and route resources. Add a SAM `HttpApi` event for `POST /v1/orders` on `OrderIntakeFunction`; the API default Cognito authorizer applies. Configure `ORDER_INGESTION_QUEUE_URL` with `!Ref OrderIngestionQueue`.

## Verification

Tests prove intake publishes the exact envelope and returns 202, rejects a missing idempotency key without publishing, and that the queue consumer accepts the new body-only envelope. Then run the full pytest suite, Ruff, `sam validate --lint`, and `sam build`.
