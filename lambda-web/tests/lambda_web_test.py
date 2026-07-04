"""Tests for running the Flask web app through API Gateway events."""

import json
import os
from pathlib import Path

from lambda_web.main import lambda_handler

from app.paths import STATIC_DIR

PING_PATH = "/ping"
STATIC_PATH = "/static/planttracer.js"


class DummyContext:
    function_name = "test-lambda-web"
    memory_limit_in_mb = 128
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-web"
    aws_request_id = "test-request-id"


def make_http_event(path: str, method: str = "GET") -> dict:
    return {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {
            "host": "lambda-web.test",
            "x-forwarded-for": "127.0.0.1",
            "x-forwarded-port": "443",
            "x-forwarded-proto": "https",
        },
        "requestContext": {
            "stage": "$default",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
            },
        },
        "isBase64Encoded": False,
    }


def test_lambda_web_ping():
    response = lambda_handler(make_http_event(PING_PATH), DummyContext())
    assert response["statusCode"] == 200
    assert response["headers"]["content-type"].startswith("application/json")
    assert json.loads(response["body"]) == {"message": "pong", "status": "ok"}


def test_lambda_web_static_asset():
    response = lambda_handler(make_http_event(STATIC_PATH), DummyContext())
    assert response["statusCode"] == 200
    assert response["isBase64Encoded"] is False
    assert len(response["body"]) > 0

    if os.environ.get("COLLECT_JS_COVERAGE", "").lower() not in ("1", "true", "yes"):
        assert response["body"] == Path(STATIC_DIR, "planttracer.js").read_text()
