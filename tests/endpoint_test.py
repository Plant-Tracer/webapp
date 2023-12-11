"""endpoint_test.py - these tests use http to a running endpoint.

The fixutre allows that running endpoint to be one that is running locally.
"""

from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import requests
from paths import TEST_DIR, BOTTLE_APP_PATH
import sys
import os
from os.path import dirname, abspath
import glob
import re
import time
import json
import base64
import pytest
import logging
import subprocess
import copy

sys.path.append(dirname(dirname(abspath(__file__))))

import db
from user_test import new_course, new_user, api_key

FRAME_FILES = glob.glob(os.path.join(TEST_DIR, "data", "frame_*.jpg"))
FRAME_RE = re.compile(r"frame_(\d+).jpg")
SKIP_ENDPOINT_TEST = (os.environ.get('SKIP_ENDPOINT_TEST', 'NO') == 'YES')
SKIP_ENDPOINT_TEST = False

HTTP_PORT = 8008


def next_port():
    global HTTP_PORT
    pt = HTTP_PORT
    HTTP_PORT += 1
    return pt


@pytest.fixture
def http_endpoint():
    """Create an endpoint running on localhost."""
    port = next_port()
    p = subprocess.Popen([sys.executable, BOTTLE_APP_PATH, '--port',
                         str(port)], stderr=subprocess.PIPE, encoding='utf-8')
    for want in ['server starting up', 'Listening on', 'Hit Ctrl-C to quit.']:
        line = p.stderr.readline()
        logging.info('%s', line)
        assert want in line
    http_endpoint_url = f'http://127.0.0.1:{port}'
    # Make sure it is working and retry up to 10 times

    s = requests.Session()
    s.mount(http_endpoint_url+'/ver',
            HTTPAdapter(max_retries=Retry(total=10, backoff_factor=0.2)))
    r = s.get(http_endpoint_url+'/ver')
    logging.info("Server running. r=%s", r)
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

@pytest.mark.skipif(SKIP_ENDPOINT_TEST, reason='SKIP_ENDPOINT_TEST set')
def test_ver(http_endpoint):
    r = requests.post(http_endpoint+'/ver')
    assert r.status_code == 200
    r = requests.get(http_endpoint+'/ver')
    assert r.status_code == 200
    r = requests.get(http_endpoint+'/verx')
    assert r.status_code == 404


@pytest.mark.skipif(SKIP_ENDPOINT_TEST, reason='SKIP_ENDPOINT_TEST set')
def test_add(http_endpoint):
    r = requests.post(http_endpoint+'/api/add', {'a': 10, 'b': 20})
    assert r.status_code == 200
    assert r.json() == {'result': 30, 'error': False}


@pytest.mark.skipif(SKIP_ENDPOINT_TEST, reason='SKIP_ENDPOINT_TEST set')
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


@pytest.mark.skipif(SKIP_ENDPOINT_TEST, reason='SKIP_ENDPOINT_TEST set')
def test_upload_movie_frame_by_frame(http_endpoint, api_key):
    """This tests creating a movie and uploading
    three frames using the frame-by-frame upload using an already existing test user"""

    assert len(FRAME_FILES) > 0
    post_data = {'api_key': api_key, 'title': 'Test Title at ' +
                 time.asctime(), 'description': 'test-upload'}
    r = requests.post(http_endpoint+'/api/new-movie', post_data)
    res = r.json()
    assert res['error'] == False
    movie_id = res['movie_id']
    for frame_file in FRAME_FILES:
        m = FRAME_RE.search(frame_file)
        frame_number = int(m.group(1))
        print("uploading frame ", frame_number)
        with open(frame_file, 'rb') as f:
            r = requests.post(http_endpoint+'/api/new-frame', {
                'api_key': api_key,
                'movie_id': movie_id,
                'frame_msec': frame_number*200,
                'frame_base64_data': base64.b64encode(f.read())})
            print("r.text=", r.text, file=sys.stderr)
            if r.json()['error']:
                raise RuntimeError(json.dumps(r.json(), indent=4))

    # Now delete the movie
    r = requests.post(http_endpoint+'/api/delete-movie',
                      { 'api_key': api_key,
                        'movie_id': movie_id
                       })
    res = r.json()
    assert res['error'] == False

    # Purge the movie (to clean up)
    db.purge_movie(movie_id = movie_id)

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
