"""Support for the object-store. Currently we have support for:

S3 - s3://bucket/name       - Stored in amazon S3. Running program needs to be authenticated to the bucket
DB - db://object_store/name - Local stored in the mysql database

movie_name = {course_id}/{movie_id}.mov
frame_name = {course_id}/{movie_id}/frame_number:06d}.jpg

Note that we previously stored everything by SHA256. We aren't doing
that anymore, and the SHA256 stuff should probably come out.

"""

import os
import logging
import urllib.parse
import hashlib
import uuid

import requests
import boto3
from botocore.exceptions import ClientError

from . import dbfile
from .constants import C
from .auth import get_dbreader,get_dbwriter,AuthError

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

ALLOWED_SCHEMES = [ C.SCHEME_S3, C.SCHEME_DB ]
S3 = 's3'
DB_TABLE = 'object_store'
STORE_LOCAL=False               # even if S3 is set, store local
S3_BUCKET = None                # define to use it

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

def object_name(*,course_id,movie_id,frame_number=None,ext):
    """object_name is a URN that is generated according to a scheme
    that uses course_id, movie_id, and frame_number, but there is also
    a 16-bit nonce This means that you can't generate it on the fly;
    it has to be stored in a database.
    """
    fm = f"/{frame_number:06d}" if frame_number is not None else ""
    nonce = str(uuid.uuid4())[0:4]
    return f"{course_id}/{movie_id}{fm}-{nonce}{ext}"

def s3_client():
    return boto3.session.Session().client( S3 )


def make_urn(*, object_name, scheme = None ):
    """
    If environment variable is not set, default to the database schema
    We grab this every time through so that the bucket can be changed during unit tests
    """
    if STORE_LOCAL:
        scheme = C.SCHEME_DB
    if scheme is None:
        scheme = C.SCHEME_S3 if (S3_BUCKET is not None) else C.SCHEME_DB
    if scheme == C.SCHEME_S3 and S3_BUCKET is None:
        scheme = C.SCHEME_DB
    if scheme == C.SCHEME_S3:
        netloc = S3_BUCKET
    elif scheme == C.SCHEME_DB:
        netloc = DB_TABLE
    else:
        raise ValueError(f"Scheme {scheme} not in ALLOWED_SCHEMES {ALLOWED_SCHEMES}")
    ret = f"{scheme}://{netloc}/{object_name}"
    logging.debug("make_urn urn=%s",ret)
    return ret

API_SECRET=os.environ.get("API_SECRET","test-secret")
def sig_for_urn(urn):
    return sha256( (urn + API_SECRET).encode('utf-8'))

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
    elif o.scheme==C.SCHEME_DB:
        params = urllib.parse.urlencode({'urn': urn, 'sig': sig_for_urn(urn) })
        return f"/api/get-object?{params}"
    else:
        raise RuntimeError(f"Unknown scheme: {o.scheme} for urn=%s")

def read_signed_url(*,urn,sig):
    computed_sig = sig_for_urn(urn)
    if sig==computed_sig:
        logging.info("URL signature matches. urn=%s",urn)
        return read_object(urn)
    logging.error("URL signature does not match. urn=%s sig=%s computed_sig=%s",urn,sig,computed_sig)
    raise AuthError("signature does not verify")

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
        return {'url':'/api/upload-movie',
                'fields':{ 'mime_type':mime_type,
                           'key': o.path[1:],
                           'scheme':C.SCHEME_DB,
                           'sha256':sha256 }}
    else:
        raise RuntimeError(f"Unknown scheme: {o.scheme}")

def read_object(urn):
    logging.info("read_object(%s)",urn)
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
    elif o.scheme == C.SCHEME_DB:
        #key = os.path.splitext(o.path[1:])[0]
        res = dbfile.DBMySQL.csfr(
            get_dbreader(),
            "SELECT object_store.data from objects left join object_store on objects.sha256 = object_store.sha256 where urn=%s LIMIT 1",
            (urn,))
        if len(res)==1:
            return res[0][0]
        # Perhaps look for the SHA256 in the path and see if we can just find the data in the object_store?
        return None
    else:
        raise ValueError("Unknown schema: "+urn)

def write_object(urn, object_data):
    logging.info("write_object(%s,len=%s)",urn,len(object_data))
    o = urllib.parse.urlparse(urn)
    if o.scheme== C.SCHEME_S3:
        s3_client().put_object(Bucket=o.netloc, Key=o.path[1:], Body=object_data)
        return
    elif o.scheme== C.SCHEME_DB and len(object_data) < C.SCHEME_DB_MAX_OBJECT_LEN:
        object_sha256 = sha256(object_data)
        assert o.netloc == DB_TABLE
        dbfile.DBMySQL.csfr(
            get_dbwriter(),
            "INSERT INTO objects (urn,sha256) VALUES (%s,%s) ON DUPLICATE KEY UPDATE id=id",
            (urn, object_sha256))
        dbfile.DBMySQL.csfr(
            get_dbwriter(),
            "INSERT INTO object_store (sha256,data) VALUES (%s,%s) ON DUPLICATE KEY UPDATE id=id",
            (object_sha256, object_data))
        return
    raise ValueError(f"Cannot write object urn={urn} len={len(object_data)}")

def delete_object(urn):
    logging.info("delete_object(%s)",urn)
    o = urllib.parse.urlparse(urn)
    logging.debug("urn=%s o=%s",urn,o)
    if o.scheme== C.SCHEME_S3:
        s3_client().delete_object(Bucket=o.netloc, Key=o.path[1:])
    elif o.scheme== C.SCHEME_DB:
        assert o.netloc == DB_TABLE
        res = dbfile.DBMySQL.csfr( get_dbwriter(), "SELECT sha256 from objects where urn=%s", (urn,))
        if not res:
            return
        sha256_val = res[0][0]
        count  = dbfile.DBMySQL.csfr( get_dbwriter(), "SELECT count(*) from objects where sha256=%s", (sha256_val,))[0][0]
        dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE FROM objects where urn=%s", (urn,))
        if count==1:
            dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE FROM object_store where sha256=%s", (sha256_val,))
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
    s3.put_bucket_cors(Bucket=args.s3_bucket, CORSConfiguration=cors_configuration)
