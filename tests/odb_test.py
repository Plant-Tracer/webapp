import uuid
import boto3
import os

import pytest

from app.odb import ODB

TEST_USER_ID = str(uuid.uuid4()) # uuid.uuid4() generates a UUID object, convert to string
TEST_COURSE_ID = str(uuid.uuid4()) # Generate ID for course
TEST_MOVIE_ID = str(uuid.uuid4()) # Generate ID for movie
TEST_USER_DATA = {
    'userId': TEST_USER_ID,
    'email': 'new.user@example.com',
    'username': 'newUser123',
    'firstName': 'New',
    'lastName': 'User',
    'primaryCourseId': TEST_COURSE_ID,
    # 'courseIds': ['course-abc-123', 'course-xyz-456'] # Example for multiple courses
}

TEST_COURSE_DATA = {
    'courseId': TEST_COURSE_ID,
    'name': 'Introduction to DynamoDB',
    'instructorId': TEST_USER_ID # Example: User is also an instructor
}

TEST_MOVIE_DATA = {
    'movieId': TEST_MOVIE_ID,
    'courseId': TEST_COURSE_ID,
    'userId': TEST_USER_ID,
    'title': 'My New Awesome Movie',
    'isPublished': False,
    'isDeleted': False,
    'description': 'A fantastic new movie project.'
}

def test_odb():
    odb = ODB(region_name=os.getenv('AWS_DEFAULT_REGION'),
             endpoint_url=os.getenv('DYNAMODB_ENDPOINT_URL'))
    odb.put_user(TEST_USER_DATA)
    u1 = odb.get_user(TEST_USER_ID)
    assert u1 == TEST_USER_DATA

    odb.put_movie(TEST_MOVIE_DATA)
    m1 = odb.get_movie(TEST_MOVIE_ID)
    assert m1 == TEST_MOVIE_DATA

    odb.put_course(TEST_COURSE_DATA)
    c1 = odb.get_course(TEST_COURSE_ID)
    assert c1 == TEST_COURSE_DATA
