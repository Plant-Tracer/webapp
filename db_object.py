"""
Support for the object-store
"""

import os
import boto3
import logging
import urllib.parse
from constants import C

S3_BUCKET = os.environ.get(C.PLANTTRACER_S3_BUCKET,'')

"""
Note tht the bucket must have this CORSRule:
<CORSRule>
    <AllowedOrigin>http://localhost:8080</AllowedOrigin>
    <AllowedMethod>PUT</AllowedMethod>
    <AllowedMethod>GET</AllowedMethod>
    <AllowedHeader>*</AllowedHeader>
</CORSRule>
"""

cors_configuration = {
    'CORSRules': [{
        'AllowedHeaders': ['*'],
        'AllowedMethods': ['PUT', 'POST', 'DELETE', 'GET'],
        'AllowedOrigins': ['*'],
        'ExposeHeaders': [],
        'MaxAgeSeconds': 3600
    }]
}


def s3_client():
    return boto3.session.Session().client('s3')

def make_urn(*, object_name, schema='s3'):
    """Currently we only support the s3 schema. Makes a URL for movies"""
    assert schema.lower() == 's3'
    if not S3_BUCKET:
        raise RuntimeError(C.PLANTTRACER_S3_BUCKET+" not set")
    ret = f"s3://{S3_BUCKET}/{object_name}"
    logging.debug("make_urn=%s",ret)
    return ret

def create_presigned_url(bucket_name, object_name, operation, expiration=3600):
    """
    Generate a presigned URL to upload a file to S3.

    :param bucket_name: String name of the bucket to upload to
    :param object_name: String name of the object for the upload URL
    :param expiration: Time in seconds for the presigned URL to remain valid
    :return: Presigned URL as string if successful, None otherwise
    """
    assert operation in ['put_object','get_object']

    # Create an S3 client.
    # May raise botocore.exceptions.NoCredentialsError
    s3_client = boto3.client('s3')
    logging.debug("operation=%s expiration=%s",operation,expiration)

    if operation=='put_object':
        return s3_client.generate_presigned_post(bucket_name,
                                                 object_name,
                                                 Fiends=None,
                                                 Conditions=None,
                                                 ExpiresIn=3600)

    return s3_client.generate_presigned_url(operation,
                                            Params={'Bucket': bucket_name,
                                                    'Key': object_name},
                                            ExpiresIn=expiration)

def make_signed_url(*,urn,operation=C.GET):
    o = urllib.parse.urlparse(urn)
    if o.scheme=='s3':
        op = {C.PUT:'put_object', C.GET:'get_object'}[operation]
        return create_presigned_url(o.netloc, o.path[1:], op) # remove the / from the path
    raise RuntimeError(f"Unknown scheme: {o.scheme}")

def make_presigned_post(*, urn, maxsize=10_000_000, mime_type='video/mp4',expires=3600):
    """Returns a dictionary with 'url' and 'fields'"""
    o = urllib.parse.urlparse(urn)
    if o.scheme!='s3':
        raise RuntimeError(f"Unknown scheme: {o.scheme} (urn={urn})")
    return s3_client().generate_presigned_post( Bucket=o.netloc,
                                                Key=o.path[1:],
                                                Conditions=[
                                                    {"Content-Type": mime_type}, # Explicitly allow Content-Type header
                                                    ["content-length-range", 1, maxsize], # Example condition: limit size between 1 and 10 MB
                                                ],
                                                Fields= { 'Content-Type':mime_type },
                                                ExpiresIn=expires)



def read_object(urn):
    o = urllib.parse.urlparse(object_url)
    if o.scheme=='s3':
        # We are getting the object, so we do not need a presigned url
        obj = s3_client().Object(o.netloc, o.path[1:])
        data = obj.get()['Body'].read()
        return data
    # default to requests
    r = requests.get(object_url, timeout=C.DEFAULT_GET_TIMEOUT)
    return r.content


if __name__=="__main__":
    assert len(S3_BUCKET)>0
    print("Updating CORS policy for ",S3_BUCKET)
    s3 = boto3.client('s3')
    s3.put_bucket_cors(Bucket=S3_BUCKET, CORSConfiguration=cors_configuration)
