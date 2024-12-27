"""
Tests for the application
"""


import pytest
import sys
import os
import logging
import json
import subprocess
import uuid

import xml.etree.ElementTree

from deploy.paths import STATIC_DIR,TEST_DATA_DIR
import deploy.db as db
import deploy.bottle_api as bottle_api
import deploy.bottle_app as bottle_app
import deploy.auth as auth
import deploy.apikey as apikey

from user_test import new_course,new_user,API_KEY,MOVIE_ID
from movie_test import new_movie
from fixtures.app_client import client

def test_version(client):  # Use the app fixture
    response = client.get('/ver')
    assert bottle_app.__version__ in response.text

def test_get_float(mocker):
    mocker.patch("deploy.bottle_api.get", return_value="3")
    assert bottle_api.get_float("key")==3
    mocker.patch("deploy.bottle_api.get", return_value="xxx")
    assert bottle_api.get_float("key",default=4)==4

def test_get_bool(mocker):
    mocker.patch("deploy.bottle_api.get", return_value="YES")
    assert bottle_api.get_bool("key")==True
    mocker.patch("deploy.bottle_api.get", return_value="xxx")
    assert bottle_api.get_bool("key",default=False)==False
    mocker.patch("deploy.bottle_api.get", return_value=3.4)
    assert bottle_api.get_bool("key",default=True)==True


def test_static_path(client):
    response = client.get('/static/test.txt')
    with open(os.path.join(STATIC_DIR, 'test.txt'),'r') as f:
        assert f.read() == response.text

    # Test file not found
    response = client.get('/static/no-file')
    assert response.status_code==404

#
# Test various error conditions

@pytest.mark.skip(reason='authentication not yet working')
def test_error(client):
    """Make sure authentication errors result in the session being expired and the cookie being cleared."""
    response = client.post('/api/list-movies',
                           data = {'api_key':'invalid'})

    cookie_name = apikey.cookie_name()
    set_cookie_header = response.headers.get('Set-Cookie')
    assert set_cookie_header == 'Set-Cookie: {cookie_name}=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=-1; Path=/'

# make sure we get no api_key with a bad request
@pytest.mark.skip(reason='authentication not yet working')
def test_null_api_key(mocker):
    mocker.patch("flask.request.values.get", return_value=None)
    assert apikey.get_user_api_key() == None


################################################################
# Validate HTML produced by templates below.
# https://stackoverflow.com/questions/35538/validate-xhtml-in-python
def test_templates(client,new_user):
    api_key = new_user[API_KEY]

    def dump_lines(text):
        for (ct, line) in enumerate(text.split("\n"), 1):
            logging.error("%s: %s",ct, line)

    def validate_html(url, html, include_text=None, exclude_text=None):
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
            logging.error("url=%s error=%s",url,e)
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

    for with_api_key in [False,True]:
        if with_api_key:
            client.set_cookie('localhost','api_key',api_key)
        for url in ['/','/about','/error','/audit','/list','/analyze','/debug','/login','/logout','/privacy','/register',
                    '/resend','/tos','/upload','/users']:
            include_text = None
            exclude_text = None
            if with_api_key==True and url=='/list':
                exclude_text = 'user_demo = 1;'
            resp = client.get(url)
            logging.info('with_api_key=%s url=%s',with_api_key,url)
            if (not with_api_key) and (url in ['/audit','/list','/analyze', '/upload', '/users']):
                # These should all be error conditions because they require being logged in
                assert resp.text[0]=='{' # should be an error
                assert resp.status_code!=200
            else:
                validate_html( url, resp.text, include_text = include_text, exclude_text = exclude_text )


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
