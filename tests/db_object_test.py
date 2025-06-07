"""
Tests the DB object storage layer
"""


import pytest
import sys
import os
import logging
import json
import subprocess
import uuid
import xml.etree.ElementTree
import hashlib

import boto3

from app.paths import STATIC_DIR,TEST_DATA_DIR
from app.constants import C
import app.db_object as db_object

s3client = boto3.client('s3')

def test_object_name():
    assert db_object.object_name(course_id=1, movie_id=2, ext='.mov').endswith(".mov")
    assert db_object.object_name(course_id=1, movie_id=2, frame_number=3, ext='.jpeg').endswith(".jpeg")

@pytest.fixture
def s3test():
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

def test_make_urn(s3test):
    name = db_object.object_name(course_id=1, movie_id=2, ext='.txt')
    a = db_object.make_urn(object_name=name, scheme=None)
    assert a.endswith(".txt")

def test_write_read_delete_object(s3test):
    DATA = str(uuid.uuid4()).encode('utf-8')
    hasher = hashlib.sha256()
    hasher.update(DATA)
    DATA_SHA256 = hasher.hexdigest()

    name = db_object.object_name(course_id=1, movie_id=3, ext='.txt')
    urn  = db_object.make_urn(object_name=name, scheme=None)
    try:
        db_object.write_object(urn=urn, object_data=DATA)
    except s3client.exceptions.NoSuchBucket as e:
        logging.error("urn=%s error: %s",urn,e)
        raise RuntimeError() from e

    obj_data = db_object.read_object(urn=urn)
    assert obj_data == DATA

    db_object.delete_object(urn=urn)
    assert db_object.read_object(urn=urn) is None
