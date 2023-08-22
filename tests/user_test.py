import sys
import os
import uuid
import logging
import pytest
import uuid
import base64

from os.path import abspath,dirname

sys.path.append( dirname(dirname(abspath(__file__))))

import bottle_app
from boddle import boddle

MYDIR = dirname(abspath(__file__))

MAX_ENROLLMENT = 10

USER_EMAIL = os.environ['TEST_USER_EMAIL'].replace('@','+'+str(uuid.uuid4())+'@')
MOVIE_FILENAME = os.path.join(MYDIR, "data", "2019-07-31 plantmovie.mov")

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
    api_key = bottle_app.new_api_key( USER_EMAIL )
    assert len(api_key)>8
    yield ( USER_EMAIL, api_key)
    ct = bottle_app.delete_api_key(api_key)
    assert ct==1
    bottle_app.delete_user( USER_EMAIL )

def test_new_user(new_user):
    (email, api_key) = new_user
    logging.info("email=%s api_key=%s", email, api_key)

def test_movie_upload(new_user):
    """Create a new user, upload the movie, delete the movie, and shut down"""
    (email, api_key) = new_user

    with open(MOVIE_FILENAME,"rb") as f:
        movie_base64_data = base64.b64encode(f.read())

   # Try to uplaod the movie with an invalid key
    with boddle(params = {"api_key":api_key+'invalid',
                          "title":"test movie title",
                          "description":"test movie description",
                          "movie_base64_data":movie_base64_data} ):
        bottle_app.expand_memfile_max()
        res = bottle_app.api_new_movie()
        assert res['error']==True


    # Try to uplaod the movie all at once
    with boddle(params = {"api_key":api_key,
                          "title":"test movie title",
                          "description":"test movie description",
                          "movie_base64_data":movie_base64_data} ):
        res = bottle_app.api_new_movie()
        assert res['error']==False

        movie_id = res['movie_id']
        assert movie_id > 0

    # Make sure that we cannot delete the movie with a bad key
    with boddle(params ={'api_key':'invalid',
                         'movie_id':movie_id}):
        res = bottle_app.api_delete_movie()
        assert res['error']==True

    # Delete the movie we uploaded
    with boddle(params ={'api_key':api_key,
                         'movie_id':movie_id}):
        res = bottle_app.api_delete_movie()
        assert res['error']==False
