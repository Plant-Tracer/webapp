import uuid
import boto3
import os
import time
import subprocess
import json
from decimal import Decimal

from botocore.exceptions import ClientError,ParamValidationError

import pytest

from app import odb
from app.odb import DDBO
from app import odbmaint
from app.constants import MIME,C

ENDPOINT_URL = 'http://localhost:8010'

MYDIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname( MYDIR )

TEST_ADMIN_ID = odb.new_user_id()
TEST_ADMIN_EMAIL = 'new.user@example.com'
TEST_COURSE_ID = 'test-course-' + str(uuid.uuid4())[0:4]
TEST_COURSE_NAME = 'Introduction to Plant Tracer'
TEST_MOVIE_ID = odb.new_movie_id()
TEST_COURSE_KEY = 'k-' + str(uuid.uuid4())[0:4]
TEST_COURSE_MAX_ENROLLMENT = 30
TEST_COURSE_DATA = {
    'course_id': TEST_COURSE_ID,
    'course_name': TEST_COURSE_NAME,
    'course_key': TEST_COURSE_KEY,
    'course_admins': [TEST_ADMIN_ID],
    'max_enrollment': TEST_COURSE_MAX_ENROLLMENT
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
    'admin': 0,
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
    'admin': 1,
    'courses': [TEST_COURSE_ID],
    'primary_course_id': TEST_COURSE_ID,
    'primary_course_name': TEST_COURSE_NAME,
}

TEST_MOVIE_DATA = {
    'movie_id': TEST_MOVIE_ID,
    'course_id': TEST_COURSE_ID,
    'user_id': TEST_USER_ID,
    'title': 'My New Awesome Movie',
    'published': 0,
    'deleted': 0,
    'description': 'A fantastic new movie project.',
    'movie_zipfile_urn':'s3://bogus/movie-data.zip',
    'movie_data_urn':'s3://bogus/movie-data.mp4',
    'last_frame_tracked':0,
    'created_at':int(time.time()),
    'date_uploaded':int(time.time()),
    'total_frames':10,
    'total_bytes':100
}

TEST_MOVIE_FRAME_DATA = {
    'movie_id': TEST_MOVIE_ID,
    'frame_number': 0,
    'frame_urn':'s3://bogus/movie-frame.jpg',
    'trackpoints':[{'x':Decimal(10),'y':Decimal(20),'label':'name1'},
                   {'x':Decimal(45),'y':Decimal(55),'label':'name2'}]
}


@pytest.fixture
def ddbo():
    """Create an empty DynamoDB locally.
    Starts the database if it is not running.
    """
    subprocess.call( [os.path.join(ROOT_DIR,'local_dynamodb_control.bash'),'start'])

    # Make a random prefix for this run.
    # Make sure that the tables don't exist, then create them

    os.environ['AWS_DEFAULT_REGION']    = 'local'
    os.environ['DYNAMODB_ENDPOINT_URL'] = ENDPOINT_URL
    os.environ['DYNAMODB_TABLE_PREFIX'] = 'test-'+str(uuid.uuid4())[0:4]
    ddbo = DDBO()
    odbmaint.drop_tables(ddbo)
    odbmaint.create_tables(ddbo)
    return ddbo

def test_odb(ddbo):
    start_time = int(time.time())

    # Create the user.
    ddbo.add_user(TEST_USER_DATA)
    # This should fail becuase the user we are putting exist
    with pytest.raises(ClientError):
        ddbo.add_user(TEST_USER_DATA)

    assert ddbo.get_user(TEST_USER_ID) == TEST_USER_DATA
    assert ddbo.get_user(None, email=TEST_USER_EMAIL) == TEST_USER_DATA

    # Create a course
    ddbo.put_course(TEST_COURSE_DATA)
    assert ddbo.get_course(TEST_COURSE_ID) == TEST_COURSE_DATA

    # Create a movie
    ddbo.put_movie(TEST_MOVIE_DATA)
    assert ddbo.get_movie(TEST_MOVIE_ID) == TEST_MOVIE_DATA
    assert ddbo.get_movies_for_user_id(TEST_USER_ID) == [TEST_MOVIE_DATA]

    # Create a movie frame
    ddbo.put_movie_frame(TEST_MOVIE_FRAME_DATA)
    assert len(ddbo.get_frames(TEST_MOVIE_ID)) == 1
    assert (odb.get_movie_trackpoints(movie_id= TEST_MOVIE_ID)
            == [{'frame_number': Decimal(0), 'x':Decimal(10), 'y':Decimal(20), 'label':'name1'},
                {'frame_number': Decimal(0), 'x':Decimal(45), 'y':Decimal(55), 'label':'name2'}])
    assert odb.last_tracked_movie_frame(movie_id=TEST_MOVIE_ID)==0
    ddbo.put_movie_frame({"movie_id":TEST_MOVIE_ID,
                         "frame_number":1,
                         "frame_urn":"s3://bogus/frame1"})

    # Give it some trackpoints
    odb.put_frame_trackpoints(movie_id=TEST_MOVIE_ID, frame_number=1,
                              trackpoints=[{'x':20, 'y':30, 'label':'name3'},
                                           {'x':65, 'y':85, 'label':'name4'}])
    assert odb.last_tracked_movie_frame(movie_id=TEST_MOVIE_ID)==1


    # Make an API key
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


    # rename the user
    new_email = TEST_USER_EMAIL+"-new"
    ddbo.rename_user(user_id=TEST_USER_ID, new_email=new_email)
    u1 = ddbo.get_user(TEST_USER_ID)
    u2 = ddbo.get_user(None, email=new_email)
    print("u1=",json.dumps(u1,indent=4,default=str))
    print("u2=",json.dumps(u2,indent=4,default=str))
    assert u1==u2
    assert u1['email'] == TEST_USER_EMAIL+"-new"

    # Try to delete the user without deleting the user's movies
    with pytest.raises(RuntimeError,match=r'.* has 1 outstanding movie.*'):
        ddbo.delete_user(TEST_USER_ID)

    # Now delete the user and their movies
    ddbo.delete_user(TEST_USER_ID, purge_movies=True)
    assert ddbo.get_user(TEST_USER_ID) is None

    # Delete the user's course
    odb.delete_course(course_id=TEST_COURSE_ID)
