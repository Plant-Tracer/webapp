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
from requests.adapters import HTTPAdapter

# TEST_ENDPOINT = os.environ['TEST_ENDPOINT']
TEST_USER_APIKEY = os.environ['TEST_USER_APIKEY']
FRAME_FILES = glob.glob( os.path.join(TEST_DIR, "data", "frame_*.jpg") )
FRAME_RE = re.compile(r"frame_(\d+).jpg")
MOVIE_FILE_NAME = os.path.join(TEST_DIR, "data","2019-07-31 plantmovie.mov")
SKIP_ENDPOINT_TEST = (os.environ.get('SKIP_ENDPOINT_TEST','NO') == 'YES')
SKIP_ENDPOINT_TEST = True

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
    p = subprocess.Popen([sys.executable, BOTTLE_APP_PATH, '--port', str(port)],stderr=subprocess.PIPE,encoding='utf-8')
    for want in ['server starting up','Listening on','Hit Ctrl-C to quit.']:
        line = p.stderr.readline()
        logging.info('%s',line)
        assert want in line
    http_endpoint = f'http://127.0.0.1:{port}'
    # Make sure it is working and retry up to 10 times

    s = requests.Session()
    s.mount( http_endpoint+'/ver', HTTPAdapter(max_retries=5))
    logging.info("Server running")
    yield http_endpoint
    p.terminate()
    try:
        p.wait(timeout=1.0)
        logging.info('clean terminate')
    except subprocess.TimeoutExpired as e:
        logging.error('KILL')
        p.kill()
        p.wait()
    time.sleep(1)


@pytest.mark.skipif(SKIP_ENDPOINT_TEST and False, reason='SKIP_ENDPOINT_TEST set')
def test_ver(http_endpoint):
    r = requests.post( http_endpoint+'/ver')
    assert r.status_code==200
    r = requests.get( http_endpoint+'/ver')
    assert r.status_code==200
    r = requests.get( http_endpoint+'/verx')
    assert r.status_code==404

@pytest.mark.skipif(SKIP_ENDPOINT_TEST and False, reason='SKIP_ENDPOINT_TEST set')
def test_add(http_endpoint):
    r = requests.post( http_endpoint+'/api/add', {'a':10, 'b':20})
    assert r.status_code == 200
    assert r.json() == {'result':30, 'error':False}

@pytest.mark.skipif(SKIP_ENDPOINT_TEST, reason='SKIP_ENDPOINT_TEST set')
def test_api_key( http_endpoint ):
    r = requests.post( http_endpoint+'/api/check-api_key', {'api_key': TEST_USER_APIKEY} )
    if (r.status_code != 200):
        logging.error("http_endpoint=%s",http_endpoint)
        raise RuntimeError(f"r.status_code={r.status_code}  r.text={r.text}")
    assert r.status_code == 200
    assert r.json()['error'] == False
    assert r.json()['userinfo']['name'] == 'Test User'

    r = requests.post( http_endpoint+'/api/check-api_key', {'api_key': TEST_USER_APIKEY+'invalid'} )
    assert r.status_code == 200
    assert r.json()['error'] == True

@pytest.mark.skipif(SKIP_ENDPOINT_TEST, reason='SKIP_ENDPOINT_TEST set')
def test_upload_movie_frame_by_frame( http_endpoint ):
    """This tests creating a movie and uploading three frames using the frame-by-frame upload using an already existing test user"""
    assert len(FRAME_FILES)>0
    post_data = {'api_key': TEST_USER_APIKEY, 'title':'Test Title at '+time.asctime(), 'description':'Test Upload'}
    r = requests.post( http_endpoint+'/api/new-movie', post_data )
    res = r.json()
    assert res['error']==False
    movie_id = res['movie_id']
    for frame_file in FRAME_FILES:
        m = FRAME_RE.search(frame_file)
        frame_number = int(m.group(1))
        print("uploading frame ",frame_number)
        with open(frame_file,'rb') as f:
            r = requests.post( http_endpoint+'/api/new-frame', {
                'api_key': TEST_USER_APIKEY,
                'movie_id':movie_id,
                'frame_msec':frame_number*200,
                'frame_base64_data':base64.b64encode(f.read()) })
            print("r.text=",r.text,file=sys.stderr)
            if r.json()['error']:
                raise RuntimeError(json.dumps(r.json(), indent=4))

    # Now delete the movie
    r = requests.post( http_endpoint+'/api/delete-movie', {
        'api_key': TEST_USER_APIKEY,
        'movie_id':movie_id })

    # Now delete the movie
    post_data2 = {'api_key': TEST_USER_APIKEY,
                 'movie_id': movie_id}
    r = requests.post( http_endpoint+'/api/delete-movie', post_data2 )
    res = r.json()
    assert res['error']==False

@pytest.mark.skip(reason='not working yet')
def test_upload_movie_data( http_endpoint ):
    """This tests creating a movie and uploading the entire thing using base64 encoding and the existing test user"""
    assert len(FRAME_FILES)>0
    with open(MOVIE_FILE_NAME,'rb') as f:
        movie_base64_data = base64.b64encode(f.read())
        post_data = {'api_key': TEST_USER_APIKEY, 'title':'Test Title at '+time.asctime(), 'description':'Test Upload',
                     'movie_base64_data': movie_base64_data }
    r = requests.post( http_endpoint+'/api/new-movie', post_data )
    res = r.json()
    assert res['error']==False
    movie_id = res['movie_id']

    # Now delete the movie
    post_data2 = {'api_key': TEST_USER_APIKEY,
                 'movie_id': movie_id}
    r = requests.post( http_endpoint+'/api/delete-movie', post_data2 )
    res = r.json()
    assert res['error']==False
