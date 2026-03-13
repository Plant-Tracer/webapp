"""
Tests for CORS-related configuration and helpers.

These tests ensure that:
- S3 CORS configuration used by bootstrap is fully open (* origins, * headers).
- Lambda HTTP JSON responses always include Access-Control-Allow-Origin: *.
"""

import json
import pathlib
import sys

from app.s3_presigned import CORS_CONFIGURATION


def _import_lambda_resize_module():
    """
    Import the Lambda resize module (resize_app.resize) from lambda-resize/src.

    This avoids depending on it being installed as a package; we add its src
    directory to sys.path at runtime for the tests.
    """
    root = pathlib.Path(__file__).resolve().parents[1]
    lambda_src = root / "lambda-resize" / "src"
    if lambda_src.is_dir() and str(lambda_src) not in sys.path:
        sys.path.insert(0, str(lambda_src))
    # pylint: disable=import-error,import-outside-toplevel
    from resize_app import resize  # type: ignore

    return resize


def test_s3_cors_configuration_is_fully_open():
    """S3 CORS config should allow all origins, headers, and required methods."""
    rules = CORS_CONFIGURATION.get("CORSRules") or []
    assert rules, "CORS_CONFIGURATION must define at least one rule"
    rule = rules[0]
    assert "*" in (rule.get("AllowedOrigins") or []), "S3 CORS must allow all origins (*)"
    assert "*" in (rule.get("AllowedHeaders") or []), "S3 CORS must allow all headers (*)"
    methods = rule.get("AllowedMethods") or []
    for required in ("GET", "PUT", "POST", "DELETE"):
        assert required in methods, f"S3 CORS must allow {required}"


def test_lambda_resp_json_includes_cors_header():
    """Lambda resp_json() helper should always include Access-Control-Allow-Origin: *."""
    resize = _import_lambda_resize_module()
    resp = resize.resp_json(200, {"ok": True})
    headers = resp.get("headers") or {}
    assert headers.get("Access-Control-Allow-Origin") == "*"


def test_lambda_options_preflight_cors_headers():
    """OPTIONS /api/v1 should return permissive CORS headers."""
    resize = _import_lambda_resize_module()
    event = {
        "requestContext": {
            "http": {
                "method": "OPTIONS",
            }
        },
        "rawPath": "/api/v1",
        "body": "",
        "isBase64Encoded": False,
    }
    resp = resize.lambda_handler(event, context={})
    headers = resp.get("headers") or {}
    assert headers.get("Access-Control-Allow-Origin") == "*"
    # Methods and headers should be fully open for browser clients
    assert "GET" in headers.get("Access-Control-Allow-Methods", "")
    assert "POST" in headers.get("Access-Control-Allow-Methods", "")
    assert "OPTIONS" in headers.get("Access-Control-Allow-Methods", "")
    assert headers.get("Access-Control-Allow-Headers") in ("*", "Content-Type,*")


def test_lambda_rotate_and_zip_error_still_has_cors():
    """
    Even when rotate-and-zip fails (e.g. invalid movie_id), Lambda should
    still set Access-Control-Allow-Origin: * so the browser does not see a
    CORS error.
    """
    resize = _import_lambda_resize_module()
    payload = {"action": "rotate-and-zip", "movie_id": "invalid-id-for-test"}
    event = {
        "requestContext": {
            "http": {
                "method": "POST",
            }
        },
        "rawPath": "/api/v1",
        "body": json.dumps(payload),
        "isBase64Encoded": False,
    }
    resp = resize.lambda_handler(event, context={})
    headers = resp.get("headers") or {}
    assert headers.get("Access-Control-Allow-Origin") == "*"

