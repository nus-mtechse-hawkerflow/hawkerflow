from contextlib import asynccontextmanager
from pathlib import Path
import os

from fastapi import FastAPI
from sqlmodel import SQLModel

from configurations.app_config import AppConfig
from entities.customer_entity import Customer
from entities.customer_loyalty_points_entity import CustomerLoyaltyPoints
from session.db_session import DBSession


@asynccontextmanager
async def startup(app: FastAPI):
    project_root = Path(__file__).resolve().parents[2]
    os.environ.setdefault("PROJECT_PATH", str(project_root))

    config = AppConfig()
    session = DBSession(config.datasource)
    SQLModel.metadata.create_all(session.engine)

    app.state.config = config
    app.state.session = session

    yield
