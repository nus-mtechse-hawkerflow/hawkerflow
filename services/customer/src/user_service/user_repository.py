from botocore.exceptions import ClientError

from .user_exceptions import UserException
from .user_model import User
from . import dynamodb


class UserRepository:

    def __init__(self):
        self._table = dynamodb.Table('users')

    def create_if_absent(self, user: User):
        try:
            self._table.put_item(
                Item=user.model_dump(),
                ConditionExpression="attribute_not_exists(user_id)"
            )

            return {
                "customer": user.model_dump(),
                "created": True
            }

        except ClientError as exc:
            error_code = exc.response['Error']['Code']
            if error_code == 'ConditionalCheckFailedException':
                return {
                    "customer": user,
                    "created": False
                }

            raise UserException(400, "User creation failed")
