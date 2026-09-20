from contextlib import asynccontextmanager
from pathlib import Path
import os

from fastapi import FastAPI
from sqlmodel import SQLModel

from configurations.app_config import AppConfig
from session.db_session import DBSession
from entities.stall_menu import StallMenu
from entities.stall_owner import StallOwner
from entities.stalls import Stalls
from hawker_service.hawker_service import HawkerService
from repository.hawker_repository import HawkerRepository


@asynccontextmanager
async def startup(app: FastAPI):
    project_root = Path(__file__).resolve().parents[2]
    os.environ.setdefault("PROJECT_PATH", str(project_root))

    config = AppConfig()
    session = DBSession(config.datasource)
    SQLModel.metadata.create_all(session.engine)

    hawker_repo = HawkerRepository(session.engine)
    hawker_service = HawkerService(hawker_repo)

    app.state.config = config
    app.state.session = session
    app.state.hawker_service = hawker_service

    yield
