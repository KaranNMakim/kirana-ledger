from fastapi.testclient import TestClient

from app.api.main import create_app
from app.settings import Settings


def test_health_ok():
    client = TestClient(create_app(Settings(db_path=":memory:")))
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["llm_mode"] == "mock"
    assert body["today"] == "2025-11-30"


def test_ontology_endpoint_formats():
    client = TestClient(create_app(Settings(db_path=":memory:")))
    summary = client.get("/ontology").json()
    assert summary["counts"]["products"] >= 150
    assert "owes" in summary["relations"]
    assert client.get("/ontology?format=turtle").headers["content-type"].startswith("text/turtle")
    assert client.get("/ontology?format=jsonld").status_code == 200
    assert client.get("/ontology?format=xml").status_code == 422
