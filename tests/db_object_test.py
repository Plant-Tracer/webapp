"""
Tests the DB object storage layer
"""
import logging
import uuid
import hashlib

import boto3

from app import s3_presigned
from app import odb_movie_data
from app import odb

# Fixtures are imported in conftest.py

s3client = boto3.client('s3')

def test_object_name():
    assert s3_presigned.make_object_name(course_id=1, movie_id=2, ext='.mov').endswith(".mov")
    assert s3_presigned.make_object_name(course_id=1, movie_id=2, frame_number=3, ext='.jpeg').endswith(".jpeg")

# pylint: disable=unused-argument
def test_make_urn(local_s3):
    name = s3_presigned.make_object_name(course_id=1, movie_id=2, ext='.txt')
    a = s3_presigned.make_urn(object_name=name)
    assert a.endswith(".txt")

# pylint: disable=unused-argument
def test_write_read_delete_object(local_s3):
    DATA = str(uuid.uuid4()).encode('utf-8')
    hasher = hashlib.sha256()
    hasher.update(DATA)
    # DATA_SHA256 = hasher.hexdigest()

    course_id = 'bogus'
    movie_id = odb.new_movie_id()
    name = s3_presigned.make_object_name(course_id=course_id, movie_id=movie_id, ext='.txt')
    urn  = s3_presigned.make_urn(object_name=name)
    try:
        odb_movie_data.write_object(urn=urn, object_data=DATA)
    except s3client.exceptions.NoSuchBucket as e:
        logging.error("urn=%s error: %s",urn,e)
        raise RuntimeError() from e

    obj_data = odb_movie_data.read_object(urn=urn)
    assert obj_data == DATA

    odb_movie_data.delete_object(urn=urn)
    assert odb_movie_data.read_object(urn=urn) is None
