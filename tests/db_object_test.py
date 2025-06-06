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

from app.auth import get_dbreader,get_dbwriter
from app.paths import STATIC_DIR,TEST_DATA_DIR
from app.constants import C
import app.dbfile as dbfile
import app.db_object as db_object

ENDPOINT_URL = 'http://localhost:9001'


def test_object_name():
    assert db_object.object_name(course_id=1, movie_id=2, ext='.mov').endswith(".mov")
    assert db_object.object_name(course_id=1, movie_id=2, frame_number=3, ext='.jpeg').endswith(".jpeg")

@pytest.fixture
def SaveS3Bucket():
    save = os.getenv(C.AWS_S3_BUCKET)
    os.environ[C.AWS_S3_BUCKET] = C.DEFAULT_S3_BUCKET
    yield save
    if save:
        sys.environ[C.AWS_S3_BUCKET] = save
    else:
        del sys.environ


def test_make_urn(SaveS3Bucket):
    logging.info("Saved S3 bucket=%s",SaveS3Bucket)
    name = db_object.object_name(course_id=1, movie_id=2, ext='.txt')
    a = db_object.make_urn(object_name=name, scheme=None)
    assert a.endswith(".txt")

def test_write_read_delete_object(SaveS3Bucket):
    logging.info("Saved S3 bucket=%s",SaveS3Bucket)
    logging.debug("dbwriter: %s",get_dbwriter())
    DATA = str(uuid.uuid4()).encode('utf-8')
    hasher = hashlib.sha256()
    hasher.update(DATA)
    DATA_SHA256 = hasher.hexdigest()

    name = db_object.object_name(course_id=1, movie_id=3, ext='.txt')
    urn  = db_object.make_urn(object_name=name, scheme=None)
    db_object.write_object(urn=urn, object_data=DATA)

    res = dbfile.DBMySQL.csfr( get_dbreader(), "SELECT * from object_store where sha256=%s", (DATA_SHA256,), asDicts=True, debug=True)
    assert len(res)==1
    assert res[0]['sha256']==DATA_SHA256
    assert res[0]['data']==DATA

    res = dbfile.DBMySQL.csfr( get_dbreader(), "SELECT * from objects where sha256=%s", (DATA_SHA256,), asDicts=True, debug=True)
    assert len(res)==1
    assert res[0]['sha256']==DATA_SHA256
    assert res[0]['urn']==urn

    obj_data = db_object.read_object(urn=urn)
    assert obj_data == DATA

    db_object.delete_object(urn=urn)
    assert db_object.read_object(urn=urn) is None
