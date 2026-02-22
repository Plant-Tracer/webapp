"""
Configuration checks used to show a configuration error page when
S3 CORS or DynamoDB is misconfigured or unreachable.
"""

import logging
import os

from botocore.exceptions import ClientError

from .constants import C

logger = logging.getLogger(__name__)


def check_dynamodb():
    """
    Verify the app can reach DynamoDB (e.g. list/scan one item).
    Returns (True, "") if ok, (False, message) on failure.
    """
    try:
        from .odb import DDBO
        ddbo = DDBO()
        # Minimal read: scan users table with limit 1 (no auth needed)
        resp = ddbo.users.scan(Limit=1)
        _ = resp.get("Items", [])
        return (True, "")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        msg = e.response.get("Error", {}).get("Message", str(e))
        logger.warning("DynamoDB check failed: %s %s", code, msg)
        return (False, f"DynamoDB unreachable: {code} — {msg}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("DynamoDB check failed: %s", e)
        return (False, f"DynamoDB unreachable: {e}")


def check_s3_cors(app_origin: str):
    """
    Verify the S3 bucket has a CORS configuration that allows GET requests
    from the given origin (e.g. 'https://simson2.planttracer.com').
    Returns (True, "") if ok, (False, message) on failure.
    """
    bucket = os.environ.get(C.PLANTTRACER_S3_BUCKET)
    if not bucket or bucket.startswith("s3:"):
        return (False, "PLANTTRACER_S3_BUCKET is not set or invalid")

    try:
        from .s3_presigned import s3_client
        client = s3_client()
        cors = client.get_bucket_cors(Bucket=bucket)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        msg = e.response.get("Error", {}).get("Message", str(e))
        if code == "NoSuchCORSConfiguration":
            return (False, "S3 bucket has no CORS configuration. Run: python -m app.s3_presigned " + bucket)
        logger.warning("S3 CORS check failed: %s %s", code, msg)
        return (False, f"S3 CORS error: {code} — {msg}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("S3 CORS check failed: %s", e)
        return (False, f"S3 unreachable: {e}")

    rules = cors.get("CORSRules") or []
    origin_ok = False
    get_ok = False
    for rule in rules:
        origins = rule.get("AllowedOrigins") or []
        methods = rule.get("AllowedMethods") or []
        if "*" in origins or app_origin in origins:
            origin_ok = True
        if "GET" in methods:
            get_ok = True
        if origin_ok and get_ok:
            return (True, "")

    if not get_ok:
        return (False, "S3 CORS does not allow GET. Run: python -m app.s3_presigned " + bucket)
    if not origin_ok:
        return (False, f"S3 CORS does not allow origin {app_origin!r}. Run: python -m app.s3_presigned " + bucket)
    return (True, "")
