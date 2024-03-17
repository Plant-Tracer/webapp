"""
Tests for the application
"""


import pytest
import sys
import os
import bottle
import logging
import json
import subprocess
import uuid

from os.path import abspath, dirname

import xml.etree.ElementTree

# https://bottlepy.org/docs/dev/recipes.html#unit-testing-bottle-applications

from boddle import boddle

sys.path.append(dirname(dirname(abspath(__file__))))

from paths import STATIC_DIR,TEST_DATA_DIR
import db
import bottle_app
import auth

from user_test import new_course,new_user,API_KEY
from movie_test import new_movie

def test_version():
    # With templates, res is just a string
    with boddle(params={}):
        res = bottle_app.func_ver()
        assert bottle_app.__version__ in res

def test_is_true():
    assert bottle_app.is_true("Y") is True
    assert bottle_app.is_true("f") is False


def test_get_float(mocker):
    mocker.patch("bottle_app.get", return_value="3")
    assert bottle_app.get_float("key")==3
    mocker.patch("bottle_app.get", return_value="xxx")
    assert bottle_app.get_float("key",default=4)==4

def test_get_bool(mocker):
    mocker.patch("bottle_app.get", return_value="YES")
    assert bottle_app.get_bool("key")==True
    mocker.patch("bottle_app.get", return_value="xxx")
    assert bottle_app.get_bool("key",default=False)==False

def test_static_path():
    # Without templates, res is an HTTP response object with .body and .header and stuff
    with boddle(params={}):
        res = bottle_app.static_path('test.txt')
        assert open(os.path.join(STATIC_DIR, 'test.txt'),'rb').read() == res.body.read()


def test_icon():
    with boddle(params={}):
        res = bottle_app.favicon()
    assert open(os.path.join(STATIC_DIR, 'favicon.ico'), 'rb').read() == res.body.read()

#
# Test various error conditions

def test_error():
    """Make sure authentication errors result in the session being expired and the cookie being cleared."""
    with boddle(params={}):
        res = bottle_app.func_error()
    cookie_name = auth.cookie_name()
    assert "Session expired - You have been logged out" in res
    assert (f'Set-Cookie: {cookie_name}=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=-1; Path=/'
            in str(bottle.response))


# Note: mocker magically works if pytest-mock is installed
def test_api_key_null(mocker):
    mocker.patch('auth.get_user_api_key', return_value=None)
    with pytest.raises(bottle.HTTPResponse) as e:
        with boddle(params={}):
            res = bottle_app.func_list() # throws bottle.HTTPResponse
        assert e.value.status[0:3]=='303' and e.value.headers=={'Location':'/'}

    with pytest.raises(bottle.HTTPResponse) as e:
        bottle_app.get_user_dict() # throws bottle.HTTPResponse
        assert e.value.status[0:3]=='303' and e.value.headers=={'Location':'/'}


################################################################
# Validate HTML produced by templates below.
# https://stackoverflow.com/questions/35538/validate-xhtml-in-python
def test_templates(new_user):
    api_key = new_user[API_KEY]

    def dump_lines(text):
        for (ct, line) in enumerate(text.split("\n"), 1):
            logging.error("%s: %s",ct, line)

    def validate_html(html, include_text=None, exclude_text=None):
        '''xml.etree.ElementTree can't properly parse the htmlraise an error.'''
        try:
            doc = xml.etree.ElementTree.fromstring(html)
            if include_text is not None:
                if include_text not in html:
                    dump_lines(html)
                    raise RuntimeError(f"'{include_text}' not in text  {new_user}")
            if exclude_text is not None:
                if exclude_text in html:
                    dump_lines(html)
                    raise RuntimeError(f"'{exclude_text}' in text {new_user}")
            return
        except xml.etree.ElementTree.ParseError as e:
            dump_lines(html)
            invalid_fname = '/tmp/invalid-' + str(uuid.uuid4()) + '.html'
            logging.error(f"invalid html written to {invalid_fname}")
            with open( invalid_fname,"w") as f:
                f.write(html)
            try:
                # Run xmllint if it is present, but don't generate an error if it is not
                print("xmllint:")
                subprocess.call(['xmllint',invalid_fname])
            except FileNotFoundError:
                pass
            raise
        assert "404 Not Found" not in data

    # Test the test infrastructure
    with pytest.raises(xml.etree.ElementTree.ParseError):
        validate_html("<a><b> this is invalid HTML</a></b>")

    with pytest.raises(RuntimeError):
        validate_html("<p>one two three</p>",include_text="four")

    with pytest.raises(RuntimeError):
        validate_html("<p>one two three</p>",exclude_text="two")

    # Test templates without an API_KEY
    with boddle(params={}):
        # These work without an api_key
        validate_html(bottle_app.func_root())
        validate_html(bottle_app.func_about())
        with pytest.raises(bottle.HTTPResponse):
            bottle_app.func_audit()
        with pytest.raises(bottle.HTTPResponse):
            bottle_app.func_list()
        validate_html(bottle_app.func_login())
        validate_html(bottle_app.func_logout())
        validate_html(bottle_app.func_register())
        validate_html(bottle_app.func_resend())
        validate_html(bottle_app.func_tos())
        with pytest.raises(bottle.HTTPResponse):
            bottle_app.func_upload()
        with pytest.raises(bottle.HTTPResponse):
            bottle_app.func_users()
        validate_html("<pre>"+bottle_app.func_ver()+"\n</pre>")


    # Test templates to see if they work with an API key
    with boddle(params={'api_key': api_key}):
        validate_html(bottle_app.func_root())
        validate_html(bottle_app.func_about())
        validate_html(bottle_app.func_audit())
        validate_html(bottle_app.func_list(), exclude_text='Demo mode')
        validate_html(bottle_app.func_login())
        validate_html(bottle_app.func_logout())
        validate_html(bottle_app.func_register())
        validate_html(bottle_app.func_resend())
        validate_html(bottle_app.func_tos())
        validate_html(bottle_app.func_upload())
        validate_html(bottle_app.func_users())
        validate_html("<pre>"+bottle_app.func_ver()+"\n</pre>")

    # Test template to see if demo text appears
    demo_key = db.list_demo_users()[0]['api_key']
    with boddle(params={'api_key': demo_key}):
        validate_html(bottle_app.func_list(), include_text='Demo mode')

def test_check_api_key(new_user):
    api_key = new_user[API_KEY]
    # no parameter should generate error
    with boddle(params={}):
        r = bottle_app.api_check_api_key()
        assert r['error'] == True

    # invalid API key should generate error
    with boddle(params={'api_key': 'invalid'}):
        r = bottle_app.api_check_api_key()
        assert r['error'] == True

    # valid key should generate no error
    with boddle(params={'api_key': api_key}):
        r = bottle_app.api_check_api_key()
        assert r['error'] == False, f'API_KEY {API_KEY} should be valid'
