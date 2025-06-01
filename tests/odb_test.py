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

TEST_USER_ID = str(uuid.uuid4()) # uuid.uuid4() generates a UUID object, convert to string
TEST_USER_EMAIL = 'new.user@example.com'
TEST_COURSE_ID = str(uuid.uuid4()) # Generate ID for course
TEST_MOVIE_ID = str(uuid.uuid4()) # Generate ID for movie
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
    ddbo.put_user(TEST_USER_DATA)
    assert ddbo.get_user(TEST_USER_ID) == TEST_USER_DATA
    assert ddbo.get_user(None, email=TEST_USER_EMAIL) == TEST_USER_DATA

    # I want these to filter...
    #assert odb.get_all_x_for_y(ddbo.users, 'user_id', 'enabled', 1) == [TEST_USER_ID]
    #assert odb.get_all_x_for_y(ddbo.users, 'user_id', 'enabled', 0) == []
    #assert odb.get_all_x_for_y(ddbo.users, 'name', 'enabled', 1) == [TEST_USER_NAME]
    #assert odb.get_all_x_for_y(ddbo.users, 'name', 'enabled', 0) == []

    ddbo.put_movie(TEST_MOVIE_DATA)
    assert ddbo.get_movie(TEST_MOVIE_ID) == TEST_MOVIE_DATA
    assert ddbo.get_movies_for_user_id(TEST_USER_ID) == [TEST_MOVIE_ID]

    ddbo.put_course(TEST_COURSE_DATA)
    assert ddbo.get_course(TEST_COURSE_ID) == TEST_COURSE_DATA
