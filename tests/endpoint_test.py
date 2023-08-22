import sys
import os
from os.path import dirname, abspath
import glob
import re
import time
import json
import base64
sys.path.append( dirname(dirname(abspath(__file__))))

MYDIR = dirname(abspath(__file__))

import requests
TEST_ENDPOINT = os.environ['TEST_ENDPOINT']
TEST_USER_APIKEY = os.environ['TEST_USER_APIKEY']
FRAME_FILES = glob.glob( os.path.join(MYDIR, "data", "frame_*.jpg") )
FRAME_RE = re.compile(r"frame_(\d+).jpg")

def test_ver():
    r = requests.post( TEST_ENDPOINT+'/ver')
    assert r.status_code==200
    r = requests.get( TEST_ENDPOINT+'/ver')
    assert r.status_code==200
    r = requests.get( TEST_ENDPOINT+'/verx')
    assert r.status_code==404

def test_add():
    r = requests.post( TEST_ENDPOINT+'/api/add', {'a':10, 'b':20})
    assert r.status_code == 200
    assert r.json() == {'result':30, 'error':False}

def test_api_key():
    r = requests.post( TEST_ENDPOINT+'/api/check-api_key', {'api_key': TEST_USER_APIKEY} )
    assert r.status_code == 200
    print(r.json())
    assert r.json()['userinfo']['username'] == 'Test User'

def test_upload_movie():
    assert len(FRAME_FILES)>0
    r = requests.post( TEST_ENDPOINT+'/api/new-movie', {'api_key': TEST_USER_APIKEY, 'title':'Test Title at '+time.asctime(), 'description':'Test Upload'} )
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
                'frame_number':frame_number,
                'frame_msec':frame_number*200,
                'frame_base64_data':base64.b64encode(f.read()) })
            print("r.text=",r.text,file=sys.stderr)
            if r.json()['error']:
                raise RuntimeError(json.dumps(r.json(), indent=4))
