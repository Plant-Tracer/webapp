"""endpoint_test.py - these tests use http to a running endpoint. Largely tests /api

Environment variables:

SKIP_ENDPOINT_TEST = "YES" to skip the tests in this file.
ENDPOINT_URL       = If defined, use the specified endpoint, rather than the one specified by the fixture

The fixture allows that running endpoint to be one that is running locally.
Most of these tests should be able to call the tests in movie_test.py
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

from requests.adapters import HTTPAdapter
import requests

import pytest

import deploy.db as db
from deploy.paths import TEST_DIR, STANDALONE_PATH

import user_test
from user_test import new_course, new_user, api_key
from constants import C,E,__version__,GET,POST,GET_POST

FRAME_FILES = glob.glob(os.path.join(TEST_DIR, "data", "frame_*.jpg"))
FRAME_RE = re.compile(r"frame_(\d+).jpg")
ENDPOINT_URL = 'ENDPOINT_URL'
SKIP_ENDPOINT_TEST = 'SKIP_ENDPOINT_TEST'

should_skip_endpoint_test = (os.environ.get(SKIP_ENDPOINT_TEST, C.NO) == C.YES)

HTTP_PORT = 8008

def next_port():
    global HTTP_PORT
    pt = HTTP_PORT
    HTTP_PORT += 1
    return pt

#
# This fixture creates a local webserver and services it with the app in the parent directory.
# It yields the URL of the endpoint.
# For testing other endpoints, we

@pytest.fixture
def http_endpoint():
    """Create an endpoint running on localhost."""
    port = next_port()
    p = subprocess.Popen([sys.executable, STANDALONE_PATH,
                          '--port', str(port)], stderr=subprocess.PIPE, encoding='utf-8')
    for want in ['server starting up', 'Listening on', 'Hit Ctrl-C to quit.']:
        line = p.stderr.readline()
        logging.info('%s', line)
        if want not in line:
            print("ERROR: line=%s",line,file=sys.stderr)
            print("REMAINDER OF INPUT: %s",p.stderr.read(),file=sys.stderr)
            raise RuntimeError("could not create http endpoint")
    http_endpoint_url = f'http://127.0.0.1:{port}'
    # Make sure it is working and retry up to 10 times

    s = requests.Session()
    s.mount(http_endpoint_url+'/ver',
            HTTPAdapter(max_retries=Retry(total=10, backoff_factor=0.2)))
    r = s.get(http_endpoint_url+'/ver')
    logging.info("Server running. r=%s", r)
    logging.info("r.ok %s", str(r.ok))
    assert r.ok
    yield http_endpoint_url
    p.terminate()
    try:
        p.wait(timeout=1.0)
        logging.info('clean terminate')
    except subprocess.TimeoutExpired as e:
        logging.error('KILL')
        p.kill()
        p.wait()

@pytest.mark.skipif(should_skip_endpoint_test, reason='SKIP_ENDPOINT_TEST set')
def test_ver(http_endpoint):
    r = requests.post(http_endpoint+'/ver')
    assert r.status_code == 200
    r = requests.get(http_endpoint+'/ver')
    assert r.status_code == 200
    r = requests.get(http_endpoint+'/verx')
    assert r.status_code == 404


@pytest.mark.skipif(should_skip_endpoint_test, reason='SKIP_ENDPOINT_TEST set')
def test_ver(http_endpoint):
    r = requests.get(http_endpoint+'/api/ver')
    assert r.status_code == 200
    val = r.json()
    assert val['__version__'] == __version__
    assert val['sys_version'] == sys.version


@pytest.mark.skipif(should_skip_endpoint_test, reason='SKIP_ENDPOINT_TEST set')
def test_add(http_endpoint):
    r = requests.post(http_endpoint+'/api/add', {'a': 10, 'b': 20})
    print("r=",r)
    print("r.text=",r.text)
    assert r.status_code == 200
    assert r.json() == {'result': 30, 'error': False}


@pytest.mark.skipif(should_skip_endpoint_test, reason='SKIP_ENDPOINT_TEST set')
def test_api_key(http_endpoint, api_key):
    r = requests.post(http_endpoint+'/api/check-api_key',
                      {'api_key': api_key})
    if (r.status_code != 200):
        raise RuntimeError(f"r.status_code={r.status_code}  r.text={r.text}")
    assert r.status_code == 200
    assert r.json()['error'] == False
    assert r.json()['userinfo']['name'] == 'Test User Name'

    r = requests.post(http_endpoint+'/api/check-api_key',
                      {'api_key': 'invalid'})
    assert r.status_code == 200
    assert r.json()['error'] == True

@pytest.mark.skipif(should_skip_endpoint_test, reason='SKIP_ENDPOINT_TEST set')
def test_api_get_logs(http_endpoint, new_user):
    api_key = new_user[user_test.API_KEY]
    user_id = new_user[user_test.USER_ID]

    r = requests.post(http_endpoint+'/api/get-logs',
                      {'api_key': api_key, 'log_user_id' : user_id})
    if (r.status_code != 200):
        raise RuntimeError(f"r.status_code={r.status_code}  r.text={r.text}")
    assert r.status_code == 200
    obj = r.json()
    assert obj['error'] == False
    assert 'logs' in obj


# need /api/register
# need /api/resend-link
# need /api/bulk-register


#@pytest.mark.skipif(should_skip_endpoint_test, reason='SKIP_ENDPOINT_TEST set')
#def test_upload_movie_frame_by_frame(http_endpoint, api_key):
#    """This tests creating a movie and uploading
#    three frames using the frame-by-frame upload using an already existing test user"""
#
#    assert len(FRAME_FILES) > 0
#    post_data = {'api_key': api_key, 'title': 'Test Title at ' +
#                 time.asctime(), 'description': 'test-upload'}
#    r = requests.post(http_endpoint+'/api/new-movie', post_data)
#    res = r.json()
#    assert res['error'] == False
#    movie_id = res['movie_id']
#    for frame_file in FRAME_FILES:
#        m = FRAME_RE.search(frame_file)
#        frame_number = int(m.group(1))
#        print("uploading frame ", frame_number)
#        with open(frame_file, 'rb') as f:
#            r = requests.post(http_endpoint+'/api/new-frame', {
#                'api_key': api_key,
#                'movie_id': movie_id,
#                'frame_msec': frame_number*200,
#                'frame_base64_data': base64.b64encode(f.read())})
#            print("r.text=", r.text, file=sys.stderr)
#            if r.json()['error']:
#                raise RuntimeError(json.dumps(r.json(), indent=4))
#
#    # Now delete the movie
#    r = requests.post(http_endpoint+'/api/delete-movie',
#                      { 'api_key': api_key,
#                        'movie_id': movie_id
#                       })
#    res = r.json()
#    assert res['error'] == False
#
#    # Purge the movie (to clean up)
#    db.purge_movie(movie_id = movie_id)

@pytest.mark.skip(reason='not working yet')
def test_upload_movie_data(http_endpoint, api_key):
    """This tests creating a movie and uploading the entire thing using base64 encoding and the existing test user"""
    assert len(FRAME_FILES) > 0
    with open(TEST_MOVE_FILENAME, 'rb') as f:
        movie_base64_data = base64.b64encode(f.read())
    post_data = {'api_key': api_key,
                 'title': 'Test Title at '+time.asctime(),
                 'description': 'test-upload',
                 'movie_base64_data': movie_base64_data}
    r = requests.post(http_endpoint+'/api/new-movie', post_data)
    res = r.json()
    assert res['error'] == False
    movie_id = res['movie_id']

    # Now delete the movie
    post_data2 = {'api_key': TEST_USER_APIKEY,
                  'movie_id': movie_id}
    r = requests.post(http_endpoint+'/api/delete-movie', post_data2)
    res = r.json()
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
