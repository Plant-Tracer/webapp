import sys
import os
import uuid
import logging
import pytest
import uuid

from os.path import abspath,dirname

sys.path.append( dirname(dirname(abspath(__file__))))

import bottle_app

MAX_ENROLLMENT = 10

USER_EMAIL = os.environ['TEST_USER_EMAIL'].replace('@','+'+str(uuid.uuid4())+'@')

@pytest.fixture
def new_course():
    course_key = str(uuid.uuid4())
    ct = bottle_app.create_course( course_key, course_key + "course name", MAX_ENROLLMENT )
    assert ct>0                 # returns course_id
    yield course_key
    ct = bottle_app.delete_course(course_key)
    assert ct==1                # returns number of courses deleted

def test_new_course(new_course):
    course_key = new_course
    logging.info("Created course %s",course_key)


@pytest.fixture
def new_user(new_course):
    """Creates a new course and a new user and yields (USER_EMAIL, api_key)
    Then deletes them. The course gets deleted by the new_course fixture.
    """
    course_key = new_course
    user_id = bottle_app.register_email( USER_EMAIL, course_key )
    assert user_id>0
    api_key = bottle_app.new_apikey( USER_EMAIL )
    assert len(api_key)>8
    yield ( USER_EMAIL, api_key)
    ct = bottle_app.delete_apikey(api_key)
    assert ct==1
    bottle_app.delete_user( USER_EMAIL )

def test_new_user(new_user):
    (email, api_key) = new_user
    logging.info("email=%s api_key=%s", email, api_key)
