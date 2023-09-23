"""endpoint_test.py - these tests use http to a running endpoint.

The fixutre allows that running endpoint to be one that is running locally.
"""


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

sys.path.append( dirname(dirname(abspath(__file__))))

from paths import TEST_DIR, BOTTLE_APP_PATH

import requests
TEST_ENDPOINT = os.environ['TEST_ENDPOINT']
TEST_USER_APIKEY = os.environ['TEST_USER_APIKEY']
FRAME_FILES = glob.glob( os.path.join(TEST_DIR, "data", "frame_*.jpg") )
FRAME_RE = re.compile(r"frame_(\d+).jpg")
MOVIE_FILE_NAME = os.path.join(TEST_DIR, "data","2019-07-31 plantmovie.mov")
SKIP_ENDPOINT_TEST = (os.environ.get('SKIP_ENDPOINT_TEST','NO') == 'YES')

HTTP_PORT = 8008

@pytest.fixture
def http_endpoint():
    """Create an endpoint running on localhost."""
    p = subprocess.Popen([sys.executable, BOTTLE_APP_PATH, '--port', str(HTTP_PORT)],stderr=subprocess.PIPE,encoding='utf-8')
    line = p.stderr.readline()
    assert 'server starting up' in line
    line2 = p.stderr.readline()
    assert 'Listening on' in line2
    line3 = p.stderr.readline()
    assert 'Hit Ctrl-C to quit.' in line3
    yield f'http://localhost:{HTTP_PORT}'
    p.terminate()
    try:
        p.wait(timeout=1.0)
    except subprocess.TimeoutExpired as e:
        p.kill()
        p.wait()


def test_ver(http_endpoint):
    TEST_ENDPOINT = http_endpoint
    r = requests.post( TEST_ENDPOINT+'/ver')
    assert r.status_code==200
    r = requests.get( TEST_ENDPOINT+'/ver')
    assert r.status_code==200
    r = requests.get( TEST_ENDPOINT+'/verx')
    assert r.status_code==404

@pytest.mark.skipif( SKIP_ENDPOINT_TEST , reason='SKIP_ENDPOINT_TEST=YES')
def test_add():
    r = requests.post( TEST_ENDPOINT+'/api/add', {'a':10, 'b':20})
    assert r.status_code == 200
    assert r.json() == {'result':30, 'error':False}

@pytest.mark.skipif( SKIP_ENDPOINT_TEST , reason='SKIP_ENDPOINT_TEST=YES')
def test_api_key():
    r = requests.post( TEST_ENDPOINT+'/api/check-api_key', {'api_key': TEST_USER_APIKEY} )
    if (r.status_code != 200):
        logging.error("TEST_ENDPOINT=%s",TEST_ENDPOINT)
        raise RuntimeError(f"r.status_code={r.status_code}  r.text={r.text}")
    assert r.status_code == 200
    assert r.json()['error'] == False
    assert r.json()['userinfo']['name'] == 'Test User'

    r = requests.post( TEST_ENDPOINT+'/api/check-api_key', {'api_key': TEST_USER_APIKEY+'invalid'} )
    assert r.status_code == 200
    assert r.json()['error'] == True


@pytest.mark.skip(reason='not working yet')
def test_upload_movie_frame_by_frame():
    """This tests creating a movie and uploading three frames using the frame-by-frame upload using an already existing test user"""
    assert len(FRAME_FILES)>0
    post_data = {'api_key': TEST_USER_APIKEY, 'title':'Test Title at '+time.asctime(), 'description':'Test Upload'}
    r = requests.post( TEST_ENDPOINT+'/api/new-movie', post_data )
    res = r.json()
    assert res['error']==False
    movie_id = res['movie_id']
    for frame_file in FRAME_FILES:
        m = FRAME_RE.search(frame_file)
        frame_number = int(m.group(1))
        print("uploading frame ",frame_number)
        with open(frame_file,'rb') as f:
            r = requests.post( TEST_ENDPOINT+'/api/new-frame', {
                'api_key': TEST_USER_APIKEY,
                'movie_id':movie_id,
                'frame_msec':frame_number*200,
                'frame_base64_data':base64.b64encode(f.read()) })
            print("r.text=",r.text,file=sys.stderr)
            if r.json()['error']:
                raise RuntimeError(json.dumps(r.json(), indent=4))

    # Now delete the movie
    r = requests.post( TEST_ENDPOINT+'/api/delete-movie', {
        'api_key': TEST_USER_APIKEY,
        'movie_id':movie_id })

    # Now delete the movie
    post_data2 = {'api_key': TEST_USER_APIKEY,
                 'movie_id': movie_id}
    r = requests.post( TEST_ENDPOINT+'/api/delete-movie', post_data2 )
    res = r.json()
    assert res['error']==False

@pytest.mark.skip(reason='not working yet')
def test_upload_movie_data():
    """This tests creating a movie and uploading the entire thing using base64 encoding and the existing test user"""
    assert len(FRAME_FILES)>0
    with open(MOVIE_FILE_NAME,'rb') as f:
        movie_base64_data = base64.b64encode(f.read())
        post_data = {'api_key': TEST_USER_APIKEY, 'title':'Test Title at '+time.asctime(), 'description':'Test Upload',
                     'movie_base64_data': movie_base64_data }
    r = requests.post( TEST_ENDPOINT+'/api/new-movie', post_data )
    res = r.json()
    assert res['error']==False
    movie_id = res['movie_id']

    # Now delete the movie
    post_data2 = {'api_key': TEST_USER_APIKEY,
                 'movie_id': movie_id}
    r = requests.post( TEST_ENDPOINT+'/api/delete-movie', post_data2 )
    res = r.json()
    assert res['error']==False
