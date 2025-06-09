"""
These fixtures set environment variables for running DynamoDB Local and minio

"""


import uuid
import pytest
import os
import subprocess
from os.path import join,dirname,abspath

import boto3

from app.constants import C
from app.paths import ROOT_DIR
from app import odb
from app.odb import DDBO
from app import odbmaint

DELETE_TEST_TABLES = True

s3client = boto3.client('s3')

TEST_USER_EMAIL  = 'test_user@company.com'       # from configure
TEST_USER_NAME   = 'Test User Name'
TEST_DEMO_EMAIL  = 'test_demo@company.com'        # completely bogus
TEST_ADMIN_EMAIL = 'test_admin@company.com'     # configuration
TEST_ADMIN_NAME  = 'Test Admin Name'

# keys for scaffolding dictionary
ADMIN_EMAIL = 'admin_email'
DEMO_EMAIL = 'demo_mail'
ADMIN_ID = 'admin_id'
API_KEY  = 'api_key'
COURSE_KEY = 'course_key'
COURSE_ID = 'course_id'
COURSE_NAME = 'course_name'
USER_EMAIL = 'user_email'
USER_ID    = 'user_id'
MOVIE_ID = 'movie_id'
MOVIE_TITLE = 'movie_title'
TEST_PLANTMOVIE_PATH = os.path.join(TEST_DATA_DIR, "2019-07-31 plantmovie.mov")
TEST_PLANTMOVIE_ROTATED_PATH = os.path.join(TEST_DATA_DIR, "2019-07-31 plantmovie-rotated.mov")
TEST_CIRCUMNUTATION_PATH = os.path.join(TEST_DATA_DIR,'2019-07-12 circumnutation.mp4')

def new_email(info):
    TEST_ADMIN_EMAIL.replace('@', '-' + info + '-'+str(uuid.uuid4())[0:4]+'@')


@pytest.fixture
def local_ddb():
    """Create an empty DynamoDB locally.
    Starts the database if it is not running.
    """
    subprocess.call( [os.path.join(ROOT_DIR,'local_dynamodb_control.bash'),'start'])

    # Make a random prefix for this run.
    # Make sure that the tables don't exist, then create them

    os.environ['AWS_DEFAULT_REGION']    = 'local'
    os.environ['DYNAMODB_ENDPOINT_URL'] = C.DYNAMODB_TEST_ENDPOINT_URL
    os.environ['DYNAMODB_TABLE_PREFIX'] = 'test-'+str(uuid.uuid4())[0:4]
    ddbo = DDBO()
    odbmaint.drop_tables(ddbo)
    odbmaint.create_tables(ddbo)
    yield ddbo
    if DELETE_TEST_TABLES:
        odbmaint.drop_tables(ddbo)

@pytest.fixture
def local_s3():
    save_bucket = os.getenv(C.PLANTTRACER_S3_BUCKET)
    save_endpoint = os.getenv(C.S3_ENDPOINT_URL)
    os.environ[C.PLANTTRACER_S3_BUCKET] = C.TEST_S3_BUCKET
    os.environ[C.S3_ENDPOINT_URL] = C.TEST_S3_ENDPOINT_URL
    os.environ[C.AWS_PROFILE ] = 'minio'
    yield save_bucket
    if save_bucket:
        os.environ[C.PLANTTRACER_S3_BUCKET] = save_bucket
    else:
        del os.environ[C.PLANTTRACER_S3_BUCKET]
    if save_endpoint:
        os.environ[C.S3_ENDPOINT_URL] = save_endpoint
    else:
        del os.environ[C.S3_ENDPOINT_URL]


@pytest.fixture
def new_course(local_ddb,local_s3):
    """Fixture to create a new course with an admin and a user and yields a dictionary with all and then """

    course_id   = 'PlantTracer ' + str(random.randint(100,999))
    course_name = f"{course_id}: Watching your plants"
    course_key = 'test-'+str(uuid.uuid4())[0:32]

    odb.create_course(course_id = course_id,
                           course_name = course_name,
                           course_key = course_key)

    admin = odb.register_email(email=new_email('admin'), full_name='Course Admin', course_key=course_key, admin=1)
    admin_id = admin[USER_ID]
    user  = odb.register_email(email=new_email('user'), full_name='Course User', course_id = course_id, admin=0)
    user_id = user[USER_ID]

    api_key = odb.make_new_api_key(user['email'])

    yield {'ddbo':local_ddb,
           COURSE_KEY:course_key,
           COURSE_NAME:course_name,
           COURSE_ID:course_id,
           ADMIN_EMAIL:admin[EMAIL],
           ADMIN_ID:admin_id,
           USER_ID:user_id,
           USER_EMAIL:user[EMAIL],
           PI_KEY:api_key }

    odb.remove_course_admin(course_id = course_id, admin_id = admin_id)
    odb.delete_user(user_id=user_id, purge_movies=True)
    odb.delete_user(user_id=admin_id, purge_movies=True)
    odb.delete_course(course_key=course_key)

@pytest.fixture
def api_key(new_course):
    """Simple fixture that just returns a valid api_key"""
    yield new_course_user[API_KEY]
