"""Guard rail: reserved concurrency across ALL stages must fit the account pool.

Reserved concurrency is drawn from a single account-wide pool (default 1000), of which
AWS requires at least 100 to remain unreserved. dev and prod are deployed into the same
account, so their reservations must be checked together - CloudFormation only discovers
the conflict at deploy time, and only for the second stack.

Run: python scripts/check_concurrency_budget.py
"""
import re
import sys
from pathlib import Path

ACCOUNT_LIMIT = 1000
MIN_UNRESERVED = 100
TEMPLATE = Path(__file__).resolve().parent.parent / "infra" / "template.yaml"


def main() -> int:
    text = TEMPLATE.read_text()
    block = re.search(r"  StageConfig:\n(.*?)\nGlobals:", text, re.S)
    if not block:
        print("FAIL: StageConfig mapping not found")
        return 1

    stages, current = {}, None
    for line in block.group(1).splitlines():
        stripped = line.strip()
        if stripped.endswith(":") and not stripped.startswith("#"):
            current = stripped[:-1]
            stages[current] = {}
        elif current and ":" in stripped and not stripped.startswith("#"):
            key, _, value = stripped.partition(":")
            value = value.split("#")[0].strip()
            if value.isdigit():
                stages[current][key.strip()] = int(value)

    total, failed = 0, False
    for stage, values in stages.items():
        reserved = sum(v for k, v in values.items() if k.endswith("Concurrency") and "Max" not in k)
        total += reserved
        print(f"  {stage:5} reserved={reserved}")
        for svc in ("Notification", "Analytics"):
            res, mx = values.get(f"{svc}Concurrency"), values.get(f"{svc}MaxConcurrency")
            if res is None or mx is None:
                continue
            if not 2 <= mx <= res:
                print(f"    FAIL: {svc} MaximumConcurrency {mx} must be between 2 and "
                      f"its reserved concurrency {res}")
                failed = True

    unreserved = ACCOUNT_LIMIT - total
    print(f"  total reserved={total}  unreserved={unreserved}  (minimum {MIN_UNRESERVED})")
    if unreserved < MIN_UNRESERVED:
        print(f"FAIL: all stages together reserve {total}, leaving {unreserved} unreserved. "
              f"The second stack to deploy will be rejected.")
        failed = True

    print("FAIL" if failed else "PASS: concurrency budget fits the account")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
