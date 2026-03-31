import sys
import time
from unittest.mock import patch
import logging

import pytest

from fastapi.testclient import TestClient

# Replace `your_app_module` with the actual module name where `app` is defined
from resize_app.main import app

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

ENDPOINT = "/resize-api/v1/ping"


# ── Happy path ────────────────────────────────────────────────────────────────

def test_ping_status_code():
    """Endpoint should return HTTP 200."""
    response = client.get(ENDPOINT)
    assert response.status_code == 200


def test_ping_response_shape():
    """Response JSON must contain all four expected keys."""
    response = client.get(ENDPOINT)
    data = response.json()
    assert set(data.keys()) == {"error", "status", "time", "path"}


def test_ping_error_is_false():
    """'error' field should always be False."""
    response = client.get(ENDPOINT)
    assert response.json()["error"] is False


def test_ping_status_is_ok():
    """'status' field should always be 'ok'."""
    response = client.get(ENDPOINT)
    assert response.json()["status"] == "ok"


def test_ping_time_is_recent():
    """'time' should be a Unix timestamp within 5 seconds of now."""
    before = time.time()
    response = client.get(ENDPOINT)
    after = time.time()
    t = response.json()["time"]
    assert isinstance(t, float)
    assert before <= t <= after + 5


def test_ping_path_matches_sys_path():
    """'path' should match sys.path at call time."""
    response = client.get(ENDPOINT)
    assert response.json()["path"] == sys.path


# ── Content-type ──────────────────────────────────────────────────────────────

def test_ping_content_type_is_json():
    """Response Content-Type should be application/json."""
    response = client.get(ENDPOINT)
    assert "application/json" in response.headers["content-type"]


# ── Logging ───────────────────────────────────────────────────────────────────

def test_ping_logs_info(caplog):
    """Endpoint should log 'ping' at INFO level."""
    with caplog.at_level(logging.INFO):
        client.get(ENDPOINT)
    assert any("ping" in record.message for record in caplog.records)


# ── Isolation / mocking ───────────────────────────────────────────────────────

def test_ping_time_value_is_mocked():
    """Demonstrate mocking time.time() for deterministic timestamp tests."""
    fake_time = 1_000_000.0
    with patch("time.time", return_value=fake_time):
        response = client.get(ENDPOINT)
    assert response.json()["time"] == fake_time


def test_ping_path_value_is_mocked():
    """Demonstrate mocking sys.path for deterministic path tests."""
    fake_path = ["/fake/path"]
    with patch("sys.path", fake_path):
        response = client.get(ENDPOINT)
    assert response.json()["path"] == fake_path


# ── Wrong methods ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_ping_wrong_http_methods(method):
    """Only GET should be accepted; other verbs should return 405."""
    response = getattr(client, method)(ENDPOINT)
    assert response.status_code == 405
