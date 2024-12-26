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

import xml.etree.ElementTree

from flask import Flask

# https://bottlepy.org/docs/dev/recipes.html#unit-testing-bottle-applications

from deploy.paths import STATIC_DIR,TEST_DATA_DIR
import deploy.db as db
import deploy.bottle_api as bottle_api
import deploy.bottle_app as bottle_app
import deploy.auth as auth

from user_test import new_course,new_user,API_KEY,MOVIE_ID
from movie_test import new_movie


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app

def test_version(app):
    # With templates, res is just a string
    with app.test_client() as client:
        response = client.get('/version.txt')
        assert bottle_app.__version__ in response.text

def test_is_true():
    assert bottle_api.is_true("Y") is True
    assert bottle_api.is_true("f") is False

def test_get_float(mocker):
    mocker.patch("bottle_api.get", return_value="3")
    assert bottle_api.get_float("key")==3
    mocker.patch("bottle_api.get", return_value="xxx")
    assert bottle_api.get_float("key",default=4)==4

def test_get_bool(mocker):
    mocker.patch("bottle_api.get", return_value="YES")
    assert bottle_api.get_bool("key")==True
    mocker.patch("bottle_api.get", return_value="xxx")
    assert bottle_api.get_bool("key",default=False)==False
    mocker.patch("bottle_api.get", return_value=3.4)
    assert bottle_api.get_bool("key",default=True)==True


def test_static_path(app):
    with app.test_client() as client:
        response = client.get('/static/test.txt')
        assert open(os.path.join(STATIC_DIR, 'test.txt'),'rb').read() == response.text

    # Test file not found
    with app.test_client() as client:
        response = client.get('/static/no-file')
        assert response.status_code==404

#
# Test various error conditions

def test_error(app):
    """Make sure authentication errors result in the session being expired and the cookie being cleared."""
    with app.test_client() as client:
        response = client.post('/api/list-movies',
                               data = {'api_key':'invalid'})

    cookie_name = apikey.cookie_name()
    set_cookie_header = response.headers.get('Set-Cookie')
    assert set_cookie_header == 'Set-Cookie: {cookie_name}=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=-1; Path=/'


# make sure we get no api_key with a bad request
def test_null_api_key(mocker):
    mocker.patch("bottle.request.query.get", return_value=None)
    assert auth.get_user_api_key() == None




"""

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
                    raise RuntimeError(f"'{include_text}' not in text {new_user}")
            if exclude_text is not None:
                if exclude_text in html:
                    dump_lines(html)
                    raise RuntimeError(f"'{exclude_text}' in text {new_user}")
            return
        except xml.etree.ElementTree.ParseError as e:
            logging.error(e)
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
        validate_html(bottle_app.func_privacy())
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
        validate_html(bottle_app.func_list(), exclude_text='user_demo = 1;')
        validate_html(bottle_app.func_login())
        validate_html(bottle_app.func_logout())
        validate_html(bottle_app.func_register())
        validate_html(bottle_app.func_resend())
        validate_html(bottle_app.func_privacy())
        validate_html(bottle_app.func_tos())
        validate_html(bottle_app.func_upload())
        validate_html(bottle_app.func_users())
        validate_html("<pre>"+bottle_app.func_ver()+"\n</pre>")

    # Test template to see if demo text appears when using a demo API key
    # but only if there is a demo user in the database
    demo_users = db.list_demo_users()
    if demo_users:
        user = demo_users[0]
        demo_api_key = db.make_new_api_key(email=user['email'])
        with boddle(params={'api_key': demo_api_key}):
            validate_html(bottle_app.func_list(), include_text='user_demo = 1;')
        db.delete_api_key(demo_api_key)
    else:
        logging.warning("no demo users; cannot test demo mode text")

def test_check_api_key(new_user):
    api_key = new_user[API_KEY]
    # no parameter should generate error
    with boddle(params={}):
        r = bottle_api.api_check_api_key()
        assert r['error'] == True

    # invalid API key should generate error
    with boddle(params={'api_key': 'invalid'}):
        r = bottle_api.api_check_api_key()
        assert r['error'] == True

    # valid key should generate no error
    with boddle(params={'api_key': api_key}):
        r = bottle_api.api_check_api_key()
        assert r['error'] == False, f'API_KEY {API_KEY} should be valid'

def test_api_edit_movie(new_movie):
    # Verifies that editing the movie version has updated
    api_key = new_movie[API_KEY]
    movie_id = new_movie[MOVIE_ID]
    movie = db.Movie(movie_id = movie_id)
    movie_metadata = movie.metadata
    with boddle(params={'api_key': api_key,
                        'movie_id': movie.movie_id,
                        'action' : 'bad-action'}):
        r = bottle_api.api_edit_movie()
        assert r['error']==True

    with boddle(params={'api_key': api_key,
                        'movie_id': movie.movie_id,
                        'action' : 'rotate90cw'}):
        r = bottle_api.api_edit_movie()
        assert r['error']==False
    movie_metadata2 = movie.metadata
    # Make sure that the version number incremented
    assert movie_metadata['version'] +1 == movie_metadata2['version']
"""
