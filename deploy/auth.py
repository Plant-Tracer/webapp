"""Authentication Layer

This layer is necessarily customized to bottle.
This provides for all authentication in the planttracer system:
* Database authentication
* Mailer authentication
"""
import os
import os.path
import functools
import configparser
import logging

import bottle
from bottle import request

#import paths
import dbfile

import db
from constants import C

API_KEY_COOKIE_BASE = 'api_key'
COOKIE_MAXAGE = 60*60*24*180
SMTP_ATTRIBS = ['SMTP_USERNAME','SMTP_PASSWORD','SMTP_PORT','SMTP_HOST']

################################################################
# Authentication configuration - for server
##


def credentials_file():
    try:
        name = os.environ[ C.PLANTTRACER_CREDENTIALS ]
    except KeyError as e:
        raise RuntimeError(f"Environment variable {C.PLANTTRACER_CREDENTIALS} must be defined") from e
    if not os.path.exists(name):
        logging.error("Cannot find %s (PLANTTRACER_CREDENTIALS=%s)",os.path.abspath(name),name)
        raise FileNotFoundError(name)
    return name

def config():
    cp = configparser.ConfigParser()
    cp.read( credentials_file() )
    return cp

def smtp_config():
    """Get the smtp config from the [smtp] section of a credentials file.
    If the file specifies a AWS secret, get that.
    """
    cp = config()
    section = cp['smtp']
    if (secret := dbfile.get_aws_secret_for_section( section )) is not None:
        return secret

    for key in SMTP_ATTRIBS:
        assert key in cp['smtp']
    return section

def http403(msg=''):
    return bottle.HTTPResponse(body='Authentication error 403 '+msg, status=403)

def http404(msg=''):
    return bottle.HTTPResponse(body='Not found error 404 '+msg, status=404)

@functools.cache
def get_dbreader():
    """Get the dbreader authentication info from:
    1 - the [dbreader] section of the file specified by the DBCREDENTIALS_PATH environment variable if it exists.
    2 - the [dbreader] section of the credentials file
    """
    return dbfile.DBMySQLAuth.FromConfigFile( credentials_file(), 'dbreader')


@functools.cache
def get_dbwriter():
    """Get the dbwriter authentication info from:
    1 - the [dbwriter] section of the file specified by the DBCREDENTIALS_PATH environment variable if it exists.
    2 - the [dbwriter] section of the credentials file
    """
    logging.debug("get_dbwriter. credentials_file=%s",credentials_file())
    return dbfile.DBMySQLAuth.FromConfigFile( credentials_file(), 'dbwriter')


################################################################
# Demo mode

# Check to see if PLANTTRACER_DEMO environment variable is set.
# If so, then we use the DEMO user if the user is not logged in
DEMO_MODE_AVAILABLE = os.environ.get(C.PLANTTRACER_DEMO_MODE_AVAILABLE,' ')[0:1] in 'yYtT1'

def demo_mode_api_key():
    """Return the api key of the first demo user"""
    for demo_user in db.list_demo_users():
        api_key = db.get_demo_user_api_key(user_id = demo_user['user_id'])
        if api_key is None:
            # Make an api key for the demo user if we do not have one
            api_key = db.make_new_api_key(email=demo_user['email'])
        return api_key
    logging.error("demo_mode_api_key requested but there are no demo users")
    return None

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
    """Gets the user APIkey from either the URL or the cookie or the
    form, but does not validate it.  If we are running in an
    environment that offers demo mode and there is no api_key in the
    browser's cookie or the URL GET string, grab the first api_key
    from the database that corresponds to a demo user.

    :return:
       a string of an API key if the user is logged in
       a string of the demo mode's API key if no user is logged in and demo mode is available.
       None if user is not logged in and no demo mode
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

    # Return the api_key if it is in a cookie.
    # Otherwise return None (not user is logged in) unless we are in Demo Mode, in which case we
    # return the api_key for the demo user.
    api_key = request.get_cookie(cookie_name(), None)
    if (api_key is None) and (DEMO_MODE_AVAILABLE):
        api_key = demo_mode_api_key()
    return api_key

def get_user_ipaddr():
    """This is the only place where db.py knows about bottle."""
    return request.environ.get('REMOTE_ADDR')

def get_param(k, default=None):
    """Get param v from the reqeust"""
    return request.query.get(k, request.forms.get(k, default))
