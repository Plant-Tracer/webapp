import sys
import os
from os.path import dirname, abspath
sys.path.append( dirname(dirname(abspath(__file__))))

import requests
TEST_ENDPOINT = os.environ['TEST_ENDPOINT']

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
