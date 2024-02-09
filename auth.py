"""Authentication Layer

This layer is necessarily customized to bottle.
This provides for all authentication in the planttracer system:
* Database authentication
* Mailer authentication
"""
import os
import functools
import configparser
import bottle
import logging
from bottle import request

import paths

from lib.ctools import dbfile
API_KEY_COOKIE_NAME = 'api_key'
COOKIE_MAXAGE = 60*60*24*180


################################################################
# Authentication configuration - for server
##


def credentials_file():
    if 'AWS' in os.environ:
        return paths.AWS_CREDENTIALS_FILE
    else:
        return paths.CREDENTIALS_FILE

def smtp_config():
    cp = configparser.ConfigParser()
    cp.read( credentials_file() )
    for key in ['SMTP_USERNAME','SMTP_PASSWORD','SMTP_PORT','SMTP_HOST']:
        assert key in cp['smtp']
    return cp['smtp']

@functools.lru_cache(maxsize=None)
def get_dbreader():
    """Get the dbreader authentication info from:
    1 - the [dbreader] section of the file specified by the DBCREDENTIALS_PATH environment variable if it exists.
    2 - the [dbreader] section of the file etc/credentials.ini
    """
    return dbfile.DBMySQLAuth.FromConfigFile( credentials_file(), 'dbreader')


@functools.lru_cache(maxsize=None)
def get_dbwriter():
    """Get the dbwriter authentication info from:
    1 - the [dbwriter] section of the file specified by the DBCREDENTIALS_PATH environment variable if it exists.
    2 - the [dbwriter] section of the file etc/credentials.ini
    """
    return dbfile.DBMySQLAuth.FromConfigFile( credentials_file(), 'dbwriter')


################################################################
# Authentication API - for clients
##


def set_cookie(api_key):
    bottle.response.set_cookie(API_KEY_COOKIE_NAME, api_key, path='/',
                               max_age=COOKIE_MAXAGE)

def clear_cookie():
    bottle.response.delete_cookie(API_KEY_COOKIE_NAME, path='/')

def get_user_api_key():
    """Gets the user APIkey from either the URL or the cookie or the form, but does not validate it.
    :return: None if user is not logged in
    """

    # check the query string
    try:
        api_key = request.query.get(API_KEY_COOKIE_NAME, None)
        if api_key is not None:
            return api_key
    except KeyError:
        return None             # not running in WSGI


    # check for a form submission
    try:
        api_key = request.forms.get('api_key', None)
    except KeyError:
        return None             # not running in WSGI

    if api_key:
        return api_key

    # Return the api_key if it is in a cookie, otherwise None
    return request.get_cookie('api_key', None)


def get_user_ipaddr():
    """This is the only place where db.py knows about bottle."""
    return request.environ.get('REMOTE_ADDR')

def get_param(k, default=None):
    """Get param v from the reqeust"""
    return request.query.get(k, request.forms.get(k, default))

#def get_movie_id():
#    movie_id = get_param('movie_id', None)
#    if movie_id is not None:
#        return movie_id
#    raise bottle.HTTPResponse(body=json.dumps(INVALID_MOVIE_ID),
#                              status=200,
#                              headers={ 'Content-type': 'application/json'})
