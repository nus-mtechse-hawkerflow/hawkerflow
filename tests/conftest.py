import os

import pytest

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-southeast-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("TABLE_NAME", "hawkerflow-test")
os.environ.setdefault("NOTIF_QUEUE_URL", "http://queue/notif")
os.environ.setdefault("ANALYTICS_QUEUE_URL", "http://queue/analytics")
os.environ.setdefault("ORDER_TTL_DAYS", "90")


@pytest.fixture()
def table():
    """A moto-mocked DynamoDB table matching infra/template.yaml exactly."""
    import boto3
    from moto import mock_aws

    with mock_aws():
        ddb = boto3.resource("dynamodb")
        t = ddb.create_table(
            TableName=os.environ["TABLE_NAME"],
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": n, "AttributeType": "S"}
                for n in ("PK", "SK", "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK")
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "GSI2",
                    "KeySchema": [
                        {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI2SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
        )
        yield t


STALL = {
    "stallId": "stall-1", "name": "Ah Hock Chicken Rice", "centreId": "maxwell",
    "status": "OPEN", "ownerSub": "owner-sub",
}

MENU = [
    {"itemId": "cr", "name": "Chicken rice", "priceCents": 450, "available": True},
    {"itemId": "laksa", "name": "Laksa", "priceCents": 600, "available": True},
    {"itemId": "teh", "name": "Teh tarik", "priceCents": 140, "available": False},
]


@pytest.fixture()
def stall():
    return dict(STALL)


@pytest.fixture()
def menu():
    return [dict(m) for m in MENU]
