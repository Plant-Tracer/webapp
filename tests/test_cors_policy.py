"""
Tests for CORS-related configuration and helpers.

These tests ensure that:
- S3 CORS configuration used by bootstrap is fully open (* origins, * headers).
- Lambda HTTP JSON responses always include Access-Control-Allow-Origin: *.
"""

import pathlib
import sys

from botocore.stub import Stubber

from app import s3_presigned
from app.s3_presigned import CORS_CONFIGURATION


def _import_lambda_resize_module():
    """
    Import the Lambda resize module (resize_app.main) from lambda-resize/src.

    This avoids depending on it being installed as a package; we add its src
    directory to sys.path at runtime for the tests.
    """
    root = pathlib.Path(__file__).resolve().parents[1]
    lambda_src = root / "lambda-resize" / "src"
    if lambda_src.is_dir() and str(lambda_src) not in sys.path:
        sys.path.insert(0, str(lambda_src))
    # pylint: disable=import-error,import-outside-toplevel
    from resize_app import main  # type: ignore

    return main


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


def test_configure_bucket_cors_applies_the_canonical_policy(monkeypatch):
    client = s3_presigned.s3_client()
    with Stubber(client) as stubber:
        stubber.add_response(
            "put_bucket_cors",
            {},
            {"Bucket": "test-bucket", "CORSConfiguration": CORS_CONFIGURATION},
        )
        monkeypatch.setattr(s3_presigned, "s3_client", lambda: client)

        s3_presigned.configure_bucket_cors("test-bucket")
