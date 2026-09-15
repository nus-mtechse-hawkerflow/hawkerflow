from datetime import datetime, timezone

from .user_repository import UserRepository
from .user_model import User


class UserService:

    def __init__(self):
        self._repository = UserRepository()

    def ensure_user_profile(self, cognito_sub: str, email: str):

        user = User(
            user_id=cognito_sub,
            email=email.lower(),
            created_at=datetime.now(timezone.utc).isoformat()
        )
        self._repository.create_if_absent(user)

        return user
