"""Tests for running the Flask web app through API Gateway events."""

import json
import os
from pathlib import Path

from lambda_web.main import lambda_handler

from app.paths import STATIC_DIR
from tests.lambda_web_event import DummyContext, make_http_event

PING_PATH = "/ping"
STATIC_PATH = "/static/planttracer.js"


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
