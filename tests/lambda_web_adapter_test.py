"""Lambda-web adapter tests that use the normal local-service fixtures."""

import json
from urllib.parse import urlencode

from lambda_web.main import lambda_handler

from app import apikey
from app.constants import STACK_NAME, __version__, stack_name
from app.odb import API_KEY
from tests.lambda_web_event import DummyContext, make_http_event


def test_lambda_web_version_route():
    response = lambda_handler(make_http_event("/ver"), DummyContext())
    assert response["statusCode"] == 200
    assert __version__ in response["body"]


def test_lambda_web_api_version_route():
    response = lambda_handler(make_http_event("/api/ver"), DummyContext())
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["__version__"] == __version__
    assert body[STACK_NAME] == stack_name()


def test_lambda_web_api_version_route_strips_http_api_stage_prefix():
    response = lambda_handler(make_http_event("/prod/api/ver", stage="prod"), DummyContext())
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["__version__"] == __version__


def test_lambda_web_api_version_route_keeps_custom_domain_path_with_named_stage():
    response = lambda_handler(make_http_event("/api/ver", stage="prod"), DummyContext())
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["__version__"] == __version__


def test_lambda_web_root_route_strips_http_api_stage_prefix(local_ddb, local_s3):
    response = lambda_handler(make_http_event("/prod", stage="prod"), DummyContext())
    assert response["statusCode"] == 200
    assert "Plant Tracer" in response["body"]


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
