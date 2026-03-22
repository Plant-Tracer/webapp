"""
Tests for the application
"""

import os
import subprocess
import uuid

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
    if os.environ.get('COLLECT_JS_COVERAGE', '').lower() not in ('1', 'true', 'yes'):
        with open(os.path.join(STATIC_DIR, PLANTTRACER_JS),'r') as f:
            assert f.read() == response.text

    # Test file not found
    response = client.get('/static/no-file')
    assert response.status_code==404

#
# Test various error conditions

def test_error(client, local_ddb, local_s3):
    """Make sure authentication errors result in the session being expired and the cookie being cleared."""
    response = client.post('/api/list-movies', data={'api_key': 'invalid'})

    assert response.status_code == 403
    cookie_name = apikey.cookie_name()
    set_cookie_header = response.headers.get('Set-Cookie')
    assert set_cookie_header is not None, "Expected Set-Cookie header to clear api_key"
    assert cookie_name in set_cookie_header
    # Empty value (clearing cookie): either quoted "" or bare ;
    assert '""' in set_cookie_header or "''" in set_cookie_header or f"{cookie_name}=;" in set_cookie_header
    assert "expires=" in set_cookie_header.lower() or "max-age=" in set_cookie_header.lower()

# make sure we get no api_key when nothing in request
def test_null_api_key(client):
    """get_user_api_key() returns None when no api_key in cookie or query (needs request context)."""
    with client.application.test_request_context():
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
    """Verify edit-movie: invalid action/auth fail; valid rotate90cw updates rotation_steps and triggers Lambda.
    VM only updates rotation_steps and clears tracking; rotation/zip run in Lambda."""
    api_key = new_movie[API_KEY]
    movie_id = new_movie[MOVIE_ID]

    movie = odb.get_movie(movie_id=movie_id)
    movie_metadata = odb.get_movie_metadata(movie_id=movie_id)
    logger.debug("movie=%s movie_metadata=%s", movie, movie_metadata)

    assert movie[VERSION] == 1  # fixture had data assigned
    assert movie['user_id'] == new_movie[USER_ID]

    userdict = apikey.user_dict_for_api_key(new_movie[API_KEY])
    assert userdict[USER_ID] == new_movie[USER_ID], f"userdict={userdict} new_movie={new_movie}"

    # Invalid action
    data = {'api_key': api_key, 'movie_id': movie_id, 'action': 'bad-action'}
    resp = client.post('/api/edit-movie', data=data)
    assert resp.json['error'] is True, f"resp.json={resp.json} data={data}"
    movie = odb.get_movie(movie_id=movie_id)
    assert movie.get('rotation_steps', 0) == 0

    # Invalid api_key
    data = {'api_key': "bad-api-key", 'movie_id': movie_id, 'action': 'rotate90cw'}
    resp = client.post('/api/edit-movie', data=data)
    assert resp.json['error'] is True, f"resp.json={resp.json} data={data}"

    # Success: rotation_steps omitted => 1 step
    data = {'api_key': api_key, 'movie_id': movie_id, 'action': 'rotate90cw'}
    resp = client.post('/api/edit-movie', data=data)
    assert resp.json['error'] is False, f"resp.json={resp.json} data={data}"
    movie = odb.get_movie(movie_id=movie_id)
    assert movie.get('rotation_steps') == 1, f"{movie}"

    # Success: rotation_steps=2
    data = {'api_key': api_key, 'movie_id': movie_id, 'action': 'rotate90cw', 'rotation_steps': '2'}
    resp = client.post('/api/edit-movie', data=data)
    assert resp.json['error'] is False, f"resp.json={resp.json} data={data}"
    movie = odb.get_movie(movie_id=movie_id)
    assert movie.get('rotation_steps') == 2, f"{movie}"

    movie_metadata2 = odb.get_movie_metadata(movie_id=movie_id)
    logger.debug("movie_metadata2=%s", movie_metadata2)
    assert movie_metadata2.get('rotation_steps') == 2
