"""
Configuration checks used to show a configuration error page when
S3 CORS, bucket region, or DynamoDB is misconfigured or unreachable.
"""

import logging
import os
import time

from botocore.exceptions import ClientError

from .constants import C
from .odb import DDBO
from .s3_presigned import s3_client

logger = logging.getLogger(__name__)

# Cache for upload readiness (region + CORS POST) to avoid repeated S3 API calls
_UPLOAD_READINESS_CACHE = {}
_UPLOAD_READINESS_TTL = 60  # seconds

def check_dynamodb():
    """
    Verify the app can reach DynamoDB (e.g. list/scan one item).
    Returns (True, "") if ok, (False, message) on failure.
    """
    try:
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


def _is_local_s3():
    """True if using local S3 (e.g. MinIO). MinIO does not implement CORS, so we skip the check."""
    if os.environ.get(C.AWS_REGION) == "local":
        return True
    endpoint = os.environ.get(C.AWS_ENDPOINT_URL_S3) or ""
    return "localhost" in endpoint or "127.0.0.1" in endpoint


def check_s3_bucket_region():
    """
    Verify the S3 bucket is in the same region as the app (AWS_REGION).
    Presigned URLs are region-specific; a mismatch causes connection reset on upload.
    Returns (True, "") if ok, (False, message) on failure.
    Skips when using local S3 (MinIO).
    """
    if _is_local_s3():
        return (True, "")

    bucket = os.environ.get(C.PLANTTRACER_S3_BUCKET)
    if not bucket or bucket.startswith("s3:"):
        return (True, "")  # Let CORS check report bucket missing

    app_region = (os.environ.get(C.AWS_REGION) or "").strip()
    if not app_region:
        return (True, "")  # Cannot validate; skip to avoid breaking dev

    try:
        loc = s3_client().get_bucket_location(Bucket=bucket)
        # us-east-1 returns None/empty LocationConstraint; other regions return the region name
        bucket_region = (loc.get("LocationConstraint") or "").strip() or "us-east-1"
        if bucket_region != app_region:
            return (
                False,
                f"S3 bucket {bucket} is in region {bucket_region!r} but app AWS_REGION is {app_region!r}. "
                "Set AWS_REGION to the bucket's region or use a bucket in this region.",
            )
        return (True, "")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        msg = e.response.get("Error", {}).get("Message", str(e))
        logger.warning("S3 bucket region check failed: %s %s", code, msg)
        return (False, f"S3 bucket region check failed: {code} — {msg}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("S3 bucket region check failed: %s", e)
        return (False, f"S3 unreachable: {e}")


def check_s3_cors(app_origin: str):
    """
    Verify the S3 bucket has a CORS configuration that allows GET and POST
    from the given origin (e.g. 'https://simson2.planttracer.com').
    Returns (True, "") if ok, (False, message) on failure.
    Skips the check when using local S3 (MinIO), which does not implement CORS.
    """
    if _is_local_s3():
        return (True, "")

    bucket = os.environ.get(C.PLANTTRACER_S3_BUCKET)
    if not bucket or bucket.startswith("s3:"):
        return (False, "PLANTTRACER_S3_BUCKET is not set or invalid")

    err_msg = None
    try:
        cors = s3_client().get_bucket_cors(Bucket=bucket)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        msg = e.response.get("Error", {}).get("Message", str(e))
        if code == "NoSuchCORSConfiguration":
            err_msg = "S3 bucket has no CORS configuration. Run: python -m app.s3_presigned " + bucket
        else:
            logger.warning("S3 CORS check failed: %s %s", code, msg)
            err_msg = f"S3 CORS error: {code} — {msg}"
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("S3 CORS check failed: %s", e)
        err_msg = f"S3 unreachable: {e}"

    if err_msg is not None:
        return (False, err_msg)

    rules = cors.get("CORSRules") or []
    origin_ok = False
    get_ok = False
    post_ok = False
    for rule in rules:
        origins = rule.get("AllowedOrigins") or []
        methods = rule.get("AllowedMethods") or []
        if "*" in origins or app_origin in origins:
            origin_ok = True
        if "GET" in methods:
            get_ok = True
        if "POST" in methods:
            post_ok = True
        if origin_ok and get_ok and post_ok:
            return (True, "")

    if not post_ok:
        msg = "S3 CORS does not allow POST (required for uploads). Run: python -m app.s3_presigned " + bucket
    elif not get_ok:
        msg = "S3 CORS does not allow GET. Run: python -m app.s3_presigned " + bucket
    elif not origin_ok:
        msg = f"S3 CORS does not allow origin {app_origin!r}. Run: python -m app.s3_presigned " + bucket
    else:
        msg = ""
    return (not msg, msg or "")


def check_s3_upload_readiness(app_origin: str):
    """
    Verify S3 bucket region and CORS are OK for browser uploads (cached).
    Returns (True, "") if ok, (False, message) on failure.
    Used by /api/new-movie to fail fast with a clear message.
    """
    if _is_local_s3():
        return (True, "")

    bucket = os.environ.get(C.PLANTTRACER_S3_BUCKET)
    app_region = (os.environ.get(C.AWS_REGION) or "").strip()
    now = time.monotonic()
    key = (app_origin, bucket, app_region)
    cached = _UPLOAD_READINESS_CACHE.get(key)
    if cached is not None and (now - cached.get("ts", 0)) < _UPLOAD_READINESS_TTL:
        return (cached["ok"], cached.get("msg", ""))

    r_ok, r_msg = check_s3_bucket_region()
    if not r_ok:
        _UPLOAD_READINESS_CACHE[key] = {"ok": False, "msg": r_msg, "ts": now}
        return (False, r_msg)
    c_ok, c_msg = check_s3_cors(app_origin)
    if not c_ok:
        _UPLOAD_READINESS_CACHE[key] = {"ok": False, "msg": c_msg, "ts": now}
        return (False, c_msg)
    _UPLOAD_READINESS_CACHE[key] = {"ok": True, "msg": "", "ts": now}
    return (True, "")
