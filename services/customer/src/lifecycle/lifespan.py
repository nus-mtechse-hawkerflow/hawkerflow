from contextlib import asynccontextmanager
from pathlib import Path
import os

from fastapi import FastAPI
from sqlmodel import SQLModel

from configurations.app_config import AppConfig
from entities.customer import Customer
from entities.customer_loyalty import CustomerLoyalty
from repository.customer_repo import CustomerRepo
from session.db_session import DBSession
from user_service.user_service import UserService


@asynccontextmanager
async def startup(app: FastAPI):
    project_root = Path(__file__).resolve().parents[2]
    os.environ.setdefault("PROJECT_PATH", str(project_root))

    config = AppConfig()
    session = DBSession(config.datasource)
    SQLModel.metadata.create_all(session.engine)

    user_repo = CustomerRepo(session.engine)
    user_service = UserService(user_repo)

    app.state.config = config
    app.state.session = session
    app.state.user_service = user_service

    yield
