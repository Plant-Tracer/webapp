import json
import os
import time
import uuid
from decimal import Decimal

import pytest

from fixtures.local_aws import local_ddb

from app import odb
from app.odb import (COURSE_ID, InvalidUser_Id, LAST_FRAME_TRACKED,
                     MOVIE_ID, USER_ID, UserExists)

MYDIR = os.path.dirname(__file__)

TEST_ADMIN_ID = odb.new_user_id()
TEST_ADMIN_EMAIL = 'new.user@example.com'
TEST_COURSE_ID = 'test-course-' + str(uuid.uuid4())[0:4]
TEST_COURSE_NAME = 'Introduction to Plant Tracer'
TEST_MOVIE_ID = odb.new_movie_id()
TEST_COURSE_KEY = 'k-' + str(uuid.uuid4())[0:4]
TEST_COURSE_MAX_ENROLLMENT = 30
TEST_COURSE_DATA = {
    COURSE_ID: TEST_COURSE_ID,
    'course_name': TEST_COURSE_NAME,
    'course_key': TEST_COURSE_KEY,
    'admins_for_course': [TEST_ADMIN_ID],
    'max_enrollment': TEST_COURSE_MAX_ENROLLMENT
}

TEST_USER_ID = odb.new_user_id()
TEST_USER_EMAIL = 'new.user@example.com'
TEST_USER_NAME = 'Firstname Lastname'
TEST_USER_DATA = {
    USER_ID: TEST_USER_ID,
    'email': TEST_USER_EMAIL,
    'user_name': TEST_USER_NAME,
    'created': int(time.time()),
    'enabled': 1,
    'admin_for_courses': [],
    'courses': [],
    'primary_course_id': TEST_COURSE_ID,
    'primary_course_name': TEST_COURSE_NAME,
}

TEST_ADMIN_DATA = {
    USER_ID: TEST_USER_ID,
    'email': TEST_USER_EMAIL,
    'user_name': 'Admin Firstname Lastname',
    'created': int(time.time()),
    'enabled': 1,
    'admin_for_courses': [TEST_COURSE_ID],
    'courses': [TEST_COURSE_ID],
    'primary_course_id': TEST_COURSE_ID,
    'primary_course_name': TEST_COURSE_NAME,
}

TEST_MOVIE_DATA = {
    MOVIE_ID: TEST_MOVIE_ID,
    COURSE_ID: TEST_COURSE_ID,
    USER_ID: TEST_USER_ID,
    'user_name': TEST_USER_NAME,
    'title': 'My New Awesome Movie',
    'published': 0,
    'deleted': 0,
    'description': 'A fantastic new movie project.',
    'movie_zipfile_urn':'s3://bogus/movie-data.zip',
    'movie_data_urn':'s3://bogus/movie-data.mp4',
    LAST_FRAME_TRACKED:0,
    'created_at':int(time.time()),
    'date_uploaded':int(time.time()),
    'fps':"29.92",
    'total_frames':10,
    'total_bytes':100
}

TEST_MOVIE_FRAME_DATA = {
    MOVIE_ID: TEST_MOVIE_ID,
    'frame_number': 0,
    'frame_urn':'s3://bogus/movie-frame.jpg',
    'trackpoints':[{'x':Decimal(10),'y':Decimal(20),'label':'name1'},
                   {'x':Decimal(45),'y':Decimal(55),'label':'name2'}]
}


def test_odb(local_ddb):
    ddbo = local_ddb
    start_time = int(time.time())

    # Create the course
    ddbo.put_course(TEST_COURSE_DATA)
    assert ddbo.get_course(TEST_COURSE_ID) == TEST_COURSE_DATA

    # Create the user.
    ddbo.put_user(TEST_USER_DATA)
    # This should fail because the user we are putting exist
    with pytest.raises(UserExists):
        ddbo.put_user(TEST_USER_DATA)

    # Register the user into the course
    odb.register_email(TEST_USER_EMAIL, TEST_USER_NAME, course_id=TEST_COURSE_ID)

    assert ddbo.get_user(TEST_USER_ID) == TEST_USER_DATA
    assert ddbo.get_user_email(TEST_USER_EMAIL) == TEST_USER_DATA

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
    api_key = odb.make_new_api_key( email = TEST_USER_EMAIL)
    assert odb.is_api_key(api_key)
    user = odb.validate_api_key(api_key)
    assert user == TEST_USER_DATA
    a2   = ddbo.get_api_key_dict(api_key)
    assert a2['enabled'] == 1
    assert a2['use_count'] == 1
    assert a2['created'] >= start_time
    assert a2['last_used_at'] >= a2['first_used_at'] >= a2['created']

    # Delete the API key
    ddbo.del_api_key(api_key)
    a3   = ddbo.get_api_key_dict(api_key)
    assert a3 is None

    # rename the user
    new_email = TEST_USER_EMAIL+"-new"
    ddbo.rename_user(user_id=TEST_USER_ID, new_email=new_email)
    u1 = ddbo.get_user(TEST_USER_ID)
    u2 = ddbo.get_user_email(new_email)
    print("u1=",json.dumps(u1,indent=4,default=str))
    print("u2=",json.dumps(u2,indent=4,default=str))
    assert u1==u2
    assert u1['email'] == TEST_USER_EMAIL+"-new"

    user_ids_before = odb.course_enrollments(course_id=TEST_COURSE_ID)

    # Remove the student from the course
    odb.unregister_from_course(user_id=TEST_USER_ID, course_id=TEST_COURSE_ID)

    # Verify student no longer present
    user_ids_after = odb.course_enrollments(course_id=TEST_COURSE_ID)

    assert len(user_ids_before) == len(user_ids_after)+1

    # Try to delete the user without deleting the user's movies
    with pytest.raises(RuntimeError,match=r'.* has 1 outstanding movie.*'):
        ddbo.delete_user(TEST_USER_ID)

    # Now delete the user and their movies
    ddbo.delete_user(TEST_USER_ID, purge_movies=True)
    with pytest.raises(InvalidUser_Id):
        ddbo.get_user(TEST_USER_ID)

    # Delete the user's course
    odb.delete_course(course_id=TEST_COURSE_ID)
