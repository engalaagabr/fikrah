from fastapi import FastAPI


app = FastAPI(title="FIKRAH API")


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    """Report that the API process is running."""
    return {"status": "ok"}
