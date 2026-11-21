import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_rejects_public_jwt_placeholder(monkeypatch) -> None:
    monkeypatch.setenv(
        "FIKRAH_JWT_SECRET", "replace-with-a-random-secret-at-least-32-characters"
    )
    with pytest.raises(RuntimeError, match="public example"), TestClient(app):
        pass
