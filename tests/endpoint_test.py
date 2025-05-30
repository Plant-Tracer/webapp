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
from fixtures.localmail_config import mailer_config
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
    assert obj['error'] is False
    assert 'logs' in obj

# need /api/register
# need /api/resend-link

# /api/bulk-register tests

def test_bulk_register_success(client, new_course, mailer_config):
    """This tests the bulk-register api happy path when given a list of 1 email addresses
    """
    email_address = 'testuser@example.com'
    course_id = new_course[user_test.COURSE_ID]
    admin_user = db.lookup_user(email=None, user_id=new_course[user_test.ADMIN_ID], get_admin=True, get_courses=None)
    api_key = db.make_new_api_key(email=new_course[user_test.ADMIN_EMAIL])
   
    r = client.post('/api/bulk-register',
                    data={'api_key': api_key,
                          'course_id': str(course_id),
                          'email-addresses': [email_address],
                          'planttracer-endpoint': 'https://example.com/',
                         })
    logging.debug("r.json=%s",r.json)
    res = r.json
    assert res['error'] is False
    assert res['message'] == 'Registered 1 email addresses'
    db.delete_user(email=email_address,purge_movies=True)

def test_bulk_register_invalid_email(client, new_course, mailer_config):
    """This tests the bulk-register api when given an invalid email address
    """
    # TODO: test body
    assert True

# TODO: api/bulk-register: invalid course id
# TODO: api/bulk-register: no mailer configuration
# TODO: api/bulk-register: invalid mailer configuration
# TODO: api/bulk-register: User is not authorized to manipulate course
# TODO: api/bulk-register: empty email-addresses list
# TODO: api/bulk-register: email-addresses list length > 1
# TODO: api/bulk-register: first email address valid, second invalid
# TODO: api/bulk-register: second email address valid, first invalid

def test_upload_movie_data(client, api_key):
    """This tests creating a movie and uploading the entire thing using base64 encoding and the existing test user.
    This is redundant with movie_test.py::new_movie
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
