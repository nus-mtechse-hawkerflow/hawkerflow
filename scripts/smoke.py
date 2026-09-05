"""Post-deploy smoke test: the public catalog endpoint must answer 200."""
import argparse
import json
import sys
import urllib.request

import boto3


def stack_outputs(stack_name: str) -> dict:
    cfn = boto3.client("cloudformation")
    stack = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", required=True)
    parser.add_argument("--centre", default="maxwell")
    args = parser.parse_args()

    api = stack_outputs(args.stack)["ApiUrl"]
    url = f"{api}/v1/centres/{args.centre}/stalls"
    with urllib.request.urlopen(url, timeout=10) as res:  # noqa: S310 - our own API URL  # nosec B310
        body = json.loads(res.read())
        assert res.status == 200, f"expected 200, got {res.status}"  # smoke test check  # nosec B101
        assert "stalls" in body, "response missing 'stalls'"  # smoke test check  # nosec B101
    print(f"SMOKE OK  {url}  ({len(body['stalls'])} stall(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
