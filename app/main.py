from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.body_limits import RequestBodyLimitMiddleware
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.connections import router as connections_router
from app.api.v1.health import router as health_router
from app.api.v1.notes import router as notes_router
from app.api.v1.projects import router as projects_router
from app.api.v1.search import router as search_router
from app.api.v1.transcriptions import router as transcription_router
from app.core.config import get_settings
from app.core.security import validate_jwt_secret
from app.db.session import close_database, initialize_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    validate_jwt_secret(settings.fikrah_jwt_secret)
    database_url = settings.database_url
    if database_url:
        initialize_database(database_url)

    yield

    await close_database()


app = FastAPI(title="FIKRAH API", lifespan=lifespan)
app.add_middleware(
    RequestBodyLimitMiddleware, audio_upload_path=transcription_router.prefix
)
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(notes_router)
app.include_router(connections_router)
app.include_router(search_router)
app.include_router(transcription_router)
app.include_router(chat_router)
app.include_router(health_router)
