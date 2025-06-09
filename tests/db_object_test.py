"""
Tests the DB object storage layer
"""
import sys
import os
import logging
import json
import subprocess
import uuid
import xml.etree.ElementTree
import hashlib

import pytest
#import boto3

#from app.paths import STATIC_DIR,TEST_DATA_DIR
#from app.constants import C
#import app.db_object as db_object

#from fixtures.local_aws import local_s3

def test_object_name():
    assert db_object.object_name(course_id=1, movie_id=2, ext='.mov').endswith(".mov")
    assert db_object.object_name(course_id=1, movie_id=2, frame_number=3, ext='.jpeg').endswith(".jpeg")

def test_make_urn(local_s3):
    name = db_object.object_name(course_id=1, movie_id=2, ext='.txt')
    a = db_object.make_urn(object_name=name, scheme=None)
    assert a.endswith(".txt")

# pylint: disable=unused-argument
def test_write_read_delete_object(local_s3):
    DATA = str(uuid.uuid4()).encode('utf-8')
    hasher = hashlib.sha256()
    hasher.update(DATA)
    # DATA_SHA256 = hasher.hexdigest()

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
