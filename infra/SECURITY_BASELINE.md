# IaC Security Baseline — accepted findings

`checkov -f infra/template.yaml --framework cloudformation`
**36 passed · 34 failed** — every failure below is a deliberate, documented decision, not an oversight.

## False positives (control IS implemented)

| Check | Finding | Reality |
|---|---|---|
| CKV_AWS_27 ×4 | "SQS queue not encrypted" | All four queues set `SqsManagedSseEnabled: true` (SSE-SQS). Checkov only recognises `KmsMasterKeyId`, so it misses AWS-managed SQS encryption. Data **is** encrypted at rest. |

## Architectural decisions (rule does not apply to this design)

| Check | Finding | Decision |
|---|---|---|
| CKV_AWS_117 ×6 | "Lambda not in a VPC" | Deliberate (AD-04/AD-05). No VPC means no NAT gateway, no subnets and no network attack surface to defend. Data access is authorised by IAM rather than network position. |
| CKV_AWS_116 ×6 | "Lambda has no DLQ" | This rule means the *function-level* async DLQ. Four of six functions are synchronous (API-invoked) where it has no effect; the two asynchronous consumers already have **SQS queue-level DLQs with redrive policies and CloudWatch alarms**, which is the correct mechanism. |

## Cost-driven accepts (with adoption triggers)

| Check | Finding | Trigger to adopt |
|---|---|---|
| CKV_AWS_173 ×6 | Lambda env vars not encrypted with a customer-managed key | Env vars hold configuration, not secrets (secrets are in SSM SecureString). AWS-managed key encryption already applies. Adopt a CMK if regulated data is ever stored. |
| CKV_AWS_158 ×6 | Log groups not encrypted with a CMK | Encrypted by default with AWS-managed keys. A CMK costs ~US$1/key/month. Adopt when logs contain regulated data. |
| CKV_AWS_119 | DynamoDB not using a customer-managed CMK | Encrypted at rest with an AWS-owned key. Adopt a CMK when a compliance regime requires key custody. |
| CKV_AWS_68 | No WAF on CloudFront | Documented accepted risk (report §4.3). Adopt on public launch beyond the pilot. |
| CKV_AWS_18 / CKV_AWS_86 | No S3 / CloudFront access logging | Storage cost for a pilot with no audit requirement. CloudTrail covers control-plane audit. Adopt at public launch. |
| CKV_AWS_95 | No API Gateway access logging | As above; adopt alongside WAF. |

## Platform limitation

| Check | Finding | Explanation |
|---|---|---|
| CKV_AWS_174 | CloudFront viewer certificate not TLS 1.2+ | The distribution uses the default `*.cloudfront.net` certificate, for which CloudFront fixes the security policy and the field cannot be set. Raising it requires a custom domain plus an ACM certificate. |

> Because of this limitation, the report states TLS 1.2+ for the API path (API Gateway enforces
> it) rather than claiming it end-to-end across the CDN edge.
