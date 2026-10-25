from fastapi.testclient import TestClient

from app.api.main import create_app
from app.settings import Settings


def test_health_ok():
    client = TestClient(create_app(Settings(db_path=":memory:")))
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["llm_mode"] == "mock"
    assert body["today"] == "2025-11-30"
