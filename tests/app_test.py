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

from app.paths import STATIC_DIR,TEST_DATA_DIR
from app import odb
from app import bottle_api
from app import bottle_app
from app import auth
from app import apikey

from app.odb import VERSION, API_KEY, MOVIE_ID, USER_ID
from fixtures.local_aws import local_ddb, local_s3, new_course, new_movie, api_key
from fixtures.app_client import client

def test_version(client):  # Use the app fixture
    response = client.get('/ver')
    assert bottle_app.__version__ in response.text

def test_get_float(mocker):
    mocker.patch("app.bottle_api.get", return_value="3")
    assert bottle_api.get_float("key")==3
    mocker.patch("app.bottle_api.get", return_value="xxx")
    assert bottle_api.get_float("key",default=4)==4

def test_get_bool(mocker):
    mocker.patch("app.bottle_api.get", return_value="YES")
    assert bottle_api.get_bool("key")==True
    mocker.patch("app.bottle_api.get", return_value="xxx")
    assert bottle_api.get_bool("key",default=False)==False
    mocker.patch("app.bottle_api.get", return_value=3.4)
    assert bottle_api.get_bool("key",default=True)==True


PLANTTRACER_JS = 'planttracer.js'
def test_static_path(client):
    response = client.get(f'/static/{PLANTTRACER_JS}')
    with open(os.path.join(STATIC_DIR, PLANTTRACER_JS),'r') as f:
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
def test_templates(client,new_course):
    api_key = new_course[API_KEY]

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
        for url in ['/','/about','/error','/audit','/list','/analyze','/debug','/login','/logout','/privacy','/register',
                    '/resend','/tos','/upload','/users']:
            include_text = None
            exclude_text = None
            if with_api_key==True and url=='/list':
                exclude_text = 'user_demo = 1;'
            if with_api_key:
                client.set_cookie( apikey.cookie_name(), api_key)
            resp = client.get(url)
            logging.info('with_api_key=%s url=%s',with_api_key,url)
            if (not with_api_key) and (url in ['/audit','/list','/analyze', '/upload', '/users']):
                # These should all be error conditions because they require being logged in
                logging.debug('not checking html')
                assert resp.text[0]=='{' # should be an error
                assert resp.status_code!=200
            else:
                validate_html( url, resp.text, include_text = include_text, exclude_text = exclude_text )


def test_api_edit_movie(new_movie,client):
    # Verifies that editing the movie version has updated
    api_key = new_movie[API_KEY]
    user_id  = new_movie[USER_ID]
    movie_id = new_movie[MOVIE_ID]

    movie = odb.get_movie(movie_id = movie_id)
    assert movie[VERSION] == 1  # because it had data assigned to it

    movie_metadata = odb.get_movie_metadata(user_id=user_id, movie_id=movie_id)[0]
    logging.debug("first version=%s", movie_metadata[VERSION])
    resp = client.post('/api/edit-movie',
                       data={'api_key': api_key,
                             'movie_id': movie_id,
                             'action' : 'bad-action'})
    assert resp.json['error']==True
    movie = odb.get_movie(movie_id = movie_id)
    assert movie[VERSION] == 1  # because it was not updated

    resp = client.post('/api/edit-movie',
                       data={'api_key': api_key,
                             'movie_id': movie_id,
                             'action' : 'rotate90cw'})
    assert resp.json['error']==False

    movie = odb.get_movie(movie_id = movie_id)
    assert movie[VERSION] == 2  # because it was edited


    # Now test the user access
    movie_metadata2 = odb.get_movie_metadata(user_id=user_id, movie_id=movie_id)[0]
    logging.debug("second version=%s", movie_metadata2[VERSION])
    # Make sure that the version number incremented
    logging.debug("movie_metadata=%s movie_metadata2=%s",movie_metadata,movie_metadata2)
    assert movie_metadata['version'] +1 == movie_metadata2['version']
