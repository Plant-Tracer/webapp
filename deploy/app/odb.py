"""
Plant Tracer object database implementation.
Currently dependent upon DynamoDB.

(C) 2025 Simson L. Garfinkel
"""

import os
import uuid
import logging
import json
import sys
import copy
import smtplib
import functools
import uuid
from functools import lru_cache

from flask import request
import boto3
from botocore.exceptions import ClientError,ParamValidationError
from jinja2.nativetypes import NativeEnvironment

from . import auth
from . import mailer
from .paths import TEMPLATE_DIR
from .constants import MIME,C


API_KEYS = 'api_keys'
USERS  = 'users'
MOVIES = 'movies'
FRAMES = 'frames'
COURSES = 'courses'

ODB_TABLES = {API_KEYS,USERS,MOVIES,FRAMES,COURSES}

EMAIL_TEMPLATE_FNAME = 'email.txt'
SUPER_ADMIN_COURSE_ID = -1      # this is the super course. People who are admins in this course see everything.

CHECK_MX = False            # True doesn't work

################################################################
## Errors
################################################################

class DB_Errors(RuntimeError):
    """Base class for DB Errors"""

class InvalidAPI_Key(DB_Errors):
    """ API Key is invalid """

class InvalidCourse_Key(DB_Errors):
    """ Course Key is invalid """

class InvalidMovie_Id(DB_Errors):
    """ MovieID is invalid """
    def __init__(self, v):
        super().__init__(str(v))

class InvalidFrameAccess(DB_Errors):
    """ FrameID is invalid """

class UnauthorizedUser(DB_Errors):
    """ User is not authorized for movie"""

class NoMovieData(DB_Errors):
    """There is no data for the movie"""


################################################################
## ODB - The Object Database Class
################################################################

@lru_cache(maxsize=None)
class ODB:
    def __init__(self, *, region_name='us-east-1', endpoint_url=None):
        self.dynamodb = boto3.resource( 'dynamodb',
                                        region_name=region_name,
                                        endpoint_url=endpoint_url)

        # Set up the tables
        self.api_keys  = self.dynamodb.Table( API_KEYS )
        self.users  = self.dynamodb.Table( USERS )
        self.movies = self.dynamodb.Table( MOVIES )
        self.frames = self.dynamodb.Table( FRAMES )
        self.courses = self.dynamodb.Table( COURSES )

    def new_id(self):
        """Can be used for users, movies, or anything else"""
        return str(uuid.uuid4())

    def get_api_key_dict(self,api_key):
        return self.api_keys.get_item(Key = {'api_key':api_key}).get('Item',None)

    def put_api_key_dict(self,api_key_dict):
        self.api_keys.put_item(Item = api_key_dict)

    def get_user(self,userId):
        return self.users.get_item(Key = {'userId':userId}).get('Item',None)

    def put_user(self,userdict):
        self.users.put_item(Item = userdict)

    def get_course(self,courseId):
        return self.courses.get_item(Key = {'courseId':courseId}).get('Item',None)

    def put_course(self, coursedict):
        self.courses.put_item(Item=coursedict)

    def get_movie(self,movieId):
        return self.movies.get_item(Key = {'movieId':movieId}).get('Item',None)

    def put_movie(self, moviedict):
        print("moviedict:",moviedict)
        self.movies.put_item(Item=moviedict)

    def get_frame(self,movieId,frameId):
        return self.frames.get_item(Key = {'movieId':userId, 'frameId':frameId}).get('Item',None)

    def put_frame(self,framedict):
        self.frames.put_item(Item=framedict)

#####################
## USER MANAGEMENT ##
#####################

def validate_api_key(api_key):
    """
    Validate API key.
    :param: api_key - the key provided by the cookie or the HTML form.
    :return: User dictionary if api_key and user are both enabled, otherwise return {}
    """
    dd = ODB()
    api_key_dict = dd.get_api_key_dict(api_key)
    if api_key_dict['enabled']:
        user = dd.get_user(api_key_dict['userId'])
        if user['enabled']:
            logging.debug("validate_api_key(%s)=%s dbreader=%s",api_key,user)
            api_key_dict['last_used_at']  = unix_timestamp()
            api_key_dict['first_used_at'] = api_key_dict.get('first_used_at', api_key_dict['last_used_at'])
            dd.put_api_key_dict(api_key_dict)
            return user
    return {}

    ret = dbfile.DBMySQL.csfr(get_dbreader(),
                              """SELECT * from api_keys left join users on user_id=users.id
                              where api_key=%s and api_keys.enabled=1 and users.enabled=1 LIMIT 1""",
                              (api_key, ), asDicts=True)

    if ret:
        dbfile.DBMySQL.csfr(get_dbwriter(),
                            """UPDATE api_keys
                             SET last_used_at=unix_timestamp(),
                             first_used_at=
                             use_count=use_count+1
                             WHERE api_key=%s""",
                            (api_key,))
        return dict(ret[0])
    return {}
