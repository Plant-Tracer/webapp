import pytest
import sys
import os
import bottle
import logging
import json

from os.path import abspath, dirname

from lxml import etree

# https://bottlepy.org/docs/dev/recipes.html#unit-testing-bottle-applications

from boddle import boddle

sys.path.append(dirname(dirname(abspath(__file__))))

from paths import STATIC_DIR
import bottle_app

from user_test import new_course,new_user,API_KEY
from movie_test import new_movie

def test_version():
    # With templates, res is just a string
    with boddle(params={}):
        res = bottle_app.func_ver()
        assert bottle_app.__version__ in res


def test_static_path():
    # Without templates, res is an HTTP response object with .body and .header and stuff
    with boddle(params={}):
        res = bottle_app.static_path('test.txt')
        assert open(os.path.join(STATIC_DIR, 'test.txt'),'rb').read() == res.body.read()


def test_icon():
    with boddle(params={}):
        res = bottle_app.favicon()
    assert open(os.path.join(STATIC_DIR, 'favicon.ico'), 'rb').read() == res.body.read()

def test_error():
    with boddle(params={}):
        res = bottle_app.func_error()
    # TODO - we need to know that the response sent the clear-cooky header
    assert "Session expired - You have been logged out" in res


################################################################
# Validate HTML produced by templates below.
# https://stackoverflow.com/questions/35538/validate-xhtml-in-python
def validate_html(html):
    '''If lxml can properly parse the html, return the lxml representation.
    Otherwise raise.'''
    try:
        return etree.fromstring(html, etree.HTMLParser())
    except etree.XMLSyntaxError as e:
        print("invalid html:", file=sys.stderr)
        for (ct, line) in enumerate(html.split("\n"), 1):
            print(ct, line, file=sys.stderr)
        raise
    assert "404 Not Found" not in data

def test_templates(new_user):
    api_key = new_user[API_KEY]

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
        validate_html(bottle_app.func_ver())


    # Test templates to see if they work with an API key
    with boddle(params={'api_key': api_key}):
        validate_html(bottle_app.func_root())
        validate_html(bottle_app.func_about())
        validate_html(bottle_app.func_audit())
        validate_html(bottle_app.func_list())
        validate_html(bottle_app.func_login())
        validate_html(bottle_app.func_logout())
        validate_html(bottle_app.func_register())
        validate_html(bottle_app.func_resend())
        validate_html(bottle_app.func_tos())
        validate_html(bottle_app.func_upload())
        validate_html(bottle_app.func_users())
        validate_html(bottle_app.func_ver())

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
