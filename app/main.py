from contextlib import asynccontextmanager
import os

from fastapi import FastAPI

from app.database import close_database, initialize_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        initialize_database(database_url)

    yield

    await close_database()


app = FastAPI(title="FIKRAH API", lifespan=lifespan)


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    """Report that the API process is running."""
    return {"status": "ok"}
