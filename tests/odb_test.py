import uuid
import boto3
import os
import time

import pytest

from app.odb import ODB

TEST_USER_ID = str(uuid.uuid4()) # uuid.uuid4() generates a UUID object, convert to string
TEST_USER_EMAIL = 'new.user@example.com'
TEST_COURSE_ID = str(uuid.uuid4()) # Generate ID for course
TEST_MOVIE_ID = str(uuid.uuid4()) # Generate ID for movie
TEST_USER_DATA = {
    'userId': TEST_USER_ID,
    'email': TEST_USER_EMAIL,
    'name': 'Firstname Lastname',
    'created': int(time.time()),
    'enabled': 1,
    'demo': 0,
    'admin': [],
    'courses': [TEST_COURSE_ID],
    'primaryCourseId': TEST_COURSE_ID,
}

TEST_COURSE_DATA = {
    'courseId': TEST_COURSE_ID,
    'name': 'Introduction to DynamoDB'
}

TEST_MOVIE_DATA = {
    'movieId': TEST_MOVIE_ID,
    'courseId': TEST_COURSE_ID,
    'userId': TEST_USER_ID,
    'title': 'My New Awesome Movie',
    'isPublished': 0,
    'isDeleted': 0,
    'description': 'A fantastic new movie project.'
}

def test_odb():
    odb = ODB(region_name=os.getenv('AWS_DEFAULT_REGION'),
             endpoint_url=os.getenv('DYNAMODB_ENDPOINT_URL'))
    odb.put_user(TEST_USER_DATA)
    u1 = odb.get_user(TEST_USER_ID)
    assert u1 == TEST_USER_DATA

    u2 = odb.get_user(None, email=TEST_USER_EMAIL)
    assert u2 == TEST_USER_DATA


    odb.put_movie(TEST_MOVIE_DATA)
    m1 = odb.get_movie(TEST_MOVIE_ID)
    assert m1 == TEST_MOVIE_DATA

    odb.put_course(TEST_COURSE_DATA)
    c1 = odb.get_course(TEST_COURSE_ID)
    assert c1 == TEST_COURSE_DATA
