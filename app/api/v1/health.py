"""Process health endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["operations"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Report that the API process is running."""
    return {"status": "ok"}
