"""Support for the object-store. Currently we have support for:

S3 - s3://bucket/name       - Stored in amazon S3. Running program needs to be authenticated to the bucket

movie_name = {course_id}/{movie_id}.mov
frame_name = {course_id}/{movie_id}/frame_number:06d}.jpg
"""

import os
import logging
import urllib.parse
import hashlib
import uuid

import requests
import boto3
from botocore.exceptions import ClientError

from .constants import C

# Configure basic logging
logging.basicConfig(format=C.LOGGING_CONFIG, level=C.LOGGING_LEVEL)
logger = logging.getLogger(__name__)

"""
Note tht to allow for local access the bucket must have this CORSRule:
<CORSRule>
    <AllowedOrigin>http://localhost:8080</AllowedOrigin>
    <AllowedMethod>PUT</AllowedMethod>
    <AllowedMethod>GET</AllowedMethod>
    <AllowedHeader>*</AllowedHeader>
</CORSRule>
We use this:
<CORSRule>
    <AllowedOrigin>*</AllowedOrigin>
    <AllowedMethod>DELETE</AllowedMethod>
    <AllowedMethod>GET</AllowedMethod>
    <AllowedMethod>POST</AllowedMethod>
    <AllowedMethod>PUT</AllowedMethod>
    <AllowedHeader>*</AllowedHeader>
</CORSRule>
"""

ALLOWED_SCHEMES = [ C.SCHEME_S3 ]
S3 = 's3'

def s3_client(region_name=None, endpoint_url=None):
    # Note: the os.environ.get() cannot be in the def above because then it is executed at compile-time,
    # not at object creation time.
    if region_name is None:
        region_name = os.environ.get(C.AWS_DEFAULT_REGION, C.THE_DEFAULT_REGION)
    if endpoint_url is None:
        endpoint_url = os.environ.get(C.S3_ENDPOINT_URL,None)

    return boto3.Session(profile_name = os.getenv(C.AWS_PROFILE)).client(
        's3', region_name = region_name, endpoint_url=endpoint_url)

CORS_CONFIGURATION = {
    'CORSRules': [{
        'AllowedHeaders': ['*'],
        'AllowedMethods': ['PUT', 'POST', 'DELETE', 'GET'],
        'AllowedOrigins': ['*'],
        'ExposeHeaders': [],
        'MaxAgeSeconds': 3600
    }]
}

def sha256(data):
    """Note: We use sha256 and have it hard coded everywhere. But the hashes should really be pluggable, in the form 'hashalg:hash'
    e.g. "sha256:01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b"
    """

    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()

def object_name(*,course_id,movie_id,frame_number=None,ext):
    """object_name is a URN that is generated according to a scheme
    that uses course_id, movie_id, and frame_number, but there is also
    a 16-bit nonce This means that you can't generate it on the fly;
    it has to be stored in a database.
    """
    fm = f"/{frame_number:06d}" if frame_number is not None else ""
    nonce = str(uuid.uuid4())[0:4]
    return f"{course_id}/{movie_id}{fm}-{nonce}{ext}"


def make_urn(*, object_name, scheme = None ):
    """
    If environment variable is not set, default to the database schema
    We grab this every time through so that the bucket can be changed during unit tests
    """
    scheme = C.SCHEME_S3        # the only one we currently support
    netloc = os.getenv(C.PLANTTRACER_S3_BUCKET,C.DEFAULT_S3_BUCKET)
    ret = f"{scheme}://{netloc}/{object_name}"
    logging.debug("make_urn urn=%s",ret)
    return ret

def make_signed_url(*,urn,operation=C.GET, expires=3600):
    assert isinstance(urn,str)
    logging.debug("make_signed_url urn=%s",urn)
    o = urllib.parse.urlparse(urn)
    if o.scheme==C.SCHEME_S3:
        op = {C.PUT:'put_object', C.GET:'get_object'}[operation]
        return s3_client().generate_presigned_url(
            op,
            Params={'Bucket': o.netloc,
                    'Key': o.path[1:]},
            ExpiresIn=expires)
    else:
        raise RuntimeError(f"Unknown scheme: {o.scheme} for urn=%s")

def make_presigned_post(*, urn, maxsize=C.MAX_FILE_UPLOAD, mime_type='video/mp4',expires=3600, sha256=None):
    """Returns a dictionary with 'url' and 'fields'"""
    o = urllib.parse.urlparse(urn)
    if o.scheme==C.SCHEME_S3:
        return s3_client().generate_presigned_post(
            Bucket=o.netloc,
            Key=o.path[1:],
            Conditions=[
                {"Content-Type": mime_type}, # Explicitly allow Content-Type header
                ["content-length-range", 1, maxsize], # Example condition: limit size between 1 and 10 MB
            ],
            Fields= { 'Content-Type':mime_type },
            ExpiresIn=expires)
    else:
        raise RuntimeError(f"Unknown scheme: {o.scheme}")

def read_object(urn):
    o = urllib.parse.urlparse(urn)
    logging.debug("urn=%s o=%s",urn,o)
    if o.scheme == C.SCHEME_S3 :
        # We are getting the object, so we do not need a presigned url
        try:
            return s3_client().get_object(Bucket=o.netloc, Key=o.path[1:])["Body"].read()
        except ClientError as ex:
            logging.error("ClientError: %s  Bucket=%s  Key=%s",ex,o.netloc,o.path[1:])
            return None
    elif o.scheme in ['http','https']:
        r = requests.get(urn, timeout=C.DEFAULT_GET_TIMEOUT)
        return r.content
    else:
        raise ValueError("Unknown schema: "+urn)

def write_object(urn, object_data):
    logging.info("write_object(%s,len=%s)",urn,len(object_data))
    o = urllib.parse.urlparse(urn)
    if o.scheme== C.SCHEME_S3:
        s3_client().put_object(Bucket=o.netloc, Key=o.path[1:], Body=object_data)
        return
    raise ValueError(f"Cannot write object urn={urn} len={len(object_data)}")

def delete_object(urn):
    logging.debug("delete_object(%s)",urn)
    o = urllib.parse.urlparse(urn)
    if o.scheme== C.SCHEME_S3:
        s3_client().delete_object(Bucket=o.netloc, Key=o.path[1:])
    else:
        raise ValueError(f"Cannot delete object urn={urn}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Set CORS policy for an S3 Bucket",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("s3_bucket")
    args = parser.parse_args()
    print("Updating CORS policy for ",args.s3_bucket)
    s3 = boto3.client( S3 )
    s3.put_bucket_cors(Bucket=args.s3_bucket, CORSConfiguration=CORS_CONFIGURATION)
