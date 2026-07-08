"""Tests for running the Flask web app through API Gateway events."""

import json
import os
from pathlib import Path

from lambda_web.main import lambda_handler

from app.constants import (
    STACK_PARAMETER_BASE_DOMAIN,
    STACK_PARAMETER_DYNAMODB_TABLE_PREFIX,
    STACK_PARAMETER_HOSTED_ZONE_ID,
    STACK_PARAMETER_IMAGE_BUCKET_NAME,
    STACK_PARAMETER_LOG_LEVEL,
    STACK_PARAMETER_MAILER_DRY_RUN,
    STACK_NAME,
    STACK_PARAMETERS,
)
from app.paths import STATIC_DIR
from tests.lambda_web_event import DummyContext, make_http_event

PING_PATH = "/ping"
STATIC_PATH = "/static/planttracer.js"


def test_lambda_web_ping():
    response = lambda_handler(make_http_event(PING_PATH), DummyContext())
    assert response["statusCode"] == 200
    assert response["headers"]["content-type"].startswith("application/json")
    body = json.loads(response["body"])
    assert body["message"] == "pong"
    assert body["status"] == "ok"
    assert body["app_version"]
    assert "path" in body
    assert STACK_NAME in body
    assert "time" in body
    assert set(body[STACK_PARAMETERS]) == {
        STACK_PARAMETER_BASE_DOMAIN,
        STACK_PARAMETER_DYNAMODB_TABLE_PREFIX,
        STACK_PARAMETER_HOSTED_ZONE_ID,
        STACK_PARAMETER_IMAGE_BUCKET_NAME,
        STACK_PARAMETER_LOG_LEVEL,
        STACK_PARAMETER_MAILER_DRY_RUN,
    }
    assert "WildcardCertificateArn" not in body[STACK_PARAMETERS]


def test_lambda_web_static_asset():
    response = lambda_handler(make_http_event(STATIC_PATH), DummyContext())
    assert response["statusCode"] == 200
    assert response["isBase64Encoded"] is False
    assert len(response["body"]) > 0

    if os.environ.get("COLLECT_JS_COVERAGE", "").lower() not in ("1", "true", "yes"):
        assert response["body"] == Path(STATIC_DIR, "planttracer.js").read_text()
