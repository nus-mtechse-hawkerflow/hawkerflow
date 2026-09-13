from pydantic import BaseModel

from .user_service import UserService


user_service = UserService()


def lambda_handler(event, context):

    attributes = event["request"]["userAttributes"]

    user_service.ensure_user_profile(
        cognito_sub=attributes["sub"],
        email=attributes["email"]
    )

    return event
