"""Lambda-web adapter tests that use the normal local-service fixtures."""

import json
from urllib.parse import urlencode

from lambda_web.main import lambda_handler

from app import apikey
from app.constants import __version__
from app.odb import API_KEY


class DummyContext:
    function_name = "test-lambda-web"
    memory_limit_in_mb = 128
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-web"
    aws_request_id = "test-request-id"


def make_http_event(
    path: str,
    *,
    method: str = "GET",
    body: str = "",
    content_type: str | None = None,
    cookies: list[str] | None = None,
) -> dict:
    headers = {
        "host": "lambda-web.test",
        "x-forwarded-for": "127.0.0.1",
        "x-forwarded-port": "443",
        "x-forwarded-proto": "https",
    }
    if content_type:
        headers["content-type"] = content_type
    event = {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": headers,
        "requestContext": {
            "stage": "$default",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
            },
        },
        "body": body,
        "isBase64Encoded": False,
    }
    if cookies:
        event["cookies"] = cookies
    return event


def test_lambda_web_version_route():
    response = lambda_handler(make_http_event("/ver"), DummyContext())
    assert response["statusCode"] == 200
    assert __version__ in response["body"]


def test_lambda_web_api_version_route():
    response = lambda_handler(make_http_event("/api/ver"), DummyContext())
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["__version__"] == __version__


def test_lambda_web_public_page(local_ddb, local_s3):
    response = lambda_handler(make_http_event("/about"), DummyContext())
    assert response["statusCode"] == 200
    assert "Plant Tracer About" in response["body"]


def test_lambda_web_authenticated_page(new_course):
    cookie = f"{apikey.cookie_name()}={new_course[API_KEY]}"
    response = lambda_handler(make_http_event("/list", cookies=[cookie]), DummyContext())
    assert response["statusCode"] == 200
    assert "Plant Tracer List Movies" in response["body"]


def test_lambda_web_flask_api_with_form_auth(new_course):
    body = urlencode({"api_key": new_course[API_KEY]})
    response = lambda_handler(
        make_http_event(
            "/api/check-api_key",
            method="POST",
            body=body,
            content_type="application/x-www-form-urlencoded",
        ),
        DummyContext(),
    )
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["error"] is False
