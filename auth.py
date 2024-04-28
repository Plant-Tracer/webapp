"""Authentication Layer

This layer is necessarily customized to bottle.
This provides for all authentication in the planttracer system:
* Database authentication
* Mailer authentication
"""
import functools
import configparser
import logging

import bottle
from bottle import request

import paths

from lib.ctools import dbfile
API_KEY_COOKIE_BASE = 'api_key'
COOKIE_MAXAGE = 60*60*24*180
SMTP_ATTRIBS = ['SMTP_USERNAME','SMTP_PASSWORD','SMTP_PORT','SMTP_HOST']

################################################################
# Authentication configuration - for server
##


def credentials_file():
    if paths.running_in_aws_lambda():
        return paths.AWS_CREDENTIALS_FILE
    else:
        return paths.CREDENTIALS_FILE

def smtp_config():
    """Get the smtp config from the [smtp] section of a credentials file.
    If the file specifies a AWS secret, get that.
    """
    cp = configparser.ConfigParser()
    cp.read( credentials_file() )
    section = cp['smtp']
    if (secret := dbfile.get_aws_secret_for_section( section )) is not None:
        return secret

    for key in SMTP_ATTRIBS:
        assert key in cp['smtp']
    return section

@functools.cache
def get_dbreader():
    """Get the dbreader authentication info from:
    1 - the [dbreader] section of the file specified by the DBCREDENTIALS_PATH environment variable if it exists.
    2 - the [dbreader] section of the file etc/credentials.ini
    """
    return dbfile.DBMySQLAuth.FromConfigFile( credentials_file(), 'dbreader')


@functools.cache
def get_dbwriter():
    """Get the dbwriter authentication info from:
    1 - the [dbwriter] section of the file specified by the DBCREDENTIALS_PATH environment variable if it exists.
    2 - the [dbwriter] section of the file etc/credentials.ini
    """
    return dbfile.DBMySQLAuth.FromConfigFile( credentials_file(), 'dbwriter')


################################################################
# Authentication API - for clients
##

@functools.cache
def cookie_name():
    """We append the database name to the cookie name to make development easier.
    This way, the localhost: cookies can be for the prod, demo, or dev databases.
    """
    return API_KEY_COOKIE_BASE + "-" + get_dbreader().database

def set_cookie(api_key):
    bottle.response.set_cookie(cookie_name(), api_key, path='/', max_age=COOKIE_MAXAGE)

def clear_cookie():
    bottle.response.delete_cookie(cookie_name(), path='/')

def get_user_api_key():
    """Gets the user APIkey from either the URL or the cookie or the form, but does not validate it.
    :return: None if user is not logged in
    """
    # check the query string
    try:
        api_key = request.query.get('api_key', None) # must be 'api_key', because may be in URL
        if api_key is not None:
            return api_key
    except KeyError:
        return None             # not running in WSGI


    # check for a form submission
    try:
        api_key = request.forms.get('api_key', None) # must be 'api_key', because may be in a form
    except KeyError:
        return None             # not running in WSGI

    if api_key:
        return api_key

    # Return the api_key if it is in a cookie, otherwise None
    return request.get_cookie(cookie_name(), None)


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
