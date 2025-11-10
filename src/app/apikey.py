"""
apikey.py

Implements the user_dict and APIKEY functions - the high-level authentication system.
All done through get_user_dict() below, which is kind of gross.

"""

import logging
import os
import functools
import subprocess
from functools import lru_cache
import base64
from os.path import join

from flask import request

from . import odb
from .paths import ETC_DIR
from .constants import C,__version__
from .odb import InvalidAPI_Key

def in_demo_mode():
    logging.debug("in_demo_mode: %s",os.environ.get(C.DEMO_COURSE_ID,None))
    return C.DEMO_COURSE_ID in os.environ

# Specify the base for the API and for the static files by Environment variables.
# This allows them to be served from different web servers.
# If they are not set, they default to '' which is the same site that serves the HTML pages.
# (note: we no longer use '/' because that causes a problem when deploying at URLs like
# https://sixybak7yh.execute-api.us-east-1.amazonaws.com/Prod/)
# STATIC is used to serve JavaScript
# API_BASE is used for the server API

api_base    = os.getenv(C.PLANTTRACER_API_BASE,'')
static_base = os.getenv(C.PLANTTRACER_STATIC_BASE,'')

@functools.cache
def git_head_time():
    try:
        return subprocess.check_output("git log --no-walk --pretty=format:%cd".split(),encoding='utf-8')
    except (subprocess.SubprocessError,FileNotFoundError):
        return ""

@functools.cache
def git_last_commit():
    try:
        return subprocess.check_output("git log --pretty=[%h] -1 HEAD".split(),encoding='utf-8')
    except (subprocess.SubprocessError,FileNotFoundError):
        return ""

@functools.cache
def git_branch():
    try:
        return subprocess.check_output("git rev-parse --abbrev-ref HEAD".split(),encoding='utf-8')
    except (subprocess.SubprocessError,FileNotFoundError):
        return ""

################################################################
# Authentication API - for clients
##

@functools.cache
def cookie_name():
    """We append the database name to the cookie name to make development easier.
    This way, the localhost: cookies can be for the prod, demo, or dev databases.
    """
    return C.API_KEY_COOKIE_BASE


def add_cookie(response):
    """Add the cookie if the apikey was in the get value"""
    api_key = request.values.get('api_key', None)
    if api_key:
        response.set_cookie(cookie_name(), api_key,
                            max_age = C.API_KEY_COOKIE_MAX_AGE)

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
    # If we are in demo mode, get the demo mode api_key
    if in_demo_mode():
        return C.DEMO_MODE_API_KEY

    api_key = request.values.get('api_key', None) # must be 'api_key', because may be in URL
    if api_key is not None:
        return api_key

    # Return the api_key if it is in a cookie.
    api_key = request.cookies.get(cookie_name(), None)
    if api_key:
        logging.debug("api_key from request.cookies cookie_name=%s api_key=%s",cookie_name(),api_key)
        return api_key

    # No API key
    return None

def get_user_dict():
    """Returns the user dict from the database of the currently logged in user, or throws a response"""
    logging.debug("get_user_dict")
    api_key = get_user_api_key()
    if api_key is None:
        logging.info("api_key is none or invalid. request=%s",request.full_path)
        # Check if we were running under an API. All calls under /api must be authenticated.
        if request.full_path.startswith('/api/'):
            raise InvalidAPI_Key("get_user_dict 1")

    # We have a key. Now validate it.
    # No special code required for demo mode, since DEMO_MODE_API_KEY is a valid key for this user.
    userdict = odb.validate_api_key(api_key)
    if userdict is None:
        logging.info("api_key %s is invalid  ipaddr=%s request.url=%s",
                     api_key,request.remote_addr,request.url)
        raise InvalidAPI_Key("get_user_dict 2")
    return userdict

@lru_cache(maxsize=1)
def favicon_base64():
    with open( join( ETC_DIR, C.FAVICON), 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

# pylint: disable=too-many-locals
def page_dict(title='', *, require_auth=False, lookup=True, logout=False):
    """Returns a dictionary that can be used by post of the templates.
    :param: title - the title we should give the page
    :param: require_auth  - if true, the user must already be authenticated, or throws an error
    :param: logout - if true, force the user to log out by issuing a clear-cookie command
    :param: lookup - if true, we weren't being called in an error condition, so we can lookup the api_key
                     in the URL or the cookie
    """
    logging.debug("page_dict(title=%s,require_auth=%s,logout=%s,lookup=%s)",title,require_auth,logout,lookup)
    if lookup:
        api_key = get_user_api_key()
        logging.debug("get_user_api_key=%s",api_key)
        if api_key is None and require_auth is True:
            logging.debug("api_key is None and require_auth is True")
            raise InvalidAPI_Key("page_dict")
    else:
        api_key = None

    if (api_key is not None) and (logout is False):
        # Get the user_dict is from the database
        user_dict  = get_user_dict()
        user_name  = user_dict['user_name']
        user_email = user_dict['email']
        user_id    = user_dict['user_id']
        user_primary_course_id = user_dict['primary_course_id']
        primary_course_name    = user_dict['primary_course_name']
        logged_in = 1
        admin = 1 if odb.check_course_admin(user_id=user_id, course_id=user_primary_course_id) and not in_demo_mode() else 0


    else:
        user_name  = None
        user_email = None
        user_id    = None
        user_primary_course_id = None
        primary_course_name = None
        admin = 0
        logged_in = 0

    try:
        movie_id = int(request.query.get('movie_id'))
    except (AttributeError, KeyError, TypeError):
        movie_id = 0            # to avoid errors

    ret= {
        C.API_BASE: api_base,
        C.STATIC_BASE: static_base,
        'favicon_base64':favicon_base64(),
        'api_key': api_key,     # the API key that is currently active
        'user_id': user_id,     # the user_id that is active
        'user_name': user_name, # the user's name
        'user_email': user_email, # the user's email
        'logged_in': logged_in,
        'demo_mode':in_demo_mode(),
        'admin':admin,
        'user_primary_course_id': user_primary_course_id,
        'primary_course_name': primary_course_name,
        'title':'Plant Tracer '+title,
        'hostname':request.host,
        'movie_id':movie_id,
        'MAX_FILE_UPLOAD': C.MAX_FILE_UPLOAD,
        'version':__version__,
        'git_head_time':git_head_time(),
        'git_last_commit':git_last_commit(),
        'git_branch': git_branch()
    }
    for (k,v) in ret.items():
        if v is None:
            ret[k] = "null"
    logging.debug("page_dict=%s",ret)
    return ret
