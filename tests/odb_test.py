import uuid
import boto3
import os
import time
import subprocess

import pytest

from app import odb
from app.odb import DDBO
from app import odbmaint

MYDIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname( MYDIR )

TEST_USER_ID = odb.new_user_id()
TEST_USER_EMAIL = 'new.user@example.com'
TEST_COURSE_ID = odb.new_course_id()
TEST_MOVIE_ID = odb.new_movie_id()
TEST_USER_DATA = {
    'user_id': TEST_USER_ID,
    'email': TEST_USER_EMAIL,
    'name': 'Firstname Lastname',
    'created': int(time.time()),
    'enabled': 1,
    'demo': 0,
    'admin': [],
    'courses': [TEST_COURSE_ID],
    'primary_course_id': TEST_COURSE_ID,
}

TEST_COURSE_DATA = {
    'course_id': TEST_COURSE_ID,
    'name': 'Introduction to DynamoDB'
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
    os.environ['AWS_DEFAULT_REGION']='local'
    os.environ['DYNAMODB_ENDPOINT_URL']=ENDPOINT_URL
    subprocess.call( [os.path.join(ROOT_DIR,'local_dynamodb_control.bash'),'start'])
    odbmaint.create_schema(region_name='local', endpoint_url=ENDPOINT_URL)
    return DDBO(region_name=os.getenv('AWS_DEFAULT_REGION'),
              endpoint_url=os.getenv('DYNAMODB_ENDPOINT_URL'))

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
