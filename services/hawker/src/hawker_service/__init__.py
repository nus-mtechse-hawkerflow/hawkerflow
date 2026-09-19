import boto3
from botocore.exceptions import ClientError


dynamodb = boto3.resource(
                "dynamodb",
                region_name="us-east-1",
                endpoint_url="http://localhost.localstack.cloud:4566",
                aws_access_key_id="test",
                aws_secret_access_key="test",
            )

client = boto3.client(
    "dynamodb",
    region_name="us-east-1",
    endpoint_url="http://localhost.localstack.cloud:4566",
    aws_access_key_id="test",
    aws_secret_access_key="test",
)


def check_if_table_exist():
    try:
        client.describe_table(TableName='hawker')
        return True

    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceNotFoundException':
            return False
        raise


def create_table():
    client.create_table(
        TableName="hawker",
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": n, "AttributeType": "S"} for n in
            ("PK", "SK", "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK")
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"}
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"}]
                ,
                "Projection": {"ProjectionType": "ALL"}
            },
            {
                "IndexName": "GSI2",
                "KeySchema": [
                    {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI2SK", "KeyType": "RANGE"}
                ],
                "Projection": {"ProjectionType": "ALL"}
            }
        ]
    )

if not check_if_table_exist():
    create_table()
