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
import posixpath

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .constants import C

logger = logging.getLogger(__name__)

_S3_CLIENTS = {}
SUPPORTED_SCHEMES = [ C.SCHEME_S3 ]
S3 = 's3'

def s3_client():
    # Note: the os.environ.get() cannot be in the def above because then it is executed at compile-time,
    # not at object creation time.
    region_name = os.environ.get(C.AWS_REGION, None)
    endpoint_url = os.environ.get(C.AWS_ENDPOINT_URL_S3, None)
    logger.info("s3_client region=%s endpoint_url=%s ", region_name, endpoint_url)
    cache_key = f"{region_name}_{endpoint_url}"
    if cache_key not in _S3_CLIENTS:
        _S3_CLIENTS[cache_key] = boto3.client('s3', region_name=region_name, endpoint_url=endpoint_url)
    return _S3_CLIENTS[cache_key]


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


def configure_bucket_cors(bucket):
    """Apply Plant Tracer's canonical browser upload/download CORS policy."""
    s3_client().put_bucket_cors(Bucket=bucket, CORSConfiguration=CORS_CONFIGURATION)

def sha256_hash(data):
    """Note: We use sha256 and have it hard coded everywhere. But the hashes should really be pluggable, in the form 'hashalg:hash'
    e.g. "sha256:01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b"
    """

    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()

def _template_value(name, value):
    """Return one required S3 template value without changing legacy IDs."""
    if value is None or str(value) == "":
        raise ValueError(f"{name} is required")
    return str(value)


def _template_component(name, value):
    """Return one required S3 key component."""
    component = _template_value(name, value)
    if "/" in component:
        raise ValueError(f"{name} must be one S3 key component")
    return component


def _deployment_value(value):
    """Return one deployment identifier used in namespaced object keys."""
    return _template_component("deployment_id", value)


def course_object_prefix(*, deployment_id, course_id):
    """Return the current course prefix for runtime movie objects."""
    return C.S3_COURSE_PREFIX_TEMPLATE.format(
        deployment_id=_deployment_value(deployment_id),
        course_id=_template_value("course_id", course_id),
    )


def movie_object_key(*, deployment_id, course_id, movie_id):
    """Return the durable original-movie object key."""
    return C.S3_MOVIE_OBJECT_KEY_TEMPLATE.format(
        deployment_id=_deployment_value(deployment_id),
        course_id=_template_value("course_id", course_id),
        movie_id=_template_value("movie_id", movie_id),
    )


def frame_object_key(*, deployment_id, course_id, movie_id, frame_number):
    """Return a persisted JPEG frame object key."""
    number = int(frame_number)
    if number < 0:
        raise ValueError("frame_number must be non-negative")
    return C.S3_FRAME_OBJECT_KEY_TEMPLATE.format(
        deployment_id=_deployment_value(deployment_id),
        course_id=_template_value("course_id", course_id),
        movie_id=_template_value("movie_id", movie_id),
        frame_number=number,
    )


def upload_staging_object_key(*, deployment_id, course_id, movie_id):
    """Return the deployment-scoped upload key reserved for issue #1152."""
    return C.S3_UPLOAD_STAGING_OBJECT_KEY_TEMPLATE.format(
        deployment_id=_deployment_value(deployment_id),
        course_id=_template_component("course_id", course_id),
        movie_id=_template_component("movie_id", movie_id),
    )


def _derived_movie_object_key(*, source_movie_object_key, template):
    source_stem, source_extension = posixpath.splitext(source_movie_object_key)
    return template.format(
        source_movie_stem=source_stem,
        source_movie_extension=source_extension,
    )


def traced_movie_object_key(*, source_movie_object_key):
    """Return the traced-movie key derived from an original movie key."""
    return _derived_movie_object_key(
        source_movie_object_key=source_movie_object_key,
        template=C.S3_TRACED_MOVIE_OBJECT_KEY_TEMPLATE,
    )


def analysis_zip_object_key(*, source_movie_object_key):
    """Return the analysis-frame ZIP key derived from an original movie key."""
    return _derived_movie_object_key(
        source_movie_object_key=source_movie_object_key,
        template=C.S3_ANALYSIS_ZIP_OBJECT_KEY_TEMPLATE,
    )


def make_urn(*, object_name, scheme=C.SCHEME_S3, bucket=None):
    """Build an S3 URN, using an explicit legacy bucket or the configured bucket."""
    if scheme not in SUPPORTED_SCHEMES:
        raise ValueError(f"Invalid scheme {scheme}")
    netloc = bucket or os.getenv(C.PLANTTRACER_S3_BUCKET)
    if not netloc:
        raise RuntimeError(f"{C.PLANTTRACER_S3_BUCKET} is not set")
    if netloc.startswith("s3:"):
        raise RuntimeError(f"{C.PLANTTRACER_S3_BUCKET} {netloc} should not start with s3://")
    ret = f"{scheme}://{netloc}/{object_name}"
    logger.debug("make_urn urn=%s",ret)
    return ret


def parse_s3_urn(*, urn):
    assert isinstance(urn, str)
    parsed = urllib.parse.urlparse(urn)
    if parsed.scheme != C.SCHEME_S3:
        raise RuntimeError(f"Unknown scheme: {parsed.scheme} for urn={urn}")
    if not parsed.netloc or not parsed.path or parsed.path == "/":
        raise ValueError(f"Invalid S3 URN: {urn}")
    return parsed.netloc, parsed.path[1:]


def traced_movie_urn(*, movie_data_urn):
    """Return a traced-movie URN while preserving the source bucket and extension."""
    bucket, source_key = parse_s3_urn(urn=movie_data_urn)
    return make_urn(
        object_name=traced_movie_object_key(source_movie_object_key=source_key),
        bucket=bucket,
    )


def analysis_zip_urn(*, movie_data_urn):
    """Return an analysis-frame ZIP URN while preserving the source bucket and extension."""
    bucket, source_key = parse_s3_urn(urn=movie_data_urn)
    return make_urn(
        object_name=analysis_zip_object_key(source_movie_object_key=source_key),
        bucket=bucket,
    )


def replace_course_object_key(*, object_key, from_course_id, to_course_id):
    """Move a namespaced or legacy key between course prefixes."""
    legacy_prefix = f"{_template_value('from_course_id', from_course_id)}/"
    namespaced_suffix = f"/{legacy_prefix}"
    if object_key.startswith(legacy_prefix):
        source_prefix = legacy_prefix
        target_prefix = f"{_template_value('to_course_id', to_course_id)}/"
    else:
        marker = object_key.find(namespaced_suffix)
        if marker < 0:
            raise ValueError(f"S3 key {object_key} does not contain course {from_course_id}")
        source_prefix = object_key[:marker + 1] + legacy_prefix
        target_prefix = (
            object_key[:marker + 1]
            + f"{_template_value('to_course_id', to_course_id)}/"
        )
    return target_prefix + object_key[len(source_prefix):]


def make_signed_url(*, urn, operation=C.GET, expires=3600, download_name=None):
    logger.debug("make_signed_url urn=%s",urn)
    bucket, key = parse_s3_urn(urn=urn)
    op = {C.PUT:'put_object', C.GET:'get_object'}[operation]
    params = {'Bucket': bucket, 'Key': key}
    if download_name is not None:
        if operation != C.GET:
            raise ValueError("download_name is valid only for signed GET URLs")
        safe_name = str(download_name).replace('"', '').replace('\r', '').replace('\n', '')
        params['ResponseContentDisposition'] = f'attachment; filename="{safe_name}"'
    return s3_client().generate_presigned_url(
        op,
        Params=params,
        ExpiresIn=expires)

def make_presigned_post(*, urn, maxsize=C.MAX_FILE_UPLOAD, exact_size=None,
                        mime_type='video/mp4', sha256=None, expires=3600,
                        research_use='not-answered', credit_by_name='not-answered', attribution_name='',
                        fpm=''):
    """Returns a dictionary with 'url' and 'fields'.
    research_use, credit_by_name, attribution_name, and fpm (capture interval, frames/minute) are included in
    the signature and set as S3 object metadata.
    Uses the bucket's region so the presigned URL is regional and S3 does not 307-redirect (avoids connection
    reset in the browser when POST body is not re-sent on redirect).
    """
    logger.debug("make_presigned_post urn=%s maxsize=%s exact_size=%s mime_type=%s sha256=%s expires=%s",
                 urn, maxsize, exact_size, mime_type, sha256, expires)
    if exact_size is not None:
        exact_size = int(exact_size)
        if exact_size < 1 or exact_size > maxsize:
            raise ValueError(f"exact_size must be between 1 and {maxsize}")
    bucket, key = parse_s3_urn(urn=urn)
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
    meta_fpm = 'x-amz-meta-fpm'
    meta_sha256 = 'x-amz-meta-sha256'
    attribution_safe = (attribution_name or '')[:256]
    fpm_safe = (fpm or '')[:32]
    fields = {
        'Content-Type': mime_type,
        meta_research: research_use,
        meta_credit: credit_by_name,
        meta_attribution: attribution_safe,
        meta_fpm: fpm_safe,
        meta_sha256: sha256 or '',
    }
    minimum_size = exact_size if exact_size is not None else 1
    maximum_size = exact_size if exact_size is not None else maxsize
    conditions = [
        {"Content-Type": mime_type},
        ["content-length-range", minimum_size, maximum_size],
        {meta_research: research_use},
        {meta_credit: credit_by_name},
        {meta_attribution: attribution_safe},
        {meta_fpm: fpm_safe},
        {meta_sha256: sha256 or ''},
    ]
    return client.generate_presigned_post(
        Bucket=bucket,
        Key=key,
        Conditions=conditions,
        Fields=fields,
        ExpiresIn=expires)

def object_exists(urn):
    assert len(urn) > 0
    bucket, key = parse_s3_urn(urn=urn)
    logger.debug("urn=%s bucket=%s key=%s", urn, bucket, key)
    try:
        s3_client().head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == "404":
            return False
        raise

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Set CORS policy for an S3 Bucket",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("s3_bucket")
    args = parser.parse_args()
    print("Updating CORS policy for ",args.s3_bucket)
    configure_bucket_cors(args.s3_bucket)
