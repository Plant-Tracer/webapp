"""
Plant Tracer object database implementation.
Currently dependent upon DynamoDB.

(C) 2025 Simson L. Garfinkel
"""

#pylint: disable=too-many-lines
import os
import logging
import json
import sys
import copy
import smtplib
import functools
import uuid
import time
from functools import lru_cache,wraps
from decimal import Decimal

from flask import request

from jinja2.nativetypes import NativeEnvironment

import boto3
from botocore.exceptions import ClientError,ParamValidationError
from boto3.dynamodb.conditions import Key,Attr

from . import auth
from . import mailer
from . import db_object
from .paths import TEMPLATE_DIR
from .constants import MIME,C

logging.basicConfig(format=C.LOGGING_CONFIG, level=C.LOGGING_LEVEL)
logger = logging.getLogger(__name__)

# tables
API_KEYS = 'api_keys'
USERS  = 'users'
UNIQUE_EMAILS = 'unique_emails'
MOVIES = 'movies'
FRAMES = 'movie_frames'
COURSES = 'courses'

# attributes
ADMIN = 'admin'

COURSE_ID = 'course_id'

EMAIL = 'email'

MOVIE_ID = 'movie_id'
MOVIE_DATA_URN = 'movie_data_urn'
MOVIE_ZIPFILE_URN = 'movie_zipfile_urn'

NAME = 'name'

USER_ID = 'user_id'

PRIMARY_COURSE_ID = 'primary_course_id'

ODB_TABLES = {API_KEYS,USERS,UNIQUE_EMAILS,MOVIES,FRAMES,COURSES}

EMAIL_TEMPLATE_FNAME = 'email.txt'
SUPER_ADMIN_COURSE_ID = -1  # this is the super course. People who are admins in this course see everything.
CHECK_MX = False            # True doesn't work

################################################################
## Errors
################################################################

class ODB_Errors(RuntimeError):
    """Base class for DB Errors"""

class InvalidAPI_Key(ODB_Errors):
    """ API Key is invalid """

class InvalidCourse_Key(ODB_Errors):
    """ Course Key is invalid """

class InvalidUser(ODB_Errors):
    """User_id or User email is invalid"""

class InvalidMovie_Id(ODB_Errors):
    """ MovieID is invalid """
    def __init__(self, v):
        super().__init__(str(v))

class InvalidFrameAccess(ODB_Errors):
    """ FrameID is invalid """

class UnauthorizedUser(ODB_Errors):
    """ User is not authorized for movie"""

class NoMovieData(ODB_Errors):
    """There is no data for the movie"""

################################################################
## DDBO - The Object Database Class
################################################################

# Note: there is no new_course_id() - we actually use the real course ID (e.g. E-331)

def new_user_id():
    return 'u'+str(uuid.uuid4())

def new_api_key():
    return 'a'+str(uuid.uuid4()).replace('-', '')

def new_movie_id():
    return 'm'+str(uuid.uuid4())

def is_user_id(k):
    return isinstance(k,str) and k[0]=='u'

def is_api_key(k):
    return isinstance(k,str) and k[0]=='a' and len(k)==33

def is_movie_id(k):
    return isinstance(k,str) and k[0]=='m'

# --- Decorator Definition ---
def dynamodb_error_debugger(func):
    """
    A decorator to catch DynamoDB-related errors (ClientError) and
    log specific debugging information about the failed operation.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (ClientError) as e:
            # 'self' (the DDBO instance) is usually the first positional arg
            # in instance methods, but we can't reliably get the exact
            # operation name or params at this decorator level unless they're
            # passed explicitly or inferred.
            # However, the error message from botocore.exceptions.ClientError
            # itself often contains valuable context like the operation name.

            logger.error("-" * 60)
            logger.error("DYNAMODB OPERATION FAILED in method: %s",func.__name__)
            logger.error("  Error Type: %s",type(e).__name__)

            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error("  Error Message from DynamoDB: %s",error_message)

            # The 'OperationName' is part of the error response for ClientError
            operation_name_from_error = e.operation_name
            if operation_name_from_error:
                logger.error("  Failed AWS API Operation: %s",operation_name_from_error)

            # The 'Parameters' (api_params) are not directly accessible from the
            # exception object in a generic way *outside* the original call scope.
            # To get specific parameters, you'd need to log them where the
            # boto3 call is made, or inspect 'e.response' carefully.
            # Example:
            if 'RequestParameters' in e.response.get('Error', {}):
                logger.error("  Request Parameters (if available): %s",e.response['Error']['RequestParameters'])

            logger.error("-" * 60)
            raise # Re-raise the original exception so the test still fails
    return wrapper


#pylint disable=too-many-public-methods
@lru_cache(maxsize=None)
class DDBO:
    """Singleton for accessing dynamodb database"""
    def __init__(self, *, region_name=None, endpoint_url=None, table_prefix=None):
        # Note: the os.environ.get() cannot be in the def above because then it is executed at compile-time,
        # not at object creation time.

        if region_name is None:
            region_name = os.environ.get(C.AWS_DEFAULT_REGION,C.THE_DEFAULT_REGION)
        if endpoint_url is None:
            endpoint_url = os.environ.get(C.DYNAMODB_ENDPOINT_URL,None)

        if table_prefix is None:
            table_prefix = os.environ.get(C.DYNAMODB_TABLE_PREFIX, '')

        self.dynamodb = boto3.resource( 'dynamodb',
                                        region_name=region_name,
                                        endpoint_url=endpoint_url)

        # Set up the tables
        logger.info("Using table prefix '%s'",table_prefix)
        self.table_prefix = table_prefix
        self.api_keys  = self.dynamodb.Table( table_prefix + API_KEYS )
        self.users     = self.dynamodb.Table( table_prefix + USERS )
        self.unique_emails = self.dynamodb.Table( table_prefix + UNIQUE_EMAILS )
        self.movies    = self.dynamodb.Table( table_prefix + MOVIES )
        self.movie_frames    = self.dynamodb.Table( table_prefix + FRAMES )
        self.courses   = self.dynamodb.Table( table_prefix + COURSES )
        self.tables    = [self.api_keys, self.users, self.movies, self.movie_frames, self.courses]

    # Generic stuff
    @staticmethod
    def _get_partition_key_name(key_schema):
        "Extract the partition (HASH) key name from a Table.key_schema list."
        return next(item['AttributeName']
                    for item in key_schema
                    if item['KeyType'] == 'HASH')

    def update_table(self, table, key_value, updates: dict):
        """
        Generic updater for any DynamoDB Table resource.

        :param table:       a boto3 Table resource (e.g. self.movies)
        :param key_value:   the value of the partition key
        :param updates:     dict mapping attribute names → new values;
                            if value is None, that attribute will be removed.
        """
        # 1) figure out the PK name & build the Key dict
        pk = self._get_partition_key_name(table.key_schema)
        key = { pk: key_value }

        # 2) separate SET vs REMOVE
        set_exprs = []
        remove_exprs = []
        expr_values = {}
        expr_names = {}

        for attr, val in updates.items():
            name_ph = f"#{attr}"
            expr_names[name_ph] = attr

            if val is None:
                remove_exprs.append(name_ph)
            else:
                val_ph = f":{attr}"
                set_exprs.append(f"{name_ph} = {val_ph}")
                expr_values[val_ph] = val

        # 3) build the combined UpdateExpression
        parts = []
        if set_exprs:
            parts.append("SET " + ", ".join(set_exprs))
        if remove_exprs:
            parts.append("REMOVE " + ", ".join(remove_exprs))
        update_expr = " ".join(parts)

        # 4) assemble parameters
        params = {
            "Key": key,
            "UpdateExpression": update_expr,
            "ExpressionAttributeNames": expr_names
        }
        if expr_values:
            params["ExpressionAttributeValues"] = expr_values

        # 5) run the update
        return table.update_item(**params)

    ### api_key management

    def get_api_key_dict(self,api_key):
        return self.api_keys.get_item(Key = {'api_key':api_key}, ConsistentRead=True).get('Item',None)

    def put_api_key_dict(self,api_key_dict):
        self.api_keys.put_item(Item = api_key_dict)

    def del_api_key(self, api_key):
        self.api_keys.delete_item(Key = {'api_key':api_key})

    ### User management

    def get_user(self, user_id, email=None):
        if email:
            assert user_id is None
            response = self.users.query(
                IndexName='email_idx',
                KeyConditionExpression=Key( EMAIL ).eq(email)
            )
            items = response.get('Items', [])
            if items:
                return items[0]
            raise InvalidUser(email)
        item = self.users.get_item(Key = { USER_ID :user_id},ConsistentRead=True).get('Item',None)
        if item:
            return item
        raise InvalidUser(user_id)

    def get_userid_for_email(self, email):
        ret = self.get_user(None, email)[ USER_ID ]
        if ret:
            return ret
        raise InvalidUser(email)

    def add_user(self, user):
        email = user[ EMAIL ]
        user_id = user[ USER_ID ]
        assert is_user_id(user_id)

        try:
            self.dynamodb.meta.client.transact_write_items(
                TransactItems=[
                    # TODO - Add a check to make sure course_id exists
                    {
                        'Put': {
                            'TableName': self.unique_emails.name,
                            'Item': { EMAIL : email},
                            'ConditionExpression': 'attribute_not_exists(email)',
                        }
                    },
                    {
                        'Put': {
                            'TableName': self.users.name,
                            'Item': user,
                            'ConditionExpression': 'attribute_not_exists(user_id)'
                        }
                    }
                ]
            )
            print("Transaction succeeded: user inserted.")
        except ClientError as e:
            # If any ConditionCheck fails, you’ll land here:
            print("Transaction canceled:", e.response['Error']['Message'])
            raise

    def rename_user(self, *, user_id, new_email):
        """Changes a user's email. Returns userdict. """
        assert is_user_id(user_id)
        userdict = self.get_user(user_id)
        if not userdict:
            raise InvalidUser(user_id)
        if userdict[ EMAIL ] == new_email:
            return userdict

        try:
            client = self.dynamodb.meta.client
            client.transact_write_items(
                TransactItems=[ {
                    'Delete': {
                        'TableName': self.unique_emails.name,
                        'Key': { EMAIL : userdict[ EMAIL ]},
                        'ConditionExpression': 'attribute_exists(email)'  # Ensure old email exists
                    }
                }, {
                    'Put': {
                        'TableName': self.unique_emails.name,
                        'Item': { EMAIL : new_email},
                        'ConditionExpression': 'attribute_not_exists(email)'  # Ensure new email doesn't exist
                    }
                }, {
                    'Update': {
                        'TableName': self.users.name,
                        'Key': { USER_ID : user_id},
                        'UpdateExpression': 'SET email = :new_email',
                        'ExpressionAttributeValues': { ':new_email': new_email}
                    }
                } ] )
            userdict[ EMAIL ] = new_email  # update the userd
            return userdict                # return new userdict
        except ClientError as e:
            raise RuntimeError(f"Email update failed: {e}") from e

    def delete_user(self, user_id, purge_movies=False):
        """Delete a user specified by user_id.
        :param: user_id - the user ID
        - First deletes the user's API keys
        - Next deletes all of the user's admin bits
        - Finally deletes the user

        Note: This will fail if the user has any outstanding movies (referrential integrity).
              In that case, the user should simply be disabled.
        Note: A course cannot be deleted if it has any users. A user cannot be deleted if it has any movies.
        Deletes all of the user's movies (if purge_movies is True)
        Also deletes the user from any courses where they may be an admin.
        """
        assert is_user_id(user_id)
        movies = self.get_movies_for_user_id(user_id)
        if purge_movies:
            self.batch_delete_movie_ids( [movie[MOVIE_ID] for movie in movies] )
        else:
            if movies:
                raise RuntimeError(f"user {user_id} has {len(movies)} outstanding movies.")

        # Now delete all of the API keys for this user
        # First get the API keys
        api_keys = []
        last_evaluated_key = None
        while True:
            query_kwargs = {
                'IndexName': 'user_id_idx',
                'KeyConditionExpression': Key( USER_ID ).eq(user_id),
                'ProjectionExpression': 'api_key'
            }
            if last_evaluated_key:
                query_kwargs['ExclusiveStartKey'] = last_evaluated_key
            response = self.api_keys.query(**query_kwargs)
            api_keys.extend(item['api_key'] for item in response['Items'])
            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break
        # Now batch delete the API keys
        with self.api_keys.batch_writer() as batch:
            for api_key in api_keys:
                batch.delete_item(Key={'api_key': api_key})

        # Get the email address. We should just get the userdict with some fancy projection...
        # Finally delete the user and the unique email
        email = self.users.get_item(Key={ USER_ID :user_id},ConsistentRead=True)['Item'][ EMAIL ]
        client = self.dynamodb.meta.client
        client.transact_write_items(
            TransactItems=[
                {
                    'Delete': {
                        'TableName': self.users.name,
                        'Key': { USER_ID : user_id},
                        'ConditionExpression': 'attribute_exists(user_id)'  # Ensure user_id exists
                    },
                },
                {
                    'Delete': {
                        'TableName': self.unique_emails.name,
                        'Key': { EMAIL : email},
                        #'ConditionExpression': 'attribute_exists(email)'  # Ensure old email exists
                    }
                }
            ])


    ### course management

    def get_course(self,course_id):
        return self.courses.get_item(Key = { COURSE_ID :course_id}).get('Item',None)

    def put_course(self, coursedict):
        self.courses.put_item(Item=coursedict)

    def del_course(self, course_id):
        """Deletes course from courses and deletes every mention of the course in every user.
        Does not run if the course has any movies.
        """
        r = self.movies.query( IndexName='course_id_idx',
                               KeyConditionExpression=Key( COURSE_ID ).eq(course_id))
        items = r.get('Items',[])
        if len(items):
            raise RuntimeError(f"course {course_id} has {len(items)} movies.")

        # delete the course
        self.courses.delete_item(Key = { COURSE_ID :course_id})

        # scan the users
        last_evaluated_key = None
        while True:
            scan_kwargs = {}
            if last_evaluated_key:
                scan_kwargs['ExclusiveStartKey'] = last_evaluated_key
            response = self.users.scan(**scan_kwargs)
            for user in response.get('Items'):
                courses = user[ COURSES ]
                if course_id in courses:
                    courses.remove(course_id)
                    self.users.update_item( Key={ USER_ID : user[ USER_ID ]},
                                       UpdateExpression='SET courses = :c',
                                       ExpressionAttributeValues={':c': courses} )
            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break
        # done!


    def get_course_by_course_key(self, course_key):
        response = self.courses.query( IndexName='course_key_idx',
                                       KeyConditionExpression=Key('course_key').eq(course_key) )
        items = response.get('Items', [])
        return items[0] if items else None

    ### movie management

    def get_movie(self, movie_id):
        ret = self.movies.get_item(Key = {MOVIE_ID:movie_id},ConsistentRead=True).get('Item',None)
        if not ret:
            raise InvalidMovie_Id()
        return ret

    def put_movie(self, moviedict):
        self.movies.put_item(Item=moviedict)

    def batch_delete_movie_ids(self, ids):
        """Delete movie items from the table using batch_writer."""
        with self.movies.batch_writer() as batch:
            for theId in ids:
                batch.delete_item(Key={ MOVIE_ID: theId})

    def get_movies_for_user_id(self, user_id):
        """Query movies.user_id_idx and return all movie records for the given user_id (with pagination)."""
        assert is_user_id(user_id)
        movies = []
        last_evaluated_key = None

        while True:
            query_kwargs = { 'IndexName': 'user_id_idx',
                             'KeyConditionExpression': Key( USER_ID ).eq( user_id ) }

            if last_evaluated_key:
                query_kwargs['ExclusiveStartKey'] = last_evaluated_key
            response = self.movies.query(**query_kwargs)
            movies.extend( response['Items'] )
            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break
        return movies

    def get_movies_for_course_id(self, course_id):
        """Query movies.course_id_idx and return all movie_ids for the given user_id (with pagination)."""
        movies = []
        last_evaluated_key = None

        while True:
            query_kwargs = { 'IndexName': 'course_id_idx',
                             'KeyConditionExpression': Key(  COURSE_ID  ).eq( course_id )}

            if last_evaluated_key:
                query_kwargs['ExclusiveStartKey'] = last_evaluated_key
            response = self.movies.query(**query_kwargs)
            movies.extend( response['Items'] )

            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break
        return movies

    ### movie_frame management

    def get_movie_frame(self,movie_id, frame_number):
        return self.movie_frames.get_item(Key = {MOVIE_ID:movie_id, 'frame_number':frame_number}).get('Item',None)

    def put_movie_frame(self,framedict):
        self.movie_frames.put_item(Item=framedict)

    def get_frames(self, movie_id):
        """Gets all the movie frames"""
        assert is_movie_id(movie_id)
        frames = []
        last_evaluated_key = None

        while True:
            query_kwargs = { 'KeyConditionExpression': Key( MOVIE_ID ).eq( movie_id ) }

            if last_evaluated_key:
                query_kwargs['ExclusiveStartKey'] = last_evaluated_key
            response = self.movie_frames.query(**query_kwargs)
            frames.extend( response['Items'] )
            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break
        return frames

    def delete_movie_frames(self, movie_frames):
        """Delete movie items from the table using batch_writer."""
        with self.movie_frames.batch_writer() as batch:
            for movie_frame in movie_frames:
                batch.delete_item(Key={MOVIE_ID: movie_frame[MOVIE_ID],
                                       'frame_number': movie_frame['frame_number']})


#############
## Logging ##
#############


def logit(*, func_name, func_args, func_return):
    # Get the name of the caller
    try:
        user_ipaddr  = request.remote_addr
    except RuntimeError:
        user_ipaddr  = '<local>'

    # Make copies of func_args and func_return so we can modify without fear
    func_args   = copy.copy(func_args)
    func_return = copy.copy(func_return)

    func_args   = json.dumps(func_args, default=str)
    func_return = json.dumps(func_return, default=str)

    if len(func_return) > C.MAX_FUNC_RETURN_LOG:
        func_return = json.dumps({'log_size':len(func_return), 'error':True}, default=str)
    logger.debug("%s %s(%s) = %s ", user_ipaddr, func_name, func_args, func_return)

def log(func):
    """Logging decorator --- log both the arguments and what was returned.
    TODO: add an option parameter of arguments not to log.
    """
    def wrapper(*args, **kwargs):
        r = func(*args, **kwargs)
        logit(func_name=func.__name__,
              func_args={**kwargs, **{'args': args}},
              func_return=r)
        return r
    return wrapper

def log_args(func):
    """Logging decorator --- log only the arguments, not the response (for things with long responses)."""
    def wrapper(*args, **kwargs):
        logit(func_name=func.__name__,
              func_args={**kwargs, **{'args': args}},
              func_return=None)
        return func(*args, **kwargs)
    return wrapper


################ REGISTRATION ################


def list_users_courses(*, user_id):
    """Returns a dictionary with keys:
    'users' - all the courses to which the user has access, and all of the people in them.
    'courses' - all of the courses
    :param: user_id - the user doing the listing (determines what they can see)

    NOTE: With MySQL users could only see the course list if they were admins.
    With DynamoDB, users can see the full course list for all of their courses.
    """
    ddbo = DDBO()

    user = ddbo.get_user(user_id)
    return {'users': [user],
            COURSES :  [dd.get_course(course_id) for course_id in user[ COURSES ] ] }


def list_admins():
    """Returns a list of all the admins"""
    dd = DDBO()
    admin_users = []
    last_evaluated_key = None

    while True:
        scan_kwargs = { 'FilterExpression': Attr( ADMIN ).eq(1) }

        if last_evaluated_key:
            scan_kwargs['ExclusiveStartKey'] = last_evaluated_key

        response = dd.users.scan(**scan_kwargs)
        admin_users.extend(response['Items'])
        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break
    return admin_users

def list_demo_users():
    """Returns a list of all demo accounts."""
    ddbo = DDBO()
    admin_users = []
    last_evaluated_key = None

    while True:
        scan_kwargs = { 'FilterExpression': Attr('demo').eq(1) }

        if last_evaluated_key:
            scan_kwargs['ExclusiveStartKey'] = last_evaluated_key

        response = ddbo.users.scan(**scan_kwargs)
        admin_users.extend(response['Items'])
        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break
    return admin_users

def register_email(email, name, course_key=None, course_id=None, demo_user=0):
    """Register a new user as identified by their email address for a given course.
    Does not make an api_key or send the links with the api_key.
    :param: email - user email
    :param: course_key - the key
    :param: course_id  - the course
    :param: demo_user  - True if this is a demo user
    :return: dictionary of { USER_ID :user_id} for user who is registered.
    """

    if (course_key is None) and (course_id is None):
        raise ValueError("Either the course_key or the course_id must be provided")

    # Get the course name and (optionally) course_id

    ddbo = DDBO()
    if course is not None:
        course = ddbo.get_course(course_id)
    else:
        course = ddbo.get_course_by_course_key(course_key)
    if course is None:
        raise InvalidCourse_Key(course_key)

    # Now we need to either be the first to create this user
    # or else we need to get the user_id of the existing user.
    while True:
        try:
            user = ddbo.get_user(None, email=email)
            # The user exists! Change the primary course and add them to this course.
            ddbo.users.update_items( Key={ USER_ID :user[ USER_ID ]},
                                     UpdateExpression=
                                     'SET primary_course_id=:pci, '
                                     'primary_course_name=:pcn, demo=:demo, courses=:courses',
                                     ExpressionAttributeValues={':pci':course[ COURSE_ID ],
                                                                ':pcn':course['course_name'],
                                                                ':demo':demo_user,
                                                                ':courses':list(set(user[ COURSES ] + [course_id]))})
            return user
        except InvalidUser:
            pass
        # user does not exist. Try to create a new user
        user = {USER_ID : new_user_id(),
                EMAIL  : email,
                'full_name' : name,
                'created' : int(time.time()),
                'enabled' : 1,
                'demo' : demo_user,
                ADMIN  :  0,
                PRIMARY_COURSE_ID : course[ COURSE_ID ],
                'primary_course_name' : course['course_name'] }

        try:
            ddbo.add_user( user )
        except RuntimeError as e:
            logger.warning("Failed to insert user: %s: %e",email,e)
        logger.warning("Looping on get_user or create_user")



################################################################
## API KEY
################################################################
def validate_api_key(api_key):
    """
    Validate API key.
    :param: api_key - the key provided by the cookie or the HTML form.
    :return: User dictionary if api_key and user are both enabled, otherwise return None
    """
    ddbo = DDBO()
    assert is_api_key(api_key)
    api_key_dict = ddbo.get_api_key_dict(api_key)
    if api_key_dict['enabled']:
        user = ddbo.get_user(api_key_dict[ USER_ID ])
        if user['enabled']:
            api_key_dict['use_count']  += 1
            api_key_dict['last_used_at']  = int(time.time())
            api_key_dict['first_used_at'] = api_key_dict.get('first_used_at', api_key_dict['last_used_at'])
            ddbo.put_api_key_dict(api_key_dict)
            return user
    raise InvalidAPI_Key()

def make_new_api_key(*, email):
    """Create a new api_key for an email that is registered
    :param: email - the email
    :return: api_key - the api_key
    """
    ddbo = DDBO()
    user = ddbo.get_user(None, email=email)
    if user['enabled'] == 1:
        api_key = new_api_key()
        ddbo.put_api_key_dict({'api_key':api_key,
                               'enabled':1,
                               USER_ID :user[ USER_ID ],
                               'use_count':0,
                               'created':int(time.time()) })
        return api_key
    raise InvalidUser(f"{email} is not enabled")


#########################
### Course Management ###
#########################

@log
def lookup_course_by_id(*, course_id):
    return DDBO().get_course(course_id)

@log
def lookup_course_by_key(*, course_key):
    return DDBO().get_course_by_course_key(course_key)

@log
def create_course(*, course_id, course_name, course_key, max_enrollment):
    """Create a new course
    :return: course_id of the new course
    """
    return DDBO().put_course({ COURSE_ID :course_id,
                              'course_name':course_name,
                              'course_key':course_key,
                              'course_admins':[],
                              'max_enrollment':max_enrollment})

@log
def delete_course(*,course_id=None):
    """Delete a course.
    :return: number of courses deleted.
    """
    return DDBO().del_course(course_id)

@log
def make_course_admin(*, email, course_id=None):
    """Promotes the user to be an administrator and makes them an administrator of a specific course.
    :param email: email address of the administrator
    :param course_id: - if specified, use this course_id
    """
    ddbo = DDBO()
    user = ddbo.get_user(None, email=email)
    user_id = user[ USER_ID ]
    new_courses = list(set(user[ COURSES ] + [course_id]))
    course = ddbo.get_course(course_id)
    course_id = course[ COURSE_ID ]
    new_course_admins = list(set(course['course_admins'] + [user_id]))

    ddbo.users.update_item( Key={ USER_ID : user_id},
                            UpdateExpression = 'SET admin=:a, courses=:c, primary_course_id=:pcid, primary_course_name=:pcn',
                            ExpressionAttributeValues = { ':a':1,
                                                          ':c':new_courses,
                                                          ':pcid': course_id,
                                                          ':pcn' : course[ NAME ]} )

    ddbo.courses.update_item( Key={ COURSE_ID :course_id},
                              UpdateExpression = 'SET course_admins=:nca',
                              ExpressionAttributeValues = { ':nca':new_course_admins })
    return { USER_ID :user_id, COURSE_ID :course_id}


@log
def remove_course_admin(*, email, course_id=None):
    """Removes email from the course admin list, but doesn't make them not an admin."""
    ddbo = DDBO()
    user = ddbo.get_user(None, email=email)
    user_id = user[ USER_ID ]
    new_courses = user[ COURSES ]

    course = ddbo.get_course(course_id)
    course_id = course[ COURSE_ID ]
    new_course_admins = course['course_admins']

    try:
        new_courses.remove( COURSE_ID )
        ddbo.users.update_item( Key={ USER_ID : user_id},
                                UpdateExpression = 'SET courses=:c, primary_course_id=:pcid, primary_course_name=:pcn',
                                ExpressionAttributeValues = { ':a':1,
                                                              ':c':new_courses,
                                                              ':pcid': None,
                                                              ':pcn' : None} )
    except KeyError:
        logger.warning("course remove fail: %s from user %s %s",course_id,user_id,email)

    try:
        new_course_admins.remove(user_id)
        ddbo.courses.update_item( Key={ COURSE_ID :course_id},
                                  UpdateExpression = 'SET course_admins=:nca',
                                  ExpressionAttributeValues = { ':nca':new_course_admins })
    except KeyError:
        logger.warning("course admin remove fail: admin %s %s from course %s",user_id,email,course_id)


@log
def check_course_admin(*, user_id, course_id):
    """Return True if user_id is an admin in course_id"""
    logger.warning("HIGH DB DRAIN")
    user = DDBO().get_user(user_id)
    return (course_id in user[ COURSES ] ) and user[ ADMIN ]

@log
def validate_course_key(*, course_key):
    logger.warning("HIGH DB DRAIN")
    if DDBO().get_course_by_course_key(course_key):
        return True
    return False

@log
def remaining_course_registrations(*,course_key):
    logger.warning("HIGH DB DRAIN and SCAN")
    ddbo = DDBO()
    course = ddbo.get_course_by_course_key(course_key)
    if not course:
        return 0
    course_id = course[ COURSE_ID ]

    registrants = 0
    last_evaluated_key = None
    while True:
        scan_kwargs = {}

        if last_evaluated_key:
            scan_kwargs['ExclusiveStartKey'] = last_evaluated_key

        response = ddbo.users.scan(**scan_kwargs)
        for user in response['Items']:
            if course_id == user[ PRIMARY_COURSE_ID ] or course_id in user[ COURSES ]:
                registrants += 1
        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break
    return course['max_enrollment'] - registrants



########################
### Movie Management ###
########################

@log
def get_movie_data(*, movie_id:int, zipfile=False, get_urn=False):
    """Returns the movie contents for a movie_id.
    If urn==True, just return the urn
    """
    what = "movie_zipfile_urn" if zipfile else "movie_data_urn"
    movie = DDBO().movies.get_item(Key={MOVIE_ID:movie_id})
    try:
        urn   = movie[what]
    except TypeError as e:
        raise InvalidMovie_Id(movie_id) from e

    if get_urn:
        return urn

    if urn:
        return db_object.read_object(urn)
    raise InvalidMovie_Id()


@log
def get_movie_metadata(*, user_id, movie_id, get_last_frame_tracked=False):
    """Gets the metadata for all movies accessible by user_id or enumerated by movie_id.
    """
    logger.warning("UNNEDED USERID QUERY")
    logger.warning("TK: replace get_movie_metadata with list_movies")
    logger.warning("ignored: get_last_frame_tracked=%s",get_last_frame_tracked)
    ddbo = DDBO()
    user = ddbo.users.get_item(Key={ USER_ID :user_id})
    movies = []
    if movie_id is not None:
        return [ddbo.get_movie(movie_id)]

    # build a query for all movies for which the user is in the course
    for course_id in user[ COURSES ]:
        movies.extend( ddbo.get_movies_for_course_id(course_id) )
    return movies


@log
def can_access_movie(*, user_id, movie_id):
    """Return if the user is allowed to access the movie."""
    logger.warning("UNNEDED USERID QUERY")
    ddbo = DDBO()
    movie = ddbo.get_movie(movie_id)
    if movie[ USER_ID ] == user_id:
        return True
    user = ddbo.users.get_item(Key={ USER_ID :user_id})
    if movie[ COURSE_ID ] in user[ COURSES ]:
        return True
    return False

################################################################
## Movie frames

@log
def create_new_movie(*, user_id, course_id, title=None, description=None, orig_movie=None):
    """
    Creates an entry for a new movie and returns the movie_id. The movie content must be uploaded separately.

    :param: user_id  - person creating movie. Stored in movies table.
    :param: title - title of movie. Stored in movies table
    :param: description - description of movie
    :param: movie_metadata - if presented, metadata for the movie. Stored in movies SQL table.
    :param: orig_movie - if presented, the movie_id of the movie on which this is based
    """
    # Create a new movie record
    ddbo = DDBO()
    movie_id = new_movie_id()
    ddbo.put_movie({MOVIE_ID:movie_id,
                    COURSE_ID: course_id,
                    USER_ID: user_id,
                    'title':title,
                    'description':description,
                    'orig_movie':orig_movie,
                    'published': 0,
                    'deleted': 0,
                    'movie_zipfile_urn':None,
                    MOVIE_DATA_URN:None,
                    'last_frame_tracked':None,
                    'created_at':int(time.time()),
                    'date_uploaded':None,
                    'total_frames':0,
                    'total_bytes':0})
    return movie_id



def set_movie_metadata(*, movie_id, movie_metadata):
    """Set the movie_metadata from a dictionary."""

    assert is_movie_id(movie_id)
    assert MOVIE_ID not in movie_metadata
    assert 'id' not in movie_metadata
    ddbo = DDBO()
    ddbo.update_table(ddbo.movies, movie_id, movie_metadata)


def set_movie_data(*,movie_id, movie_data):
    """If we are setting the movie data, be sure that any old data (frames, zipfile, stored objects) are gone"""
    assert is_movie_id(movie_id)
    ddbo = DDBO()
    purge_movie_data(movie_id=movie_id)
    purge_movie_frames( movie_id=movie_id )
    purge_movie_zipfile( movie_id=movie_id )
    object_name= db_object.object_name( course_id = course_id_for_movie_id( movie_id ),
                                        movie_id = movie_id,
                                        ext=C.MOVIE_EXTENSION)
    movie_data_urn        = db_object.make_urn( object_name = object_name)
    db_object.write_object(movie_data_urn, movie_data)
    ddbo.update_table(ddbo.movies, movie_id, {MOVIE_DATA_URN:movie_data_urn})

def set_movie_data_urn(*,movie_id, movie_data_urn):
    """If we are setting the movie data, be sure that any old data (frames, zipfile, stored objects) are gone"""
    assert is_movie_id(movie_id)
    ddbo = DDBO()
    ddbo.update_table(ddbo.movies, movie_id, {MOVIE_DATA_URN:movie_data_urn})


################################################################
## Deleting

@log
def purge_movie_data(*,movie_id):
    """Delete the movie data associated with a movie"""
    logger.debug("purge_movie_data movie_id=%s",movie_id)
    ddbo = DDBO()
    urn = ddbo.get_movie(movie_id).get(MOVIE_DATA_URN,None)
    if urn:
        db_object.delete_object( urn )
        ddbo.update_table(ddbo.movies,movie_id, {MOVIE_DATA_URN:None})

@log
def purge_movie_frames(*,movie_id):
    """Delete the frames and zipfile associated with a movie."""
    logger.debug("purge_movie_frames movie_id=%s",movie_id)
    ddbo = DDBO()
    frames = ddbo.get_frames( movie_id )

    for frame in frames:
        db_object.delete_object(frame['frame_urn'])
    ddbo.delete_movie_frames( frames )


@log
def purge_movie_zipfile(*,movie_id):
    """Delete the frames associated with a movie."""
    logger.debug("purge_movie_data movie_id=%s",movie_id)
    ddbo = DDBO()
    movie = ddbo.get_movie(movie_id)
    db_object.delete_object(movie['movie_zipfile_urn'])
    DDBO().movies.update_item( Key={MOVIE_ID: movie_id},
                               UpdateExpression='SET movie_zipfile_urn = :val',
                               ExpressionAttributeValues={':val': None})

@log
def purge_movie(*,movie_id, callback=None):
    """Actually delete a movie and all its frames"""
    purge_movie_data(movie_id=movie_id)
    purge_movie_frames( movie_id=movie_id )
    purge_movie_zipfile( movie_id=movie_id )


@log
def delete_movie(*,movie_id, delete=1):
    """Set a movie's deleted bit to be true"""
    purge_movie_data(movie_id=movie_id)
    purge_movie_frames( movie_id=movie_id )
    purge_movie_zipfile( movie_id=movie_id )
    DDBO().movies.delete_item( Key={MOVIE_ID: movie_id})


################################################################
## frames
################################################################

@functools.lru_cache(maxsize=128)
def course_id_for_movie_id(movie_id):
    logger.warning("INEFFICIENT CALL")
    return DDBO().get_movie(movie_id)[ COURSE_ID ]

@functools.lru_cache(maxsize=128)
def movie_data_urn_for_movie_id(movie_id):
    logger.warning("INEFFICIENT CALL")
    return DDBO().get_movie(movie_id)[MOVIE_DATA_URN]


@functools.lru_cache(maxsize=128)
def movie_zipfile_urn_for_movie_id(movie_id):
    logger.warning("INEFFICIENT CALL. Perhaps make it just get the item requested")
    return DDBO().get_movie(movie_id)['movie_zipfile_urn']

# New implementation that writes to s3
# Possible -  move jpeg compression here? and do not write out the frame if it was already written out?
def create_new_movie_frame(*, movie_id, frame_number, frame_data=None):
    """Get the frame id specified by movie_id and frame_number.
    if frame_data is provided, save it as an object in s3e. Otherwise just return the frame_urn.
    if trackpoints are provided, replace current trackpoints with those. This is used sometimes
    just to update the frame_data

    returns frame_urn
    """
    logger.debug("create_new_movie_frame(movie_id=%s, frame_number=%s, type(frame_data)=%s",movie_id, frame_number, type(frame_data))
    course_id = course_id_for_movie_id(movie_id)
    if frame_data is not None:
        # upload the frame to the store and make a frame_urn
        object_name = db_object.object_name(course_id=course_id,
                                            movie_id=movie_id,
                                            frame_number = frame_number,
                                            ext=C.JPEG_EXTENSION)
        frame_urn = db_object.make_urn( object_name = object_name)
    else:
        frame_urn = None
    DDBO().put_movie_frame({"movie_id":movie_id,
                            "frame_number":frame_number,
                            "frame_urn":frame_urn})
    return frame_urn

@log
def get_frame_urn(*, movie_id, frame_number):
    """Get a frame by movie_id and frame number.
    Don't log this to prevent blowing up.
    :param: movie_id - the movie_id wanted
    :param: frame_number - provide one of these. Specifies which frame to get
    :return: the URN or None
    """
    return DDBO().get_movie_frame(movie_id, frame_number)['frame_urn']


def get_frame_data(*, movie_id, frame_number):
    """Get a frame by movie_id and either frame number.
    Don't log this to prevent blowing up.
    :param: movie_id - the movie_id wanted
    :param: frame_number - provide one of these. Specifies which frame to get
    :return: returns the frame data or None
    """
    frame_urn = DDBO().get_movie_frame(movie_id, frame_number)['frame_urn']
    return db_object.read_object(row['frame_urn'])


################################################################
## Trackpoints

def iter_movie_frames_in_range(table, movie_id, f1, f2):
    """Yield movie_frame records for movie_id where frame_number is between f1 and f2."""
    last_evaluated_key = None

    while True:
        query_kwargs = { }

        if last_evaluated_key:
            query_kwargs['ExclusiveStartKey'] = last_evaluated_key

        response = table.query(KeyConditionExpression = Key(MOVIE_ID).eq(movie_id) & Key('frame_number').between(Decimal(f1), Decimal(f2)),
                               **query_kwargs)

        for item in response['Items']:
            yield item

        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break

def get_movie_trackpoints(*, movie_id, frame_start=None, frame_count=None):
    """Returns a list of trackpoint dictionaries where each dictonary represents a trackpoint.
    :param: frame_start, frame_count - optional
    """

    if frame_start is None:
        frame_start = 0
    if frame_count is None:
        frame_count = 1e10

    ret = []
    for frame in iter_movie_frames_in_range( DDBO().movie_frames, movie_id, frame_start, frame_start+frame_count ):
        for tp in frame['trackpoints']:
            ret.append({'frame_number':frame['frame_number'],
                        'x':tp['x'],
                        'y':tp['y'],
                        'label':tp['label']})
    return ret

def get_movie_frame_metadata(*, movie_id, frame_start, frame_count):
    """Returns a set of dictionaries for each frame in the movie. Each dictionary contains movie_id, frame_number, frame_urn
    :param: frame_start, frame_count -
    """
    assert is_movie_id(movie_id)
    return [{MOVIE_ID:frame[MOVIE_ID],
             'frame_number':frame['frame_number'],
             'frame_urn':frame['frame_run']}
            for frame in
            iter_movie_frames_in_range( OODB().movie_frames, movie_id, frame_start, frame_start+frame_count ) ]


def last_tracked_movie_frame(*, movie_id):
    """Return the last tracked frame_number of the movie"""

    assert is_movie_id(movie_id)
    movie_frames=DDBO().movie_frames
    last_evaluated_key=None
    while True:
        query_kwargs = {
            'KeyConditionExpression': Key(MOVIE_ID).eq(movie_id),
            'FilterExpression': Attr('trackpoints').exists(),
            'ScanIndexForward': False,
            'Limit': 1
        }

        if last_evaluated_key:
            query_kwargs['ExclusiveStartKey'] = last_evaluated_key

        response = movie_frames.query(**query_kwargs)
        items = response.get('Items', [])
        if items:
            return items[0]['frame_number']

        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break
    return None

def put_frame_trackpoints(*, movie_id:int, frame_number:int, trackpoints:list[dict]):
    """
    :frame_number: the frame to replace. If the frame has existing trackpoints, they are overwritten
    :param: trackpoints - array of dicts where each dict has an x, y and label. Other fields are ignored.
    """
    assert is_movie_id(movie_id)
    DDBO().movie_frames.update_item( Key={MOVIE_ID:movie_id,
                                          'frame_number':frame_number},
                                     UpdateExpression='SET trackpoints=:val',
                                     ExpressionAttributeValues={':val':trackpoints})


################################################################

# Don't log this; we run list_movies every time the page is refreshed
def list_movies(*,user_id, movie_id=None, orig_movie=None):
    """Return a list of movies that the user is allowed to access.
    This should be updated so that we can request only a specific movie
    :param: user_id - only list movies visible to user_id (0 for all movies)
    :param: movie_id - if provided, only use this movie
    :param: orig_movie - if provided, only list movies for which the original movie is orig_movie_id
    """
    if is_movie_id:
        assert is_movie_id(movie_id)
    ddbo = DDBO()
    user = ddbo.users.get_item(Key={ USER_ID :user_id})
    if orig_movie is not None:
        raise NotImplemented("orig_movie not implemented")
    movies = []
    if movie_id is not None:
        return [ddbo.get_movie(movie_id)]

    # build a query for all movies for which the user is in the course
    for course_id in user[ COURSES ]:
        movies.extend( ddbo.get_movies_for_course_id(course_id) )
    return movies

################################################################
## Logs
################################################################

def get_logs( *, user_id , start_time = 0, end_time = None, course_id=None,
              course_key=None, log_user_id=None,
              ipaddr=None, security=True):
    """get log entries (to which the user is entitled) - Implements /api/get-log
    :param: user_id    - The user who is initiating the query
    :param: start_time - The earliest log entry to provide (time_t)
    :param: end_time   - the last log entry to provide (time_t)
    :param: course_id  - if provided, only provide log entries for this course
    :param: log_user_id - if provided, only provide log entries for this person
    :param: security   - False to disable security checks
    :return: list of dictionaries of log records.
    """
    ddbo = DDBO()
    # Use epoch max if end_time not given
    if end_time is None:
        end_time = int(time.time())

    # Select GSI based on parameters
    if log_user_id:
        index_name = 'user_id_idx'
        key_condition = Key( USER_ID ).eq(log_user_id)
    elif ipaddr:
        index_name = 'ipaddr_idx'
        key_condition = Key('ipaddr').eq(ipaddr)
    elif course_id:
        index_name = 'course_time_t_idx'
        key_condition = Key( COURSE_ID ).eq(course_id)
        if start_time and end_time:
            key_condition &= Key('time_t').between(start_time, end_time)
        elif start_time:
            key_condition &= Key('time_t').gte(start_time)
        elif end_time:
            key_condition &= Key('time_t').lte(end_time)
    else:
        raise InvalidFrameAccess("No index provided.")

    # Prepare query
    kwargs = {
        'IndexName': index_name,
        'KeyConditionExpression': key_condition
    }

    # Perform paginated query
    items = []
    while True:
        response = table.query(**kwargs)
        items.extend(response.get('Items', []))
        if 'LastEvaluatedKey' not in response:
            break
        kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']

    # Optional filtering in Python
    if course_id and index_name != 'course_time_t_idx':
        items = [item for item in items if item.get( COURSE_ID ) == course_id]
    if start_time and index_name != 'course_time_t_idx':
        items = [item for item in items if int(item.get('time_t', 0)) >= start_time]
    if end_time and index_name != 'course_time_t_idx':
        items = [item for item in items if int(item.get('time_t', 0)) <= end_time]

    return items


################################################################
## Metadata
################################################################


# set movie metadata privileges array:
# columns indicate WHAT is being set, WHO can set it, and HOW to set it
# We kept this, even thoguh we are now just parsing it
SET_MOVIE_METADATA = {
    # these can be changed by the owner or an admin
    'title': 'update movies set title=%s where id=%s and (@is_owner or @is_admin)',
    'description': 'update movies set description=%s where id=%s and (@is_owner or @is_admin)',
    'status': 'update movies set status=%s where id=%s and (@is_owner or @is_admin)',
    'fps': 'update movies set fps=%s where id=%s and (@is_owner or @is_admin)',
    'width': 'update movies set width=%s where id=%s and (@is_owner or @is_admin)',
    'height': 'update movies set height=%s where id=%s and (@is_owner or @is_admin)',
    'total_frames': 'update movies set total_frames=%s where id=%s and (@is_owner or @is_admin)',
    'total_bytes': 'update movies set total_bytes=%s where id=%s and (@is_owner or @is_admin)',
    'version':'update movies set version=%s where id=%s and (@is_owner or @is_admin)',
    'movie_zipfile_urn':'update movies set movie_zipfile_urn=%s where id=%s and (@is_owner or @is_admin)',

    # the user can delete or undelete movies; the admin can only delete them
    'deleted': 'update movies set deleted=%s where id=%s and (@is_owner or (@is_admin and deleted=0))',

    # the admin can publish or unpublish movies; the user can only unpublish them
    'published': 'update movies set published=%s where id=%s and (@is_admin or (@is_owner and published!=0))',
}


@log
def set_metadata(*, user_id, set_movie_id=None, set_user_id=None, prop, value):
    """We tried doing this in a single statement and it failed
    :param user_id: - user doing the setting. 0 for root
    :param set_movie_id: - if not None, the movie for which we are setting metadata
    :param set_user_id: - if not None, the user for which we are setting metadata
    :param prop - the name of the metadata property being set
    :param value - the value of the metadata property being set

    """
    # First compute @is_owner
    logger.debug("set_user_id=%s set_movie_id=%s prop=%s value=%s", set_user_id, set_movie_id, prop, value)
    assert isinstance(user_id, int)
    assert isinstance(set_movie_id, int) or (set_movie_id is None)
    assert isinstance(set_user_id, int) or (set_user_id is None)
    assert isinstance(prop, str)
    assert value is not None

    ddbo = DDBO()
    user = ddbo.get_user(user_id)

    if set_movie_id is not None:
        movie = ddbo.get_movie(movie_id)
        is_owner = movie[ USER_ID ] == user_id
        is_admin = user_id[ ADMIN ] and (movie[ COURSE_ID ] in user_id[ COURSES ])

        acl  = SET_MOVIE_METADATA[prop]
        if not ((is_owner and '@is_owner' in acl) or (is_admin and '@is_admin') in acl):
            # permission not granted
            raise UnauthorizedUser("permission denied")

        ddbo.movie.update_item( Key={ MOVIE_ID : movie_id},
                                UpdateExpression=f'SET {prop} = :val',
                                ExpressionAttributeValues={':val':value})
    elif set_user_id is not None:
        set_user = ddbo.get_user(set_user_id)
        is_owner = user_id == set_user_id
        is_admin = user_id[ ADMIN ] and (set_user[ PRIMARY_COURSE_ID ] in user_id[ COURSES ])

        if is_owner or is_admin:
            if prop not in [  NAME ,  EMAIL ]:
                raise UnauthorizedUser('currently users can only set name and email')
            ddbo.users.update_item( Key={ USER_ID :set_user_id},
                                    UpdateExpression=f'SET {prop} = :val',
                                    ExpressionAttributeValues={':val':value})
    else:
        raise ValueError("set set_user_id or set_movie_id must be provided")
