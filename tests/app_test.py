import pytest
import sys
import os
import bottle
import warnings
import json

from os.path import abspath,dirname

# https://bottlepy.org/docs/dev/recipes.html#unit-testing-bottle-applications

from boddle import boddle
# from webtest import TestApp

sys.path.append( dirname(dirname(abspath(__file__))))

import bottle_app
from paths import STATIC_DIR

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
