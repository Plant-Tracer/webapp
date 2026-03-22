"""
Support for the object-store. Currently we have support for:

S3 - s3://bucket/name       - Stored in amazon S3. Running program needs to be authenticated to the bucket

All objects have this standard naming convention.
Nevertheless, we store the frame names in the DynamoDB. We may stop doing that shortly.

"""

import os
import logging
import urllib.parse
import hashlib

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .constants import C

# Prefix under which uploads land so lambda-resize is triggered; lambda moves to final key.
UPLOAD_STAGING_PREFIX = "uploads/"

logger = logging.getLogger(__name__)

SUPPORTED_SCHEMES = [ C.SCHEME_S3 ]
S3 = 's3'

def s3_client(region_name=None, endpoint_url=None):
    # Note: the os.environ.get() cannot be in the def above because then it is executed at compile-time,
    # not at object creation time.
    if region_name is None:
        region_name = os.environ.get(C.AWS_REGION, None)
    if endpoint_url is None:
        endpoint_url = os.environ.get(C.AWS_ENDPOINT_URL_S3, None)

    logger.info("s3_client region=%s endpoint_url=%s ", region_name, endpoint_url)

    return boto3.Session().client('s3', region_name=region_name, endpoint_url=endpoint_url)


def _get_bucket_region(bucket):
    """Return the bucket's region (e.g. 'us-east-1'). Skips when using local S3."""
    if os.environ.get(C.AWS_REGION) == "local":
        return None
    if os.environ.get(C.AWS_ENDPOINT_URL_S3):
        return None
    try:
        loc = s3_client().get_bucket_location(Bucket=bucket)
        return (loc.get("LocationConstraint") or "").strip() or "us-east-1"
    except ClientError:
        return None

CORS_CONFIGURATION = {
    'CORSRules': [{
        'AllowedHeaders': ['*'],
        'AllowedMethods': ['PUT', 'POST', 'DELETE', 'GET'],
        'AllowedOrigins': ['*'],
        'ExposeHeaders': [],
        'MaxAgeSeconds': 3600
    }]
}

def sha256_hash(data):
    """Note: We use sha256 and have it hard coded everywhere. But the hashes should really be pluggable, in the form 'hashalg:hash'
    e.g. "sha256:01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b"
    """

    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()

def make_object_name(*,course_id,movie_id,frame_number=None, ext):
    """object_name is a URN that is generated according to a scheme
    that uses course_id, movie_id, and frame_number. URNs are deterministic.
    """
    if frame_number is None:
        return C.MOVIE_TEMPLATE.format(course_id=course_id, movie_id=movie_id, ext=ext)
    return C.FRAME_TEMPLATE.format(course_id=course_id, movie_id=movie_id, frame_number=frame_number, ext=ext)


def make_urn(*, object_name, scheme = C.SCHEME_S3 ):
    """
    If environment variable is not set, default to the database schema
    We grab this every time through so that the bucket can be changed during unit tests
    """
    if scheme not in SUPPORTED_SCHEMES:
        raise ValueError(f"Invalid scheme {scheme}")
    netloc = os.getenv(C.PLANTTRACER_S3_BUCKET)
    if netloc.startswith("s3:"):
        raise RuntimeError(f"{C.PLANTTRACER_S3_BUCKET} {netloc} should not start with s3://")
    ret = f"{scheme}://{netloc}/{object_name}"
    logger.debug("make_urn urn=%s",ret)
    return ret

def make_signed_url(*,urn,operation=C.GET, expires=3600):
    assert isinstance(urn,str)
    logger.debug("make_signed_url urn=%s",urn)
    o = urllib.parse.urlparse(urn)
    if o.scheme==C.SCHEME_S3:
        op = {C.PUT:'put_object', C.GET:'get_object'}[operation]
        return s3_client().generate_presigned_url(
            op,
            Params={'Bucket': o.netloc,
                    'Key': o.path[1:]},
            ExpiresIn=expires)
    raise RuntimeError(f"Unknown scheme: {o.scheme} for urn=%s")

def make_presigned_post(*, urn, maxsize=C.MAX_FILE_UPLOAD, mime_type='video/mp4', sha256=None, expires=3600,
                        research_use='0', credit_by_name='0', attribution_name=''):
    """Returns a dictionary with 'url' and 'fields'.
    research_use, credit_by_name, attribution_name are included in the signature and set as S3 object metadata.
    Uses the bucket's region so the presigned URL is regional and S3 does not 307-redirect (avoids connection
    reset in the browser when POST body is not re-sent on redirect).
    """
    logger.debug("make_presigned_post urn=%s maxsize=%s mime_type=%s sha256=%s expires=%s",
                 urn, maxsize, mime_type, sha256, expires)
    o = urllib.parse.urlparse(urn)
    if o.scheme == C.SCHEME_S3:
        bucket = o.netloc
        region = _get_bucket_region(bucket)
        if region:
            endpoint_url = f"https://s3.{region}.amazonaws.com"
            client = boto3.Session().client(
                's3',
                region_name=region,
                endpoint_url=endpoint_url,
                config=Config(s3={'addressing_style': 'virtual'})
            )
        else:
            client = s3_client()
        meta_research = 'x-amz-meta-research-use'
        meta_credit = 'x-amz-meta-credit-by-name'
        meta_attribution = 'x-amz-meta-attribution-name'
        attribution_safe = (attribution_name or '')[:256]
        fields = {
            'Content-Type': mime_type,
            meta_research: research_use,
            meta_credit: credit_by_name,
            meta_attribution: attribution_safe,
        }
        conditions = [
            {"Content-Type": mime_type},
            ["content-length-range", 1, maxsize],
            {meta_research: research_use},
            {meta_credit: credit_by_name},
            {meta_attribution: attribution_safe},
        ]
        return client.generate_presigned_post(
            Bucket=bucket,
            Key=o.path[1:],
            Conditions=conditions,
            Fields=fields,
            ExpiresIn=expires)
    raise RuntimeError(f"Unknown scheme: {o.scheme}")

def object_exists(urn):
    assert len(urn) > 0
    o = urllib.parse.urlparse(urn)
    logger.debug("urn=%s o=%s",urn,o)
    if o.scheme==C.SCHEME_S3:
        try:
            s3_client().head_object(Bucket=o.netloc, Key=o.path[1:])
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == "404":
                return False
            raise
    else:
        raise RuntimeError(f"Unknown scheme: {o.scheme}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Set CORS policy for an S3 Bucket",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("s3_bucket")
    args = parser.parse_args()
    print("Updating CORS policy for ",args.s3_bucket)
    s3 = boto3.client( S3 )
    s3.put_bucket_cors(Bucket=args.s3_bucket, CORSConfiguration=CORS_CONFIGURATION)
