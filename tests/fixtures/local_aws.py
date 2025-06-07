"""
These fixtures set environment variables for running DynamoDB Local and minio

"""


import uuid
import pytest
import os
import subprocess
from os.path import join,dirname,abspath

import boto3

from app.constants import C
from app.paths import ROOT_DIR
from app import odb
from app.odb import DDBO
from app import odbmaint

s3client = boto3.client('s3')

@pytest.fixture
def local_ddb():
    """Create an empty DynamoDB locally.
    Starts the database if it is not running.
    """
    subprocess.call( [os.path.join(ROOT_DIR,'local_dynamodb_control.bash'),'start'])

    # Make a random prefix for this run.
    # Make sure that the tables don't exist, then create them

    os.environ['AWS_DEFAULT_REGION']    = 'local'
    os.environ['DYNAMODB_ENDPOINT_URL'] = C.DYNAMODB_TEST_ENDPOINT_URL
    os.environ['DYNAMODB_TABLE_PREFIX'] = 'test-'+str(uuid.uuid4())[0:4]
    ddbo = DDBO()
    odbmaint.drop_tables(ddbo)
    odbmaint.create_tables(ddbo)
    return ddbo



@pytest.fixture
def local_s3():
    save_bucket = os.getenv(C.PLANTTRACER_S3_BUCKET)
    save_endpoint = os.getenv(C.S3_ENDPOINT_URL)
    os.environ[C.PLANTTRACER_S3_BUCKET] = C.TEST_S3_BUCKET
    os.environ[C.S3_ENDPOINT_URL] = C.TEST_S3_ENDPOINT_URL
    os.environ[C.AWS_PROFILE ] = 'minio'
    yield save_bucket
    if save_bucket:
        os.environ[C.PLANTTRACER_S3_BUCKET] = save_bucket
    else:
        del os.environ[C.PLANTTRACER_S3_BUCKET]
    if save_endpoint:
        os.environ[C.S3_ENDPOINT_URL] = save_endpoint
    else:
        del os.environ[C.S3_ENDPOINT_URL]
