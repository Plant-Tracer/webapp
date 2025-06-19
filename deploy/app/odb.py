"""
Plant Tracer object database implementation.
Currently dependent upon DynamoDB.

(C) 2025 Simson L. Garfinkel
"""

#pylint: disable=too-many-lines
import os
import logging
import json
import copy
import functools
import re
import uuid
import time
from collections import defaultdict
from functools import wraps
from decimal import Decimal

from flask import request

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key,Attr
from pydantic import ValidationError
import pydantic_core

from . import db_object
from .schema import User, Movie, Trackpoint, validate_movie_field, Course
from .constants import C

# tables
API_KEYS = 'api_keys'
USERS  = 'users'
UNIQUE_EMAILS = 'unique_emails'
MOVIES = 'movies'
FRAMES = 'movie_frames'
COURSES = 'courses'
COURSE_USERS = 'course_users'
LOGS = 'logs'
ROOT_USER_ID = 'u0'                # the root user

# attributes
#SUPER_ADMIN = 'super_admin'             # user.super_admin==1 makes the user admin for everything

DEMO = 'demo'

# apikeys table
API_KEY = 'api_key'

# users table
EMAIL     = 'email'
FULL_NAME = 'full_name'
ENABLED   = 'enabled'
USE_COUNT = 'use_count'
ADMIN_FOR_COURSES = 'admin_for_courses' # user.admin_for_courses[]

# courses table
ADMINS_FOR_COURSE = 'admins_for_course' # courses.admins_for_course[]
COURSE_ID   = 'course_id'               # course.course_id
COURSE_NAME = 'course_name'             # course.course_name
COURSE_KEY  = 'course_key'              # course.course_key
MAX_ENROLLMENT = 'max_enrollment'       # course.max_enrollment

# movies table

MOVIE_ID = 'movie_id'
MOVIE_DATA_URN = 'movie_data_urn'
MOVIE_ZIPFILE_URN = 'movie_zipfile_urn'
TITLE = 'title'
TOTAL_BYTES='total_bytes'
TOTAL_FRAMES='total_frames'
DATE_UPLOADED='date_uploaded'
VERSION = 'version'
DELETED = 'deleted'
PUBLISHED = 'published'
CREATED = 'created'
EMAIL = 'email'
NAME = 'name'


USER_ID = 'user_id'

PRIMARY_COURSE_ID = 'primary_course_id'
PRIMARY_COURSE_NAME = 'primary_course_name'

EMAIL_TEMPLATE_FNAME = 'email.txt'
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

class InvalidCourse_Id(ODB_Errors):
    """ Course Id is invalid """

class ExistingCourse_Id(ODB_Errors):
    """ Course Id exists """

class InvalidUser_Email(ODB_Errors):
    """User email is invalid"""

class InvalidUser_Id(ODB_Errors):
    """User_id is invalid"""

class UserExists(ODB_Errors):
    """User email exists"""

class InvalidMovie_Id(ODB_Errors):
    """ MovieID is invalid """

class InvalidFrameAccess(ODB_Errors):
    """ FrameID is invalid """

class UnauthorizedUser(ODB_Errors):
    """ User is not authorized for movie"""

class NoMovieData(ODB_Errors):
    """There is no data for the movie"""

################################################################
## Type conversion
################################################################

def _fixer(obj):
    if isinstance(obj,Decimal):
        if obj.to_integral_value() == obj:
            return int(obj)
        return float(obj)
    return str(obj)

def fix_types(obj):
    """Process JSON so that it dumps without `default=str`"""
    return json.loads(json.dumps(obj,default=_fixer))



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
    return isinstance(k,str) and k[0:1]=='u'

def is_api_key(k):
    return isinstance(k,str) and len(k)==33 and k[0]=='a'

def is_movie_id(k):
    return isinstance(k,str) and k[0:1]=='m'

def is_ddbo(ddbo):
    return isinstance(ddbo,DDBO)

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

            logging.error("-" * 60)
            logging.error("DYNAMODB OPERATION FAILED in method: %s",func.__name__)
            logging.error("  Error Type: %s",type(e).__name__)

            error_message = e.response.get('Error', {}).get('Message', str(e))
            logging.error("  Error Message from DynamoDB: %s",error_message)

            # The 'OperationName' is part of the error response for ClientError
            operation_name_from_error = e.operation_name
            if operation_name_from_error:
                logging.error("  Failed AWS API Operation: %s",operation_name_from_error)

            # The 'Parameters' (api_params) are not directly accessible from the
            # exception object in a generic way *outside* the original call scope.
            # To get specific parameters, you'd need to log them where the
            # boto3 call is made, or inspect 'e.response' carefully.
            # Example:
            if 'RequestParameters' in e.response.get('Error', {}):
                logging.error("  Request Parameters (if available): %s",e.response['Error']['RequestParameters'])

            logging.error("-" * 60)
            raise # Re-raise the original exception so the test still fails
    return wrapper


# pylint: disable=too-many-public-methods, too-many-instance-attributes
class DDBO:
    """Singleton for accessing dynamodb database"""
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = False
        if self._initialized:
            return  # Skip re-initialization

        region_name = os.environ.get(C.AWS_DEFAULT_REGION, None)
        endpoint_url = os.environ.get(C.AWS_ENDPOINT_URL_DYNAMODB)
        table_prefix = os.environ.get(C.DYNAMODB_TABLE_PREFIX, '')

        self.dynamodb = boto3.resource( 'dynamodb',
                                        region_name=region_name,
                                        endpoint_url=endpoint_url)

        # Set up the tables
        logging.info("region_name=%s endpoint_url=%s table_prefix=%s",region_name,endpoint_url,table_prefix)
        self.table_prefix = table_prefix
        self.api_keys  = self.dynamodb.Table( table_prefix + API_KEYS )
        self.users     = self.dynamodb.Table( table_prefix + USERS )
        self.unique_emails = self.dynamodb.Table( table_prefix + UNIQUE_EMAILS )
        self.movies    = self.dynamodb.Table( table_prefix + MOVIES )
        self.movie_frames    = self.dynamodb.Table( table_prefix + FRAMES )
        self.courses   = self.dynamodb.Table( table_prefix + COURSES )
        self.course_users = self.dynamodb.Table( table_prefix + COURSE_USERS )
        self.logs   = self.dynamodb.Table( table_prefix + LOGS )
        self.tables    = [self.api_keys, self.users, self.movies, self.movie_frames, self.courses, self.course_users, self.logs]
        self._initialized = True

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
        logging.debug("UPDATES=%s",updates)

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
                logging.debug("REMOVE %s val=%s",name_ph,val)
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
        return self.api_keys.get_item(Key = { API_KEY :api_key}).get('Item',None)

    def put_api_key_dict(self,api_key_dict):
        self.api_keys.put_item(Item = api_key_dict,
                               ConditionExpression = 'attribute_not_exists(api_key)' )

    def del_api_key(self, api_key):
        self.api_keys.delete_item(Key = { API_KEY :api_key},
                                  ConditionExpression = 'attribute_exists(api_key)' )

    ### User management

    def get_user(self, user_id):
        """gets the user dictionary given the user_id. Raise InvalidUser_id if it does not exist.
        This is critical, so we always do a consistent read.
        """
        item = self.users.get_item(Key = { USER_ID :user_id},ConsistentRead=True).get('Item',None)
        if item:
            return item
        raise InvalidUser_Id(user_id)

    def get_user_email(self, email):
        """gets the user dictionary given an email address. If email is provided, look up user by email."""
        response = self.users.query( IndexName='email_idx',
                                     KeyConditionExpression=Key( EMAIL ).eq(email) )
        items = response.get('Items', [])
        if items:
            return items[0]
        raise InvalidUser_Email(email)

    def put_user(self, user):
        """Creates the user from the user dict.
        Raises UserExists if the user already exists. Doesn't properly handle other errors.
        """
        try:
            user = User(**user).model_dump() # validate User
        except ValidationError:
            logging.error("user=%s",user)
            raise
        email = user[ EMAIL ]
        assert email is not None
        user_id = user[ USER_ID ]
        assert is_user_id(user_id)
        logging.debug("put_user email=%s user_id=%s user=%s",email,user_id,user)
        logging.warning("NOTE: create_user does not check to make sure user %s's course %s exists",email,user[PRIMARY_COURSE_ID])

        try:
            self.dynamodb.meta.client.transact_write_items(
                TransactItems=[
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
            logging.info("Transaction canceled: %s", e.response['Error']['Message'])
            raise UserExists() from e

    def rename_user(self, *, user_id, new_email):
        """Changes a user's email."""
        assert is_user_id(user_id)
        userdict = self.get_user(user_id)
        if userdict[ EMAIL ] == new_email:
            return

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
        except ClientError as e:
            raise RuntimeError(f"Email update failed: {e}") from e

    def delete_user(self, user_id, purge_movies=False):
        """Delete a user specified by user_id.
        :param user_id: - the user ID
        :param purge_movies: - if true, delete the user's movies
        - First deletes the user's API keys
        - Next deletes all of the user's admin bits
        - Finally deletes the user

        Note: This will fail if the user has any outstanding movies (referrential integrity).
              In that case, the user should simply be disabled.
        Note: A course cannot be deleted if it has any users. A user cannot be deleted if it has any movies.
        Deletes all of the user's movies (if purge_movies is True)
        Also deletes the user from any courses where they may be an admin.
        """
        logging.debug("delete_user user_id = %s purge_movies=%s",user_id,purge_movies)
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
                'ProjectionExpression':  API_KEY
            }
            if last_evaluated_key:
                query_kwargs['ExclusiveStartKey'] = last_evaluated_key
            response = self.api_keys.query(**query_kwargs)
            api_keys.extend(item[ API_KEY ] for item in response['Items'])
            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break
        # Now batch delete the API keys
        with self.api_keys.batch_writer() as batch:
            for api_key in api_keys:
                batch.delete_item(Key={ API_KEY : api_key})

        # Remove them from every course in which they are an admin
        user = self.get_user(user_id)
        for course_id in user[ADMIN_FOR_COURSES]:
            course = self.get_course(course_id)
            admins_for_course = course[ADMINS_FOR_COURSE]
            try:
                admins_for_course.remove(user_id)
                self.update_table(self.courses,course_id,{ADMINS_FOR_COURSE:admins_for_course})
            except ValueError:
                pass            # looks like this user wasn't in the list

        # Get the email address. We should just get the userdict with some fancy projection...
        # Finally delete the user and the unique email
        email = self.users.get_item(Key={ USER_ID :user_id},ConsistentRead=True)['Item'][ EMAIL ]
        client = self.dynamodb.meta.client
        logging.warning("Does not require the email exists in unique_emails. When we did that, it did not work.")
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
        course = self.courses.get_item(Key = { COURSE_ID :course_id}).get('Item',None)
        if not course:
            raise InvalidCourse_Id(course_id)
        return course


    def put_course(self, coursedict):
        """Puts the course into the database. Raises an error if the course already exists"""
        try:
            coursedict = Course(**coursedict).model_dump() # validate coursedict
        except ValidationError:
            logging.error("coursedict=%s",coursedict)
            raise

        ################ see if a course_key already exists
        try:
            resp = self.courses.query( IndexName='course_key_idx',
                                       KeyConditionExpression=Key('course_key').eq(coursedict['course_key']) )
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logging.error("Resource not found: %s. Perhaps table prefix is incorrect?",self.courses)
                raise ValueError(self.courses) from e
            logging.error("courses=%s",self.courses)
            raise
        if resp['Count'] > 0:
            raise ExistingCourse_Id(f"Course key {coursedict[COURSE_KEY]} already exists")
        logging.warning("Potential race condition if course_key=%s already exists",coursedict[COURSE_KEY])
        ################

        try:
            self.courses.put_item(Item=coursedict,
                                  ConditionExpression= 'attribute_not_exists(course_id)')
        except ClientError as e:
            logging.error("courses=%s coursedict=%s",self.courses,coursedict)
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                raise ExistingCourse_Id("Course already exists") from e
            raise


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

        logging.warning("scan the users and remove the course from every user that has it.")
        logging.warning("eliminate this scan by having the courses track their users.")
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
                    self.update_table(self.users, user[ USER_ID ], {'courses':courses})
            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break
        # done!


    def get_course_by_course_key(self, course_key):
        return self.courses.query( IndexName='course_key_idx',
                                   KeyConditionExpression=Key('course_key').eq(course_key)).get('Items')[0]

    ### movie management

    def get_movie(self, movie_id):
        if not is_movie_id(movie_id):
            raise InvalidMovie_Id(movie_id)
        return self.movies.get_item(Key = {MOVIE_ID:movie_id},ConsistentRead=True).get('Item')

    def put_movie(self, moviedict):
        assert is_movie_id(moviedict[MOVIE_ID])
        try:
            _moviedict = Movie(**moviedict).model_dump() # validate moviedict
        except ValidationError:
            logging.error("moviedict=%s",moviedict)
            raise
        self.movies.put_item(Item=moviedict)

    def batch_delete_movie_ids(self, ids):
        """Delete movie items from the table using batch_writer."""
        with self.movies.batch_writer() as batch:
            for theId in ids:
                assert is_movie_id(theId)
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
        return self.movie_frames.get_item(Key = {MOVIE_ID:movie_id, 'frame_number':frame_number}).get('Item')

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
    logging.debug("%s %s(%s) = %s ", user_ipaddr, func_name, func_args, func_return)

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
    'users' - all the users to which the user has access, and all of the people in them.
    'courses' - all of the courses to which the user has access, and all the people in them.
    :param: user_id - the user doing the listing (determines what they can see)

    NOTE: With MySQL users could only see the course list if they were admins.
    With DynamoDB, users can see the full course list for all of their courses.
    """
    ddbo = DDBO()
    user = ddbo.get_user(user_id)
    return {USERS: [user],
            COURSES :  [ddbo.get_course(course_id) for course_id in user[ COURSES ] ] }


def list_admins():
    """Returns dict of all the admins and the courses in which they are admins."""
    dd = DDBO()
    admin_users = defaultdict(list)
    last_evaluated_key = None

    while True:
        scan_kwargs = {}
        if last_evaluated_key:
            scan_kwargs['ExclusiveStartKey'] = last_evaluated_key

        response = dd.courses.scan(**scan_kwargs)
        print("response=",response)
        for course in response['Items']:
            print("course=",course)
            for user_id in course[ADMINS_FOR_COURSE]:
                print("user_id=",user_id)
                admin_users[user_id].append(course[COURSE_ID])
        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break
    return admin_users

def list_demo_users():
    """Returns a list of all demo accounts."""
    logging.warning("Scanning users for demo accounts")
    ddbo = DDBO()
    demo_users = []
    last_evaluated_key = None

    while True:
        scan_kwargs = { 'FilterExpression': Attr('demo').eq(1) }

        if last_evaluated_key:
            scan_kwargs['ExclusiveStartKey'] = last_evaluated_key

        response = ddbo.users.scan(**scan_kwargs)
        demo_users.extend(response['Items'])
        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break
    return demo_users

# pylint: disable=too-many-arguments
def register_email(email, full_name, *, course_key=None, course_id=None, demo_user=0, admin=False):
    """Register a user as identified by their email address for a given course.
    If the user exists, just change their primary course Id and add them to the course.
    If the user does not exist, create them.
    - Add the user to the specified course.
    - If the user is admin, add them to the list of course admins

    Does not make an api_key or send the links with the api_key.
    :param email: - user email
    :param course_key: - the key. We might only have this, if the user went to the we page
    :param course_id:  - the course
    :param demo_user:  - 1 if this is a demo user
    :param admin:      - True if this is a course admin
    :return: dictionary of { USER_ID :user_id} for user who is registered.
    """

    assert isinstance(email,str)
    if '@' not in email:
        raise InvalidUser_Email()

    if (course_key is None) and (course_id is None):
        raise ValueError("Either the course_key or the course_id must be provided")

    # Get the course name and (optionally) course_id
    ddbo = DDBO()
    if course_id is not None:
        course = ddbo.get_course(course_id)
    else:
        try:
            course = ddbo.get_course_by_course_key(course_key)
            course_id = course[COURSE_ID]
        except (IndexError,TypeError) as e:
            raise InvalidCourse_Key(course_key) from e

    # We don't know if the user exists or not. So do a put assuming that they don't.
    # If they do, we will then do an update.
    admin_for_courses = []
    if admin:
        admin_for_courses = [course_id]
    try:
        user_id = new_user_id()
        ddbo.put_user({USER_ID:user_id,
                       EMAIL:email,
                       FULL_NAME:full_name,
                       'created' : int(time.time()),
                       DEMO:demo_user,
                       ENABLED:1,
                       ADMIN_FOR_COURSES:admin_for_courses,
                       PRIMARY_COURSE_ID:course_id,
                       PRIMARY_COURSE_NAME:course[COURSE_NAME],
                       COURSES:[course_id]
                       })
    except UserExists:
        # The user exists! Change the primary course and add them to this course.
        user = ddbo.get_user_email(email)
        admin_for_courses = user[ADMIN_FOR_COURSES]
        if admin:
            admin_for_courses = list(set(admin_for_courses).union([course_id]))
        logging.debug("user=%s",user)
        ddbo.update_table(ddbo.users, user_id,
                          {PRIMARY_COURSE_ID:  course[ COURSE_ID ],
                           PRIMARY_COURSE_NAME:course[ COURSE_NAME ],
                           DEMO:demo_user,
                           COURSES: list(set(user[ COURSES ] + [course_id])),
                           ADMIN_FOR_COURSES: admin_for_courses})

        user_id = user[ USER_ID ]

    # Add the user to the course registration.
    ddbo.course_users.put_item(Item={COURSE_ID:course_id, USER_ID:user_id})

    # Add the user to the course admins if the user is an admin
    if admin:
        course = ddbo.get_course(course_id)
        ddbo.update_table(ddbo.courses, course_id,
                          {ADMINS_FOR_COURSE: list(set(course[ADMINS_FOR_COURSE] + [user_id]))})
    return {USER_ID:user_id}


@log
def unregister_from_course(*, course_id, user_id):
    """Remove user_id from course_id, but do not make other changes."""
    ddbo = DDBO()
    user = ddbo.get_user(user_id)
    try:
        user[COURSES].remove(course_id)
        ddbo.update_table(ddbo.users, user_id, {COURSES:user[COURSES]})
    except ValueError:
        pass
    ddbo.course_users.delete_item(Key={COURSE_ID:course_id, USER_ID:user_id})

@log
def delete_user(*, user_id, purge_movies=False):
    ddbo = DDBO()
    user = ddbo.get_user(user_id)
    # Remove the student from every course
    for course_id in user[COURSES]:
        unregister_from_course(course_id=course_id, user_id = user_id)

    ddbo.delete_user(user_id=user_id, purge_movies=purge_movies)


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
    if not is_api_key(api_key):
        raise InvalidAPI_Key()
    api_key_dict = ddbo.get_api_key_dict(api_key)
    print("api_key_dict:",api_key_dict)
    if api_key_dict[ ENABLED ]:
        user = ddbo.get_user(api_key_dict[ USER_ID ])
        if user[ ENABLED ]:
            first_used_at = api_key_dict.get('first_used_at',int(time.time()))
            ddbo.update_table(ddbo.api_keys,api_key,
                              { USE_COUNT :api_key_dict[ USE_COUNT ]+1,
                               'last_used_at':int(time.time()),
                               'first_used_at':first_used_at})
            return user
    raise InvalidAPI_Key()

def make_new_api_key(*, email):
    """Create a new api_key for an email that is registered
    :param: email - the email
    :return: api_key - the api_key
    """
    ddbo = DDBO()
    user = ddbo.get_user_email(email)
    if user[ ENABLED ] == 1:
        api_key = new_api_key()
        ddbo.put_api_key_dict({API_KEY:api_key,
                               ENABLED:1,
                               USER_ID :user[ USER_ID ],
                               USE_COUNT:0,
                               CREATED:int(time.time()) })
        return api_key
    raise InvalidUser_Email(email)


@log
def get_user(user_id):
    return DDBO().get_user(user_id)

def get_user_email(email):
    return DDBO().get_user_email(email)

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
def create_course(*, course_id, course_name, course_key, max_enrollment=C.DEFAULT_MAX_ENROLLMENT):
    """Create a new course
    """
    DDBO().put_course({ COURSE_ID :course_id,
                        COURSE_NAME:course_name,
                        COURSE_KEY:course_key,
                        ADMINS_FOR_COURSE:[],
                        MAX_ENROLLMENT:max_enrollment})

@log
def delete_course(*,course_id):
    """Delete a course.
    """
    DDBO().del_course(course_id)

@log
def add_course_admin(*, admin_id, course_id):
    """Promotes the user to be an administrator and makes them an administrator of a specific course.
    :param email: email address of the administrator
    :param course_id: - if specified, use this course_id
    :returns {'user_id':admin_id, 'admin_id':admin_id, 'course_id':course_id }
    """
    ddbo = DDBO()
    admin = ddbo.get_user(admin_id)
    course = ddbo.get_course(course_id)
    courses           = list(set(admin[ COURSES ] + [course_id]))
    admin_for_courses = list(set(admin[ ADMIN_FOR_COURSES ] + [course_id]))

    ddbo.update_table(ddbo.users,
                      admin_id,
                      {PRIMARY_COURSE_ID:course_id,
                       PRIMARY_COURSE_NAME:course[COURSE_NAME],
                       COURSES: courses,
                       ADMIN_FOR_COURSES: admin_for_courses})


    ddbo.update_table(ddbo.courses, course_id,
                      { ADMINS_FOR_COURSE:list(set(course[ ADMINS_FOR_COURSE ] + [admin_id]))})

    return { USER_ID :admin_id, 'admin_id':admin_id, COURSE_ID :course_id}


@log
def remove_course_admin(*, course_id, admin_id):
    """Removes email from the course admin list and takes them out of the course."""
    ddbo = DDBO()

    ## Update admin in users.

    admin  = ddbo.get_user( admin_id )

    try:
        courses = admin[ COURSES ]
        courses.remove(course_id)
        ddbo.update_table(ddbo.users, admin_id,
                           { COURSES:courses,
                            PRIMARY_COURSE_ID:None,
                            PRIMARY_COURSE_NAME:None})

    except ValueError:
        logging.warning("removing courses from %s from user %s",course_id,admin_id)

    try:
        admin_for_courses = admin[ ADMIN_FOR_COURSES ]
        admin_for_courses.remove(course_id)
        ddbo.update_table(ddbo.users, admin_id,
                           { ADMIN_FOR_COURSES:admin_for_courses,
                            PRIMARY_COURSE_ID:None,
                            PRIMARY_COURSE_NAME:None})

    except ValueError:
        logging.warning("remove admin_for_courses fail: %s from user %s",course_id,admin_id)

    ## Update admin in courses

    course = ddbo.get_course( course_id )
    assert course is not None
    assert course[ADMINS_FOR_COURSE] is not None
    try:
        admins_for_course = course[ADMINS_FOR_COURSE]
        admins_for_course.remove(admin_id)
        ddbo.update_table(ddbo.courses, course_id,{ADMINS_FOR_COURSE:admins_for_course})

    except ValueError:
        logging.warning("course admin remove fail: admin %s from course %s",admin_id,course_id)


@log
def check_course_admin(*, user_id, course_id):
    """Return True if user_id is an admin in course_id"""
    logging.info("TODO: Make get_user more efficient by just getting the attribute ADMIN_FOR_COURSES")
    assert is_user_id(user_id)
    assert isinstance(course_id,str)
    user = DDBO().get_user(user_id)
    logging.debug("user=%s",user)
    return course_id in user[ ADMIN_FOR_COURSES ]

@log
def validate_course_key(*, course_key):
    if DDBO().get_course_by_course_key(course_key):
        return True
    return False

@log
def remaining_course_registrations(*,course_key):
    ddbo = DDBO()
    course = ddbo.get_course_by_course_key(course_key)
    if not course:
        return 0
    course_id = course[ COURSE_ID ]
    enrolled = course_enrollments(course_id)
    return course['max_enrollment'] - len(enrolled)

@log
def course_enrollments(course_id):
    """Return a list of all those enrolled in the course (including staff)"""
    """Gets all the movie frames"""
    ddbo = DDBO()
    user_ids = []
    last_evaluated_key = None

    while True:
        query_kwargs = { 'KeyConditionExpression': Key( COURSE_ID ).eq( course_id ) }

        if last_evaluated_key:
            query_kwargs['ExclusiveStartKey'] = last_evaluated_key
        response = ddbo.course_users.query(**query_kwargs)
        user_ids.extend( (item[USER_ID] for item in response['Items']) )
        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break
    return user_ids



########################
### Movie Management ###
########################

@log
def get_movie_data(*, movie_id, zipfile=False, get_urn=False):
    """Returns the movie contents for a movie_id.
    If urn==True, just return the urn
    """
    movie = DDBO().get_movie(movie_id)
    try:
        if zipfile:
            urn = movie['movie_zipfile_urn']
        else:
            urn = movie['movie_data_urn']
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
    :return: list of movies
    """
    logging.warning("UNNEDED USERID QUERY")
    logging.warning("TK: replace get_movie_metadata with list_movies")
    logging.warning("ignored: get_last_frame_tracked=%s",get_last_frame_tracked)
    ddbo = DDBO()
    user = ddbo.get_user(user_id)
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
    logging.warning("UNNEDED USERID QUERY")
    logging.warning("UNNEDED USERID QUERY2")
    ddbo = DDBO()
    movie = ddbo.get_movie(movie_id)
    if movie[ USER_ID ] == user_id:
        return True
    user = ddbo.get_user(user_id)
    logging.debug("Can user '%s' access movie '%s'",json.dumps(user,default=str),json.dumps(movie,default=str))
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
                    TITLE:title,
                    'description':description,
                    'orig_movie':orig_movie,
                    PUBLISHED: 0,
                    DELETED: 0,
                    'movie_zipfile_urn':None,
                    MOVIE_DATA_URN:None,
                    'last_frame_tracked':None,
                    'created_at':int(time.time()),
                    'date_uploaded':None,
                    TOTAL_FRAMES:None, # will be set later
                    TOTAL_BYTES:None,  # will be set later
                    VERSION:0  # will be set to 1 with set_movie_data
                    })
    return movie_id

def get_movie(*, movie_id):
    """Returns the movie's data"""
    return DDBO().get_movie(movie_id)

#def set_movie_metadata(*, movie_id, movie_metadata):
#    """Set the movie_metadata from a dictionary. If fps is present, turn to a string because DynamoDB cannot store floats"""
#
#    logging.debug("movie_id=%s movie_metadata=%s",movie_id,movie_metadata)
#    assert is_movie_id(movie_id)
#    assert MOVIE_ID not in movie_metadata
#    assert 'id' not in movie_metadata
#    if 'fps' in movie_metadata:
#        movie_metadata = copy.copy(movie_metadata)
#        movie_metadata['fps'] = str(movie_metadata['fps'])
#    ddbo = DDBO()
#    ddbo.update_table(ddbo.movies, movie_id, movie_metadata)


def set_movie_data(*,movie_id, movie_data):
    """If we are setting the movie data, be sure that any old data (frames, zipfile, stored objects) are gone.
    increments version.
    """
    assert is_movie_id(movie_id)
    ddbo = DDBO()
    movie = ddbo.get_movie(movie_id)

    logging.debug("got movie=%s version=%s",movie,movie[VERSION])
    purge_movie_data(movie_id=movie_id)
    purge_movie_frames( movie_id=movie_id )
    purge_movie_zipfile( movie_id=movie_id )
    object_name = db_object.object_name( course_id = course_id_for_movie_id( movie_id ),
                                        movie_id = movie_id,
                                        ext=C.MOVIE_EXTENSION)
    movie_data_urn        = db_object.make_urn( object_name = object_name)

    db_object.write_object(movie_data_urn, movie_data)
    ddbo.update_table(ddbo.movies, movie_id, {MOVIE_DATA_URN:movie_data_urn,
                                              DATE_UPLOADED:int(time.time()),
                                              TOTAL_BYTES:len(movie_data),
                                              TOTAL_FRAMES:None,
                                              VERSION:movie[VERSION]+1 })

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
    logging.debug("purge_movie_data movie_id=%s",movie_id)
    ddbo = DDBO()
    urn = ddbo.get_movie(movie_id).get(MOVIE_DATA_URN,None)
    if urn:
        db_object.delete_object( urn )
        ddbo.update_table(ddbo.movies,movie_id, {MOVIE_DATA_URN:None})

@log
def purge_movie_frames(*,movie_id):
    """Delete the frames and zipfile associated with a movie."""
    logging.debug("purge_movie_frames movie_id=%s",movie_id)
    ddbo = DDBO()
    frames = ddbo.get_frames( movie_id )

    for frame in frames:
        frame_urn = frame.get('frame_urn',None)
        if frame_urn is not None:
            db_object.delete_object(frame_urn)
    ddbo.delete_movie_frames( frames )


@log
def purge_movie_zipfile(*,movie_id):
    """Delete the frames associated with a movie."""
    logging.debug("purge_movie_data movie_id=%s",movie_id)
    ddbo = DDBO()
    movie = ddbo.get_movie(movie_id)
    if movie.get('movie_zipfile_urn',None) is not None:
        db_object.delete_object(movie['movie_zipfile_urn'])
        ddbo.update_table(ddbo.movies, movie_id, {'movie_zipfile_urn':None})

@log
def purge_movie(*,movie_id):
    """Actually delete a movie and all its frames"""
    purge_movie_data(movie_id=movie_id)
    purge_movie_frames( movie_id=movie_id )
    purge_movie_zipfile( movie_id=movie_id )


@log
def delete_movie(*,movie_id, delete=1):
    """Set a movie's deleted bit to be true"""
    assert delete in (0,1)
    ddbo = DDBO()
    ddbo.update_table(ddbo.movies,movie_id, {DELETED:delete})


################################################################
## frames
################################################################

@functools.lru_cache(maxsize=128)
def course_id_for_movie_id(movie_id):
    logging.warning("INEFFICIENT CALL")
    return DDBO().get_movie(movie_id)[ COURSE_ID ]

@functools.lru_cache(maxsize=128)
def movie_data_urn_for_movie_id(movie_id):
    logging.warning("INEFFICIENT CALL")
    return DDBO().get_movie(movie_id)[MOVIE_DATA_URN]


@functools.lru_cache(maxsize=128)
def movie_zipfile_urn_for_movie_id(movie_id):
    logging.warning("INEFFICIENT CALL. Perhaps make it just get the item requested")
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
    logging.debug("create_new_movie_frame(movie_id=%s, frame_number=%s, type(frame_data)=%s",movie_id, frame_number, type(frame_data))
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
    logging.debug("movie_id=%s frame_number=%s",movie_id,frame_number)
    frame = DDBO().get_movie_frame(movie_id, frame_number)
    if frame is None:
        return None
    return frame.get('frame_urn',None)


def get_frame_data(*, movie_id, frame_number):
    """Get a frame by movie_id and either frame number.
    Don't log this to prevent blowing up.
    :param: movie_id - the movie_id wanted
    :param: frame_number - provide one of these. Specifies which frame to get
    :return: returns the frame data or None
    """
    logging.warning("We should only get the value that we need")
    frame_urn = DDBO().get_movie_frame(movie_id, frame_number)['frame_urn']
    return db_object.read_object(frame_urn)


################################################################
## Trackpoints

def iter_movie_frames_in_range(table, movie_id, f1, f2):
    """Yield movie_frame records for movie_id where frame_number is between f1 and f2."""
    last_evaluated_key = None

    while True:
        query_kwargs = { }

        if last_evaluated_key:
            query_kwargs['ExclusiveStartKey'] = last_evaluated_key

        response = table.query(KeyConditionExpression = Key(MOVIE_ID).eq(movie_id)
                               & Key('frame_number').between(Decimal(f1), Decimal(f2)),
                               **query_kwargs)

        for i in response['Items']:
            logging.debug("a frame response=%s",i)
            assert i['trackpoints'] != 'd'

        yield from response['Items']

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
    for frame in iter_movie_frames_in_range( DDBO().movie_frames, movie_id,
                                             frame_start, frame_start+frame_count ):
        for tp in frame['trackpoints']:
            ret.append({'frame_number':int(frame['frame_number']),
                        'x':int(tp['x']),
                        'y':int(tp['y']),
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
            iter_movie_frames_in_range( DDBO().movie_frames, movie_id, frame_start, frame_start+frame_count ) ]


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

def put_frame_trackpoints(*, movie_id, frame_number:int, trackpoints:list[dict]):
    """
    :frame_number: the frame to replace. If the frame has existing trackpoints, they are overwritten
    :param: trackpoints - array of dicts where each dict has an x, y and label. Other fields are ignored.
    """
    # Remove numpy from trackpoints
    trackpoints = [ Trackpoint(**tp).model_dump() for tp in trackpoints ]
    logging.debug("put trackpoints frame=%s trackpoints=%s",frame_number,trackpoints)

    DDBO().movie_frames.update_item( Key={MOVIE_ID:movie_id,
                                          'frame_number':frame_number},
                                     UpdateExpression='SET trackpoints=:val',
                                     ExpressionAttributeValues={':val':trackpoints})




################################################################

def list_movies(*,user_id, movie_id=None, orig_movie=None):
    """Return a list of movies that the user is allowed to access.
    This should be updated so that we can request only a specific movie
    :param: user_id - only list movies visible to user_id (0 for all movies)
    :param: movie_id - if provided, only use this movie
    :param: orig_movie - if provided, only list movies for which the original movie is orig_movie_id
    """
    if movie_id is not None:
        assert is_movie_id(movie_id)
    if orig_movie is not None:
        assert is_movie_id(orig_movie)

    ddbo = DDBO()
    user = ddbo.get_user(user_id)
    if orig_movie is not None:
        raise NotImplementedError("orig_movie not implemented")
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

# pylint: disable=too-many-arguments, too-many-branches
def get_logs( *, user_id , start_time = 0, end_time = None, course_id=None,
              log_user_id=None,
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
        response = ddbo.logs.query(**kwargs)
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

    #
    if security:
        logging.warning("TODO: If the user %s is not an admin on the course %s, they can only see their own logs",user_id,course_id)

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
    DELETED: 'update movies set deleted=%s where id=%s and (@is_owner or (@is_admin and deleted=0))',

    # the admin can publish or unpublish movies; the user can only unpublish them
    PUBLISHED: 'update movies set published=%s where id=%s and (@is_admin or (@is_owner and published!=0))',
}

def will_it_float(s):
    if not isinstance(s, str):
        return False
    return re.match(r'^-?\d+(?:\.\d+)$', s) is not None

def will_it_int(s):
    if not isinstance(s, str):
        return False
    return re.match(r'^-?\d+$', s) is not None

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
    logging.debug("set_user_id=%s set_movie_id=%s prop=%s value=%s", set_user_id, set_movie_id, prop, value)
    assert is_user_id(user_id)
    assert is_movie_id(set_movie_id) or (set_movie_id is None)
    assert is_user_id(set_user_id) or (set_user_id is None)
    assert isinstance(prop, str)
    assert value is not None

    if isinstance(value, float):
        logging.debug("1. Converted %s %s -> %s",prop,value,str(value))
        value = str(value)
    if will_it_float(value):
        logging.debug("2. Converting %s",value)
        value = Decimal(value)
    if will_it_int(value):
        logging.debug("3. Converting %s",value)
        value = int(value)

    logging.debug("prop=%s value=%s type=%s",prop,value,type(value))

    ddbo = DDBO()

    if set_movie_id is not None:
        # Fix the data type
        value = validate_movie_field(prop, value)
        movie = ddbo.get_movie(set_movie_id)
        if user_id != ROOT_USER_ID:
            # Check permissions
            user = ddbo.get_user(user_id)
            is_owner = movie[ USER_ID ] == user_id
            is_admin = movie[ COURSE_ID ] in user[ ADMIN_FOR_COURSES ]

            acl  = SET_MOVIE_METADATA[prop]
            logging.debug("is_owner=%s is_admin=%s acl=%s",is_owner, is_admin, acl)

            if not ((is_owner is not None and '@is_owner' in acl) or (is_admin is not None and '@is_admin' in acl)):
                # permission not granted
                raise UnauthorizedUser("permission denied")

        ddbo.update_table(ddbo.movies, set_movie_id, {prop:value})
    elif set_user_id is not None:
        if user_id != ROOT_USER_ID:
            # Check Permissions
            set_user = ddbo.get_user(set_user_id)
            is_owner = user_id == set_user_id
            is_admin = any( ( (course_id in set_user[ ADMIN_FOR_COURSES ])  for course_id in set_user[ COURSES ] ) )

            if is_owner or is_admin:
                if prop not in [  NAME ,  EMAIL ]:
                    raise UnauthorizedUser('currently users can only set name and email')
        ddbo.update_table(ddbo.users, set_user_id, {prop:value})
    else:
        raise ValueError("set set_user_id or set_movie_id must be provided")
