"""endpoint_test.py - can test either the local endpoint or remote endpoints
(with a fixture that uses requests)
"""

import logging
import subprocess
import copy
import sys
import os
from os.path import dirname, abspath
import glob
import re
import time
import json
import base64
from urllib3.util import Retry

import pytest

import app.db as db
import app.db_object as db_object
from app.paths import TEST_DIR, STANDALONE_PATH, TEST_MOVIE_FILENAME
from app.constants import C,E,__version__,GET,POST,GET_POST

from fixtures.app_client import client
import user_test
from user_test import new_course, new_user, api_key

FRAME_FILES = glob.glob(os.path.join(TEST_DIR, "data", "frame_*.jpg"))
FRAME_RE = re.compile(r"frame_(\d+).jpg")
ENDPOINT_URL = 'ENDPOINT_URL'
SKIP_ENDPOINT_TEST = 'SKIP_ENDPOINT_TEST'

def test_ver1(client):
    r = client.get('/ver')
    assert r.status_code == 200
    r = client.get('/verx')
    assert r.status_code == 404

def test_ver2(client):
    r = client.get('/api/ver')
    assert r.status_code == 200
    val = r.json
    assert val['__version__'] == __version__
    assert val['sys_version'] == sys.version


def test_add(client):
    r = client.post('/api/add', data={'a': 10, 'b': 20})
    assert r.status_code == 200
    assert r.json == {'result': 30, 'error': False}


def test_api_key(client, api_key):
    r = client.post('/api/check-api_key', data={'api_key': api_key})
    assert r.status_code == 200
    assert r.json['error'] == False
    assert r.json['userinfo']['name'] == 'Test User Name'

    r = client.post('/api/check-api_key', data={'api_key': 'invalid'})
    assert r.status_code == 200
    assert r.json['error'] == True

def test_api_get_logs(client, new_user):
    api_key = new_user[user_test.API_KEY]
    user_id = new_user[user_test.USER_ID]

    r = client.post('/api/get-logs',
                    data={'api_key': api_key, 'log_user_id' : user_id})
    assert r.status_code == 200
    obj = r.json
    assert obj['error'] == False
    assert 'logs' in obj

# need /api/register
# need /api/resend-link
# need /api/bulk-register


def test_upload_movie_data(client, api_key):
    """This tests creating a movie and uploading the entire thing using base64 encoding and the existing test user.
    This is redundent with movie_test.py::new_movie
    """
    assert len(FRAME_FILES) > 0
    with open(TEST_MOVIE_FILENAME, 'rb') as f:
        movie_data = f.read()
    movie_base64_data = base64.b64encode(movie_data)
    movie_data_sha256 = db_object.sha256(movie_data)
    r = client.post('/api/new-movie',
                    data={'api_key': api_key,
                          'title': 'Test Title at '+time.asctime(),
                          'description': 'test-upload',
                          'movie_base64_data': movie_base64_data,
                          'movie_data_sha256': movie_data_sha256 })
    logging.debug("r.json=%s",r.json)
    res = r.json
    assert res['error'] == False
    movie_id = res['movie_id']

    # Now delete the movie
    r = client.post('/api/delete-movie', data = {'api_key': api_key,
                  'movie_id': movie_id})
    res = r.json
    assert res['error'] == False

    # Purge the movie (to clean up)
    db.purge_movie(movie_id = movie_id)

# need /api/get-movie-data
# need /api/get-movie-metadata
# need /api/get-movie-trackpoints
# need /api/delete-movie
# need /api/track-movie
# need /api/new-movie-analysis
# need /api/new-frame
# need /api/get-frame
# need /api/put-frame-analysis
