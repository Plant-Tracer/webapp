import json
import sys
import time
import logging
from unittest.mock import patch

import pytest

from resize_app.main import api_ping, lambda_handler


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
    assert set(data.keys()) == {"error", "status", "time", "path"}


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
