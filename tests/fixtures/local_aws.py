"""
These fixtures set environment variables for running DynamoDB Local and minio

"""

import logging
import copy
import uuid
import pytest
import os
import subprocess
import random
from os.path import join,dirname,abspath

import boto3

from app.constants import C
from app import odb
from app import odbmaint
from app import db_object

from app.paths import ROOT_DIR,TEST_DATA_DIR
from app.odb import DDBO,VERSION,API_KEY,COURSE_KEY,COURSE_ID,COURSE_NAME,USER_ID,MOVIE_ID,DELETED,PUBLISHED

DELETE_TEST_TABLES = True

s3client = boto3.client('s3')

TEST_USER_EMAIL  = 'test_user@company.com'       # from configure
TEST_USER_NAME   = 'Test User Name'
TEST_DEMO_EMAIL  = 'test_demo@company.com'        # completely bogus
TEST_ADMIN_EMAIL = 'test_admin@company.com'     # configuration
TEST_ADMIN_NAME  = 'Test Admin Name'

# additional keys for scaffolding dictionary
ADMIN_EMAIL = 'admin_email'
DEMO_EMAIL = 'demo_mail'
ADMIN_ID = 'admin_id'
USER_EMAIL = 'user_email'
MOVIE_TITLE = 'movie_title'

TEST_PLANTMOVIE_PATH = os.path.join(TEST_DATA_DIR, "2019-07-31 plantmovie.mov")
TEST_PLANTMOVIE_ROTATED_PATH = os.path.join(TEST_DATA_DIR, "2019-07-31 plantmovie-rotated.mov")
TEST_CIRCUMNUTATION_PATH = os.path.join(TEST_DATA_DIR,'2019-07-12 circumnutation.mp4')

def new_email(info):
    return TEST_USER_EMAIL.replace('@', '-' + info + '-'+str(uuid.uuid4())[0:4]+'@')

@pytest.fixture(scope="session")
def local_ddb():
    """Create an empty DynamoDB locally.
    Starts the database if it is not running.
    """
    subprocess.call( [os.path.join(ROOT_DIR,'bin/local_dynamodb_control.bash'),'start'])

    # Make a random prefix for this run.
    # Make sure that the tables don't exist, then create them

    os.environ[ C.AWS_DEFAULT_REGION ]    = 'local'
    os.environ[ C.AWS_ENDPOINT_URL ]      = C.TEST_ENDPOINT_URL_DYNAMODB
    os.environ[ C.DYNAMODB_TABLE_PREFIX ] = 'test-'+str(uuid.uuid4())[0:4]
    os.environ[ C.AWS_ACCESS_KEY_ID ] = C.TEST_ACCESS_KEY_ID
    os.environ[ C.AWS_SECRET_ACCESS_KEY ]    = C.TEST_SECRET_ACCESS_KEY
    ddbo = DDBO()
    odbmaint.drop_tables(ddbo)
    odbmaint.create_tables(ddbo)
    yield ddbo
    if DELETE_TEST_TABLES:
        odbmaint.drop_tables(ddbo)

@pytest.fixture(scope="session")
def local_s3():
    """Create an empty S3 locally.
    Starts the database if it is not running.
    """
    subprocess.call( [os.path.join(ROOT_DIR,'bin/local_minio_control.bash'),'start'])

    save_bucket = os.getenv(C.PLANTTRACER_S3_BUCKET)
    save_endpoint = os.getenv(C.AWS_ENDPOINT_URL_S3)
    os.environ[C.PLANTTRACER_S3_BUCKET] = C.TEST_PLANTTRACER_S3_BUCKET
    os.environ[C.AWS_ENDPOINT_URL_S3] = C.TEST_ENDPOINT_URL_S3
    yield save_bucket
    if save_bucket:
        os.environ[C.PLANTTRACER_S3_BUCKET] = save_bucket
    else:
        del os.environ[C.PLANTTRACER_S3_BUCKET]
    if save_endpoint:
        os.environ[C.AWS_ENDPOINT_URL_S3] = save_endpoint
    else:
        del os.environ[C.AWS_ENDPOINT_URL_S3]


@pytest.fixture
def new_course(local_ddb, local_s3):
    """Fixture to create a new course with an admin and a user and yields a dictionary with all and then """

    course_id   = 'PlantTracer ' + str(random.randint(100,999))
    course_name = f"{course_id}: Watching your plants"
    course_key = 'test-'+str(uuid.uuid4())[0:32]

    odb.create_course(course_id = course_id,
                           course_name = course_name,
                           course_key = course_key)

    user_email = new_email('user')
    user_id  = odb.register_email(email=user_email, user_name='Course User', course_id = course_id, admin=0)[USER_ID]
    api_key = odb.make_new_api_key(email=user_email)

    admin_email = new_email('admin')
    admin_id = odb.register_email(email=admin_email, user_name='Course Admin', course_key=course_key, admin=1)[USER_ID]


    yield {'ddbo':local_ddb,
           COURSE_KEY:course_key,
           COURSE_NAME:course_name,
           COURSE_ID:course_id,
           ADMIN_EMAIL:admin_email,
           ADMIN_ID:admin_id,
           USER_ID:user_id,
           USER_EMAIL:user_email,
           API_KEY:api_key
           }

    odb.remove_course_admin(course_id = course_id, admin_id = admin_id)
    odb.delete_user(user_id=user_id, purge_movies=True)
    odb.delete_user(user_id=admin_id, purge_movies=True)
    odb.delete_course(course_id=course_id)

@pytest.fixture
def api_key(new_course):
    """Simple fixture that just returns a valid api_key"""
    assert odb.is_api_key(new_course[API_KEY])
    yield new_course[API_KEY]

@pytest.fixture
def new_movie(new_course):
    """Fixture that creates a new course, new user, and a new movie, returning a dictionary holding them all.
    Unlike movie_test.test_new_movie_api, this version goes directly to the database, rather than going through the API"""

    cfg = copy.copy(new_course)
    movie_title = f'test-movie title {str(uuid.uuid4())}'
    movie_id = odb.create_new_movie(user_id = cfg[ADMIN_ID],
                                    course_id = cfg[COURSE_ID],
                                    title = movie_title,
                                    description = 'Description')

    logging.debug("new_movie fixture: Opening %s",TEST_PLANTMOVIE_PATH)
    with open(TEST_PLANTMOVIE_PATH, "rb") as f:
        movie_data   = f.read()
        movie_data_sha256 = db_object.sha256(movie_data)
    assert len(movie_data) == os.path.getsize(TEST_PLANTMOVIE_PATH)
    assert len(movie_data) > 0

    odb.set_movie_data(movie_id = movie_id, movie_data = movie_data)
    movie = odb.get_movie(movie_id = movie_id)
    assert movie[DELETED] == 0
    assert movie[PUBLISHED] == 0
    assert movie[VERSION] == 1

    cfg[MOVIE_ID] = movie_id
    cfg[MOVIE_TITLE] = movie_title

    yield cfg

    odb.purge_movie(movie_id = movie_id)
    odb.delete_movie(movie_id = movie_id)
