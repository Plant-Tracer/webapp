"""
Tests for the application
"""


import os
import subprocess
import uuid

import pytest
import html5validate

from app.paths import STATIC_DIR
from app import odb
from app import flask_api
from app import flask_app
from app import apikey

from app.odb import VERSION, API_KEY, MOVIE_ID, USER_ID

# Fixtures are imported in conftest.py
from app.constants import logger

def test_version(client):  # Use the app fixture
    response = client.get('/ver')
    assert flask_app.__version__ in response.text


# These check type conversion

def test_get_float(mocker):
    mock_get = mocker.patch("app.flask_api.get")
    mock_get.return_value = "3"
    assert flask_api.get_float("key") == 3.0  # Note: 3.0 is a float, 3 is an int

    mocker.patch("app.flask_api.get", return_value="3")
    assert flask_api.get_float("key")==3
    mocker.patch("app.flask_api.get", return_value="xxx")
    assert flask_api.get_float("key",default=4)==4

def test_get_bool(mocker):
    mocker.patch("app.flask_api.get", return_value="YES")
    assert flask_api.get_bool("key") is True
    mocker.patch("app.flask_api.get", return_value="xxx")
    assert flask_api.get_bool("key",default=False) is False
    mocker.patch("app.flask_api.get", return_value=3.4)
    assert flask_api.get_bool("key",default=True) is True


PLANTTRACER_JS = 'planttracer.js'
def test_static_path(client):
    response = client.get(f'/static/{PLANTTRACER_JS}')
    # When COLLECT_JS_COVERAGE is enabled, Flask serves instrumented files
    # which will differ from the original, so we just check the file is served
    assert response.status_code == 200
    assert len(response.text) > 0
    
    # If not in coverage mode, verify exact match
    import os
    if os.environ.get('COLLECT_JS_COVERAGE', '').lower() not in ('1', 'true', 'yes'):
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
    assert set_cookie_header == f'Set-Cookie: {cookie_name}=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=-1; Path=/'

# make sure we get no api_key with a bad request
@pytest.mark.skip(reason='authentication not yet working')
def test_null_api_key(mocker):
    mocker.patch("flask.request.values.get", return_value=None)
    assert apikey.get_user_api_key() is None


################################################################
# Validate HTML produced by templates below.
# https://stackoverflow.com/questions/35538/validate-xhtml-in-python
def test_templates(client,new_course):
    api_key = new_course[API_KEY]

    def dump_lines(text):
        for (ct, line) in enumerate(text.split("\n"), 1):
            logger.error("%s: %s",ct, line)

    def validate_html(url, html, include_text=None, exclude_text=None):
        '''If html5validate can't properly properly parse the htmlraise an error.'''
        try:
            html5validate.validate(html)
            if include_text is not None:
                if include_text not in html:
                    dump_lines(html)
                    raise RuntimeError(f"'{include_text}' not in text")
            if exclude_text is not None:
                if exclude_text in html:
                    dump_lines(html)
                    raise RuntimeError(f"'{exclude_text}' in text")
            return
        except html5validate.ParseError as e:
            logger.error("*****************************************************")
            logger.error("url=%s error=%s",url,e)
            dump_lines(html)
            invalid_fname = '/tmp/invalid-' + str(uuid.uuid4()) + '.html'
            logger.error("invalid html written to %s",invalid_fname)
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
            if with_api_key is True and url=='/list':
                exclude_text = 'user_demo = true;'
            if with_api_key:
                client.set_cookie( apikey.cookie_name(), api_key)
            resp = client.get(url)
            logger.info('with_api_key=%s url=%s',with_api_key,url)
            if (not with_api_key) and (url in ['/audit','/list','/analyze', '/upload', '/users']):
                # These should all be error conditions because they require being logged in
                logger.debug('not checking the html %s',resp.text)
                assert resp.status_code!=200 # should be an error
            else:
                validate_html( url, resp.text, include_text = include_text, exclude_text = exclude_text )


def test_api_edit_movie(new_movie, client):
    """verify that new_movie fixture is set up properly and that we can use edit-movie"""
    api_key = new_movie[API_KEY]
    movie_id = new_movie[MOVIE_ID]

    movie = odb.get_movie(movie_id = movie_id)
    movie_metadata = odb.get_movie_metadata(movie_id=movie_id)
    logger.debug("movie=%s movie_metadata=%s",movie,movie_metadata)

    assert movie[VERSION] == 1  # because it had data assigned to it
    assert movie['user_id'] == new_movie[USER_ID]

    userdict = apikey.user_dict_for_api_key(new_movie[API_KEY])
    assert userdict[USER_ID]==new_movie[USER_ID],f"userdict={userdict} new_movie={new_movie}"


    ### This one should fail
    data = {'api_key': api_key, 'movie_id': movie_id, 'action' : 'bad-action'}
    resp = client.post('/api/edit-movie', data=data)
    assert resp.json['error'] is True,f"resp.json={resp.json} data={data}"
    movie = odb.get_movie(movie_id = movie_id)
    assert movie[VERSION] == 1  # because it was not updated

    ### This one should also
    data = {'api_key': "bad-api-key", 'movie_id': movie_id, 'action' : 'rotate90cw'}
    resp = client.post('/api/edit-movie', data=data)
    assert resp.json['error'] is True,f"resp.json={resp.json} data={data}"
    movie = odb.get_movie(movie_id = movie_id)
    assert movie[VERSION] == 1  # because it was not updated

    ### This one should be successful
    data = {'api_key': api_key, 'movie_id': movie_id, 'action' : 'rotate90cw'}
    resp = client.post('/api/edit-movie', data=data)
    assert resp.json['error'] is False,f"resp.json={resp.json} data={data}"
    movie = odb.get_movie(movie_id = movie_id)
    assert movie[VERSION] == 2,f"{movie}"  # because it was edited

    # Now test the user access
    movie_metadata2 = odb.get_movie_metadata(movie_id=movie_id)
    logger.debug("movie_metadata=%s movie_metadata2=%s",movie_metadata,movie_metadata2)
    # Make sure that the version number incremented
    assert movie_metadata['version'] +1 == movie_metadata2['version'],f"{movie_metadata} / {movie_metadata2}"
