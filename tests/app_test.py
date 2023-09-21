import pytest
import sys
import os
import bottle
import logging
import json

from os.path import abspath,dirname

# https://bottlepy.org/docs/dev/recipes.html#unit-testing-bottle-applications

from boddle import boddle

sys.path.append( dirname(dirname(abspath(__file__))))

import bottle_app
from paths import STATIC_DIR

API_KEY = os.getenv('TEST_USER_APIKEY')

def test_version():
    # With templates, res is just a string
    with boddle(params={}):
        res = bottle_app.func_ver()
        assert bottle_app.__version__ in res

def test_static_path():
    # Without templates, res is an HTTP response object with .body and .header and stuff
    with boddle(params={}):
        res = bottle_app.static_path('test.txt')
        assert open( os.path.join( STATIC_DIR, 'test.txt'), 'rb').read() == res.body.read()

def test_templates():
    # Test templates with and without an API_KEY
    with boddle(params={}):
        bottle_app.func_root()
        bottle_app.func_register()
        bottle_app.func_resend()
        bottle_app.func_tos()

        with pytest.raises(bottle.HTTPResponse):
            bottle_app.func_list()

        with pytest.raises(bottle.HTTPResponse):
            bottle_app.func_upload()

    with boddle(params={'api_key':API_KEY}):
        bottle_app.func_root()
        bottle_app.func_register()
        bottle_app.func_resend()
        bottle_app.func_list()
        bottle_app.func_upload()
        bottle_app.func_tos()

def test_check_api_key():
    # no parameter should generate error
    with boddle(params={}):
        r = bottle_app.api_check_api_key()
        assert r['error']==True

    # invalid API key should generate error
    with boddle(params={'api_key':'invalid'}):
        r = bottle_app.api_check_api_key()
        assert r['error']==True

    # valid key should generate no error
    with boddle(params={'api_key':API_KEY}):
        r = bottle_app.api_check_api_key()
        assert r['error']==False,f'API_KEY {API_KEY} should be valid'
