"""Local CORS for the Expo web build (another port on the same PC)."""

from fastapi.testclient import TestClient

from app.main import app


def test_local_web_origin_allowed() -> None:
    r = TestClient(app).options(
        "/v1/me",
        headers={
            "Origin": "http://192.168.1.20:8081",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-dev-user",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://192.168.1.20:8081"


def test_public_origin_not_allowed() -> None:
    r = TestClient(app).get("/healthz", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in r.headers
