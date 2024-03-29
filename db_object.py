"""
Support for the object-store. Currently we have support for:

S3 - s3://bucket/name       - Stored in amazon S3. Running program needs to be authenticated to the bucket
DB - db://object_store/name - Local stored in the mysql database

If the environment varialbe PLANTTRACER_S3_BUCKET is set, use that bucket for writes, otherwise use DB.
Reads are based on whatever is in the URN.

"""

import os
import logging
import urllib.parse
import hashlib
import requests
import boto3

from lib.ctools import dbfile
from constants import C
from auth import get_dbreader,get_dbwriter

"""
Note tht the bucket must have this CORSRule:
<CORSRule>
    <AllowedOrigin>http://localhost:8080</AllowedOrigin>
    <AllowedMethod>PUT</AllowedMethod>
    <AllowedMethod>GET</AllowedMethod>
    <AllowedHeader>*</AllowedHeader>
</CORSRule>

We support the following schemas:

s3:// - Store in the AWS S3 bucket specified by the environment variable PLANTTRACER_S3_BUCKET. The running script must be authorized to read and write that bucket.

db:// - Store in the local MySQL DB specified in etc/client.ini under the [dbreader] and [dbwriter] sections.
"""

ALLOWED_SCHEMES = [ C.SCHEME_S3, C.SCHEME_DB ]
S3 = 's3'
DB_TABLE = 'object_store'

cors_configuration = {
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

def s3_client():
    return boto3.session.Session().client( S3 )

def make_urn(*, object_name, scheme = None ):
    # If environment variable is not set, default to the database schema
    # We grab this every time through so that the bucket can be changed during unit tests
    s3_bucket = os.environ.get(C.PLANTTRACER_S3_BUCKET,None)
    if scheme is None:
        scheme = C.SCHEME_S3 if (s3_bucket is not None) else C.SCHEME_DB
    if scheme == C.SCHEME_S3 and s3_bucket is None:
        scheme = C.SCHEME_DB
    if scheme == C.SCHEME_S3:
        netloc = s3_bucket
    elif scheme == C.SCHEME_DB:
        netloc = DB_TABLE
    else:
        raise ValueError(f"Scheme {scheme} not in ALLOWED_SCHEMES {ALLOWED_SCHEMES}")
    ret = f"{scheme}://{netloc}/{object_name}"
    logging.debug("make_urn=%s",ret)
    return ret

def make_signed_url(*,urn,operation=C.GET, expires=3600):
    logging.debug("urn=%s",urn)
    o = urllib.parse.urlparse(urn)
    if o.scheme==C.SCHEME_S3:
        op = {C.PUT:'put_object', C.GET:'get_object'}[operation]
        return s3_client().generate_presigned_url(
            op,
            Params={'Bucket': o.netloc,
                    'Key': o.path[1:]},
            ExpiresIn=expires)
    elif o.scheme==C.SCHEME_DB:
        raise RuntimeError("Signed URLs not implemented for DB")
    else:
        raise RuntimeError(f"Unknown scheme: {o.scheme}")

def make_presigned_post(*, urn, maxsize=10_000_000, mime_type='video/mp4',expires=3600, sha256=None):
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
    elif o.scheme==C.SCHEME_DB:
        return {'url':'/upload-movie',
                'mime_type':mime_type,
                'key': o.path[1:],
                'scheme':C.SCHEME_DB,
                'sha256':sha256 }
    else:
        raise RuntimeError(f"Unknown scheme: {o.scheme}")

def read_object(urn):
    o = urllib.parse.urlparse(urn)
    logging.debug("urn=%s o=%s",urn,o)
    if o.scheme == C.SCHEME_S3 :
        # We are getting the object, so we do not need a presigned url
        return s3_client().get_object(Bucket=o.netloc, Key=o.path[1:])["Body"].read()
    elif o.scheme in ['http','https']:
        r = requests.get(urn, timeout=C.DEFAULT_GET_TIMEOUT)
        return r.content
    elif o.scheme == C.SCHEME_DB:
        sha256 = os.path.splitext(o.path[1:])[0]
        res = dbfile.DBMySQL.csfr( get_dbreader(), "SELECT data from object_store where sha256=%s",(sha256,))
        return res[0][0]
    else:
        raise ValueError("Unknown schema: "+urn)

def write_object(urn, object_data):
    o = urllib.parse.urlparse(urn)
    logging.debug("urn=%s o=%s",urn,o)
    if o.scheme== C.SCHEME_S3:
        s3_client().put_object(Bucket=o.netloc, Key=o.path[1:], Body=object_data)
    elif o.scheme== C.SCHEME_DB:
        assert o.netloc == DB_TABLE
        dbfile.DBMySQL.csfr(
            get_dbwriter(), "INSERT INTO object_store (sha256,data) VALUES (%s,%s) ON DUPLICATE KEY UPDATE id=id",
            (sha256(object_data), object_data))
    else:
        raise ValueError(f"Cannot write object urn={urn}s len={len(object_data)}")


if __name__=="__main__":
    s3_bucket = os.environ.get(C.PLANTTRACER_S3_BUCKET,None)
    if s3_bucket is None:
        raise RuntimeError(C.PLANTTRACER_S3_BUCKET + " is not set")
    print("Updating CORS policy for ",s3_bucket)
    s3 = boto3.client( S3 )
    s3.put_bucket_cors(Bucket=s3_bucket, CORSConfiguration=cors_configuration)
