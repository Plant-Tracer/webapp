import uuid
import boto3
import os
import time
import subprocess
import json

import pytest

from app import odb
from app.odb import DDBO
from app import odbmaint
from app.constants import MIME,C

MYDIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname( MYDIR )

TEST_ADMIN_ID = odb.new_user_id()
TEST_ADMIN_EMAIL = 'new.user@example.com'
TEST_COURSE_ID = 'test-course-' + str(uuid.uuid4())[0:4]
TEST_COURSE_NAME = 'Introduction to Plant Tracer'
TEST_MOVIE_ID = odb.new_movie_id()
TEST_COURSE_KEY = 'k-' + str(uuid.uuid4())[0:4]

TEST_COURSE_DATA = {
    'course_id': TEST_COURSE_ID,
    'course_name': TEST_COURSE_NAME,
    'course_key': TEST_COURSE_KEY,
    'course_admins': [TEST_ADMIN_ID]
}

TEST_USER_ID = odb.new_user_id()
TEST_USER_EMAIL = 'new.user@example.com'
TEST_USER_DATA = {
    'user_id': TEST_USER_ID,
    'email': TEST_USER_EMAIL,
    'full_name': 'Firstname Lastname',
    'created': int(time.time()),
    'enabled': 1,
    'demo': 0,
    'admin': [],
    'admin_for_courses': [TEST_COURSE_ID],
    'primary_course_id': TEST_COURSE_ID,
    'primary_course_name': TEST_COURSE_NAME,
}

TEST_ADMIN_DATA = {
    'user_id': TEST_USER_ID,
    'email': TEST_USER_EMAIL,
    'full_name': 'Admin Firstname Lastname',
    'created': int(time.time()),
    'enabled': 1,
    'demo': 0,
    'admin': [TEST_COURSE_ID],
    'courses': [TEST_COURSE_ID],
    'primary_course_id': TEST_COURSE_ID,
    'primary_course_name': TEST_COURSE_NAME,
}

TEST_MOVIE_DATA = {
    'movie_id': TEST_MOVIE_ID,
    'course_id': TEST_COURSE_ID,
    'user_id': TEST_USER_ID,
    'title': 'My New Awesome Movie',
    'isPublished': 0,
    'isDeleted': 0,
    'description': 'A fantastic new movie project.'
}

ENDPOINT_URL = 'http://localhost:8010'

@pytest.fixture
def ddbo():
    """Create an empty DynamoDB locally.
    Starts the database if it is not running.
    """
    subprocess.call( [os.path.join(ROOT_DIR,'local_dynamodb_control.bash'),'start'])

    # Make a random prefix for this run.
    # Make sure that the tables don't exist, then create them

    os.environ['AWS_DEFAULT_REGION'] = 'local'
    os.environ['DYNAMODB_ENDPOINT_URL'] = ENDPOINT_URL
    os.environ['DYNAMODB_TABLE_PREFIX'] = str(uuid.uuid4())[0:4]
    ddbo = DDBO()
    odbmaint.drop_tables(ddbo)
    odbmaint.create_tables(ddbo)
    return ddbo

def test_odb(ddbo):
    start_time = int(time.time())

    ddbo.put_user(TEST_USER_DATA)
    assert ddbo.get_user(TEST_USER_ID) == TEST_USER_DATA
    assert ddbo.get_user(None, email=TEST_USER_EMAIL) == TEST_USER_DATA

    ddbo.put_movie(TEST_MOVIE_DATA)
    assert ddbo.get_movie(TEST_MOVIE_ID) == TEST_MOVIE_DATA
    assert ddbo.get_movies_for_user_id(TEST_USER_ID) == [TEST_MOVIE_ID]

    ddbo.put_course(TEST_COURSE_DATA)
    assert ddbo.get_course(TEST_COURSE_ID) == TEST_COURSE_DATA

    # test api_key management

    api_key = ddbo.make_new_api_key( email = TEST_USER_EMAIL)
    assert odb.is_api_key(api_key)
    user = ddbo.validate_api_key(api_key)
    assert user == TEST_USER_DATA
    a2   = ddbo.get_api_key_dict(api_key)
    assert a2['enabled'] == 1
    assert a2['use_count'] == 1
    assert a2['created'] >= start_time
    assert a2['last_used_at'] >= a2['first_used_at'] >= a2['created']
    ddbo.del_api_key(api_key)

    a3   = ddbo.get_api_key_dict(api_key)
    assert a3 == None


    # test user management
    new_email = TEST_USER_EMAIL+"-new"
    ddbo.rename_user(user_id=TEST_USER_ID, new_email=new_email)
    u1 = ddbo.get_user(TEST_USER_ID)
    u2 = ddbo.get_user(None, email=new_email)
    print("u1=",json.dumps(u1,indent=4,default=str))
    print("u2=",json.dumps(u2,indent=4,default=str))
    assert u1==u2
    assert u1['email'] == TEST_USER_EMAIL+"-new"

    # Try to delete the user
    with pytest.raises(RuntimeError,match=r'.* has 1 outstanding movie.*'):
        ddbo.delete_user(TEST_USER_ID)

    ddbo.delete_user(TEST_USER_ID, purge_movies=True)


    assert ddbo.get_user(TEST_USER_ID) is None
