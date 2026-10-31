"""Tests for health and auth."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_healthz_no_auth():
    app = create_app(Settings(api_token="secret"))
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_system_requires_token():
    app = create_app(Settings(api_token="secret"))
    client = TestClient(app)
    r = client.get("/api/system")
    assert r.status_code == 401


def test_system_wrong_token():
    app = create_app(Settings(api_token="secret"))
    client = TestClient(app)
    r = client.get("/api/system", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_system_correct_token():
    app = create_app(Settings(api_token="secret"))
    client = TestClient(app)
    r = client.get("/api/system", headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_system_no_token_configured_insecure():
    app = create_app(Settings(api_token="", allow_insecure=True))
    client = TestClient(app)
    r = client.get("/api/system")
    assert r.status_code == 200


def test_system_no_token_configured_secure():
    app = create_app(Settings(api_token="", allow_insecure=False))
    client = TestClient(app)
    r = client.get("/api/system")
    assert r.status_code == 503
