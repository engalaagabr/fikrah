from contextlib import asynccontextmanager
import os

from fastapi import FastAPI

from app.auth.routes import router as auth_router
from app.database import close_database, initialize_database
from app.projects.routes import router as projects_router
from app.notes.routes import router as notes_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        initialize_database(database_url)

    yield

    await close_database()


app = FastAPI(title="FIKRAH API", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(notes_router)


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    """Report that the API process is running."""
    return {"status": "ok"}
