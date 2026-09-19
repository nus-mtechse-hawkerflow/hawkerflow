"""Seed demo users, stalls and menus into a deployed stack.

Usage: python scripts/seed_data.py --stack hawkerflow-dev
Creates:
  diner@hawkerflow.demo / HawkerDemo1!   (consumer)
  owner@hawkerflow.demo / HawkerDemo1!   (producer, group: stall-owner)
  2 stalls in centre 'maxwell' with menus
"""
import argparse

import boto3

PASSWORD = "HawkerDemo1!"  # demo-only credential, rotate for any real use  # noqa: S105

STALLS = [
    {
        "stallId": "ahhock-cr", "name": "Ah Hock Chicken Rice", "centreId": "maxwell",
        "status": "OPEN", "description": "Poached and roasted, since 1979.",
        "menu": [
            {"itemId": "cr", "name": "Chicken rice", "priceCents": 450, "available": True},
            {"itemId": "cr-set", "name": "Chicken rice set with soup", "priceCents": 650, "available": True},
            {"itemId": "extra", "name": "Extra chicken", "priceCents": 300, "available": True},
        ],
    },
    {
        "stallId": "mei-laksa", "name": "Mei's Laksa Corner", "centreId": "maxwell",
        "status": "OPEN", "description": "Rich gravy, real cockles.",
        "menu": [
            {"itemId": "laksa", "name": "Laksa", "priceCents": 550, "available": True},
            {"itemId": "laksa-l", "name": "Laksa (large)", "priceCents": 700, "available": True},
            {"itemId": "otah", "name": "Otah side", "priceCents": 200, "available": True},
        ],
    },
]


def stack_outputs(stack_name: str) -> dict:
    cfn = boto3.client("cloudformation")
    stack = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}


def ensure_user(idp, pool_id: str, email: str, group: str = None) -> str:
    try:
        idp.admin_create_user(
            UserPoolId=pool_id, Username=email, MessageAction="SUPPRESS",
            UserAttributes=[{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": "true"}],
        )
        print(f"created user {email}")
    except idp.exceptions.UsernameExistsException:
        print(f"user exists  {email}")
    idp.admin_set_user_password(UserPoolId=pool_id, Username=email, Password=PASSWORD, Permanent=True)
    if group:
        idp.admin_add_user_to_group(UserPoolId=pool_id, Username=email, GroupName=group)
    return idp.admin_get_user(UserPoolId=pool_id, Username=email)["Username"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", required=True)
    args = parser.parse_args()

    outputs = stack_outputs(args.stack)
    idp = boto3.client("cognito-idp")
    table = boto3.resource("dynamodb").Table(outputs["TableName"])

    ensure_user(idp, outputs["UserPoolId"], "diner@hawkerflow.demo")
    owner_sub = ensure_user(idp, outputs["UserPoolId"], "owner@hawkerflow.demo", group="stall-owner")

    for stall in STALLS:
        menu = stall.pop("menu")
        table.put_item(Item={
            "PK": f"STALL#{stall['stallId']}", "SK": "PROFILE",
            "GSI1PK": f"CENTRE#{stall['centreId']}", "GSI1SK": f"STALL#{stall['stallId']}",
            "GSI2PK": f"OWNER#{owner_sub}", "GSI2SK": f"STALL#{stall['stallId']}",
            "type": "STALL", "ownerSub": owner_sub, **stall,
        })
        for item in menu:
            table.put_item(Item={"PK": f"STALL#{stall['stallId']}", "SK": f"ITEM#{item['itemId']}",
                                 "type": "MENU_ITEM", **item})
        print(f"seeded stall {stall['name']} ({len(menu)} items)")

    print("\nApp config values (paste into apps/*/index.html CONFIG):")
    print(f"  API_URL   = {outputs['ApiUrl']}")
    print(f"  CLIENT_ID = {outputs['UserPoolClientId']}")
    print(f"  Web URL   = {outputs.get('WebUrl', '(pending CloudFront)')}")
    print(f"  Logins    = diner@hawkerflow.demo / owner@hawkerflow.demo  ({PASSWORD})")


if __name__ == "__main__":
    main()
