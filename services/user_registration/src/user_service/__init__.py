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
        client.describe_table(TableName='users')
        return True

    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ResourceNotFoundException':
            return False
        raise


def create_table():
    client.create_table(
        AttributeDefinitions=[
            {
                'AttributeName': 'user_id',
                'AttributeType': 'S'
            }
        ],
        KeySchema=[
            {
                'AttributeName': 'user_id',
                'KeyType': 'HASH'
            }
        ],
        ProvisionedThroughput={
            'ReadCapacityUnits': 5,
            'WriteCapacityUnits': 5,
        },
        TableName='users',
    )

if not check_if_table_exist():
    create_table()
