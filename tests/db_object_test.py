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

from deploy.auth import get_dbreader,get_dbwriter
from deploy.paths import STATIC_DIR,TEST_DATA_DIR
from deploy.constants import C
import deploy.dbfile as dbfile
import deploy.db_object as db_object

def test_object_name():
    assert db_object.object_name(course_id=1, movie_id=2, ext='.mov').endswith(".mov")
    assert db_object.object_name(course_id=1, movie_id=2, frame_number=3, ext='.jpeg').endswith(".jpeg")

@pytest.fixture
def SaveS3Bucket():
    save = db_object.S3_BUCKET
    db_object.S3_BUCKET = None
    yield save
    db_object.S3_BUCKET = save

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
