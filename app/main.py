from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth.routes import router as auth_router
from app.chat.routes import router as chat_router
from app.connections.routes import router as connections_router
from app.core.config import get_settings
from app.db.session import close_database, initialize_database
from app.notes.routes import router as notes_router
from app.projects.routes import router as projects_router
from app.search.routes import router as search_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = get_settings().database_url
    if database_url:
        initialize_database(database_url)

    yield

    await close_database()


app = FastAPI(title="FIKRAH API", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(notes_router)
app.include_router(connections_router)
app.include_router(search_router)
app.include_router(chat_router)


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    """Report that the API process is running."""
    return {"status": "ok"}
