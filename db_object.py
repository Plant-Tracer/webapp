"""
Support for the object-store
"""

import os
import boto3
from constants import C

S3_BUCKET = os.environ.get(C.PLANTTRACER_S3_BUCKET,'')


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
    return s3_client.generate_presigned_url(operation,
                                            Params={'Bucket': bucket_name,
                                                    'Key': object_name},
                                            ExpiresIn=expiration)


def make_urn(*,movie_data_sha256, schema='s3'):
    """Currently we only support the s3 schema. Makes a URL for movies"""
    assert len(movie_data_sha256)==64
    assert schema.lower() == 's3'
    if not S3_BUCKET:
        raise RuntimeError(C.PLANTTRACER_S3_BUCKET+" not set")
    return f"s3://{S3_BUCKET}/{movie_data_sha256}" + C.MOVIE_EXTENSION

def make_url(*,movie_data_sha256,operation=C.GET,schema='s3'):
    assert len(movie_data_sha256)==64
    assert schema.lower() == 's3'
    assert operation in [C.PUT, C.GET]
    if not S3_BUCKET:
        raise RuntimeError(C.PLANTTRACER_S3_BUCKET+" not set")

    op = {C.PUT:'put_object', C.GET:'get_object'}[operation]
    return create_presigned_url(S3_BUCKET, movie_data_sha256, op)
