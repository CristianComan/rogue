"""Unit tests for the M0 health-check endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from rogue.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "rogue-api"}
