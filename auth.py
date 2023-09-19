"""Authentication Layer

This layer is necessarily customized to bottle.
"""
import sys
import os
import io
import datetime
import logging
from urllib.parse import urlparse
import json

import bottle

################################################################
## Authentication API
##

def get_user_api_key():
    """Gets the user APIkey from either the URL or the cookie or the form, but does not validate it.
    :return: None if user is not logged in
    """
    # check the query string
    api_key = request.query.get('api_key',None)
    if api_key:
        return api_key
    # check for a form submission
    api_key = request.forms.get('api_key',None)
    if api_key:
        return api_key
    # Check for a cookie
    api_key = request.get_cookie('api_key',None)
    if api_key:
        return api_key
    return None

def get_movie_id():
    movie_id = request.query.get('movie_id',None)
    if movie_id is not None:
        return movie_id
    movie_id = request.forms.get('movie_id',None)
    if movie_id is not None:
        return movie_id
    raise bottle.HTTPResponse(body=json.dumps(INVALID_MOVIE_ID), status=200, headers={'Content-type':'application/json'})

def get_user_dict():
    """Returns the user_id of the currently logged in user, or throws a response"""
    api_key = get_user_api_key()
    if api_key is None:
        raise bottle.HTTPResponse(body=json.dumps(INVALID_API_KEY), status=200, headers={'Content-type':'application/json'})
    userdict = db.validate_api_key( api_key )
    if not userdict:
        raise bottle.HTTPResponse(body=json.dumps(INVALID_API_KEY), status=200, headers={'Content-type':'application/json'})
    return userdict

def get_user_id():
    """Returns the user_id of the currently logged in user, or throws a response"""
    userdict = get_user_dict()
    if 'id' in userdict:
        return userdict['id']
    logging.warning("no ID in userdict = %s",userdict)
    raise bottle.HTTPResponse(body=json.dumps(INVALID_API_KEY), status=200, headers={'Content-type':'application/json'})

def get_user_ipaddr():
    """This is the only place where db.py knows about bottle."""
    return request.environ.get('REMOTE_ADDR')
