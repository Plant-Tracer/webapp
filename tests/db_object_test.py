"""
Tests the DB object storage layer
"""


import pytest
import sys
import os
import bottle
import logging
import json
import subprocess
import uuid
import xml.etree.ElementTree

from os.path import abspath, dirname

sys.path.append(dirname(dirname(abspath(__file__))))

from auth import get_dbreader,get_dbwriter
from paths import STATIC_DIR,TEST_DATA_DIR
from lib.ctools import dbfile
from constants import C
import db_object

DATA = b"foobar"
DATA_SHA256 = "c3ab8ff13720e8ad9047dd39466b3c8974e592c2fa383d4a3960714caef0c4f2"

def test_sha256():
    assert db_object.sha256( DATA ) == DATA_SHA256

def test_object_name():
    assert db_object.object_name(course_id=1, movie_id=2, ext='.mov', data=DATA,
                                 data_sha256=DATA_SHA256).endswith(".mov")
    assert db_object.object_name(course_id=1, movie_id=2,
                                 frame_number=3, ext='.jpeg').endswith(".jpeg")

class SaveEnviron:
    def __init__(self,name):
        self.name = name
        self.save = os.environ.get(name,None)
    def __enter__(self):
        if self.save:
            del os.environ[self.name]
    def __exit__(self, *args):
        if self.save:
            os.environ[self.name] = self.save

def test_make_urn():
    with SaveEnviron(C.PLANTTRACER_S3_BUCKET) as e:
        name = db_object.object_name(course_id=1, movie_id=2, ext='.txt', data=DATA, data_sha256=DATA_SHA256)
        a = db_object.make_urn(object_name=name, scheme=None)
        assert a.endswith(".txt")

def test_write_read_delete_object():
    logging.debug("dbwriter: %s",get_dbwriter())
    with SaveEnviron(C.PLANTTRACER_S3_BUCKET) as e:
        name = db_object.object_name(course_id=1, movie_id=3, ext='.txt', data=DATA, data_sha256=DATA_SHA256)
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
    assert db_object.read_object(urn=urn) == None
