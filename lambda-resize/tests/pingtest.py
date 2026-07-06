import json
import sys
import time
import logging
from unittest.mock import patch

import pytest

from resize_app.main import DEPLOYED_AT_ENV, api_ping, deploy_metadata, lambda_handler
from resize_app.src.app.constants import __version__


ENDPOINT = "/resize-api/v1/ping"


class DummyContext:
    def __init__(self):
        self.function_name = "test-ping"
        self.memory_limit_in_mb = 128
        self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-ping"
        self.aws_request_id = "test-request-id"


def make_http_event(method: str) -> dict:
    return {
        "version": "2.0",
        "routeKey": f"{method} {ENDPOINT}",
        "rawPath": ENDPOINT,
        "rawQueryString": "",
        "headers": {},
        "requestContext": {
            "stage": "$default",
            "http": {
                "method": method,
                "path": ENDPOINT,
                "sourceIp": "127.0.0.1",
            }
        },
        "isBase64Encoded": False,
    }


def parse_lambda_response(response: dict) -> dict:
    body = response.get("body", "{}")
    if isinstance(body, str):
        return json.loads(body)
    return body


def test_ping_status_code():
    response = lambda_handler(make_http_event("GET"), DummyContext())
    assert response["statusCode"] == 200


def test_ping_response_shape():
    data = api_ping()
    assert set(data.keys()) == {"error", "status", "time", "path", "app_version", "deployed_at"}


def test_ping_error_is_false():
    assert api_ping()["error"] is False


def test_ping_status_is_ok():
    assert api_ping()["status"] == "ok"


def test_ping_time_is_recent():
    before = time.time()
    t = api_ping()["time"]
    after = time.time()
    assert isinstance(t, float)
    assert before <= t <= after + 5


def test_ping_path_matches_sys_path():
    assert api_ping()["path"] == sys.path


def test_ping_app_version_matches_application_version():
    assert api_ping()["app_version"] == __version__


def test_ping_deployed_at_defaults_to_unknown(monkeypatch):
    monkeypatch.delenv(DEPLOYED_AT_ENV, raising=False)
    assert api_ping()["deployed_at"] == "unknown"


def test_ping_deployed_at_can_come_from_environment(monkeypatch):
    deployed_at = "2026-07-04T22:50:00Z"
    monkeypatch.setenv(DEPLOYED_AT_ENV, deployed_at)
    assert api_ping()["deployed_at"] == deployed_at


def test_deploy_metadata_reads_stamped_file(tmp_path, monkeypatch):
    monkeypatch.setenv(DEPLOYED_AT_ENV, "env-value")
    metadata_path = tmp_path / "deploy_metadata.json"
    metadata_path.write_text(
        '{"deployed_at": "2026-07-04T22:55:00Z", "app_version": "9.9.9"}',
        encoding="utf-8",
    )
    assert deploy_metadata(metadata_path) == {
        "app_version": "9.9.9",
        "deployed_at": "2026-07-04T22:55:00Z",
    }


def test_ping_content_type_is_json():
    response = lambda_handler(make_http_event("GET"), DummyContext())
    assert response["headers"]["Content-Type"] == "application/json"


def test_ping_logs_info(caplog):
    with caplog.at_level(logging.INFO):
        api_ping()
    assert any("ping" in record.message for record in caplog.records)


def test_ping_time_value_is_mocked():
    fake_time = 1_000_000.0
    with patch("time.time", return_value=fake_time):
        assert api_ping()["time"] == fake_time


def test_ping_path_value_is_mocked():
    fake_path = ["/fake/path"]
    with patch("sys.path", fake_path):
        assert api_ping()["path"] == fake_path


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_ping_wrong_http_methods(method):
    response = lambda_handler(make_http_event(method), DummyContext())
    assert response["statusCode"] != 200
    data = parse_lambda_response(response)
    assert data["error"]
