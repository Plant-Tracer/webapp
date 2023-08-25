import sys
import os
import uuid
import logging
import pytest
import uuid
import base64

from os.path import abspath,dirname

import bottle
sys.path.append( dirname(dirname(abspath(__file__))))

import bottle_app
import db
from boddle import boddle

MYDIR = dirname(abspath(__file__))

MAX_ENROLLMENT = 10

USER_EMAIL = os.environ['TEST_USER_EMAIL'].replace('@','+'+str(uuid.uuid4())+'@')
MOVIE_FILENAME = os.path.join(MYDIR, "data", "2019-07-31 plantmovie.mov")

@pytest.fixture
def new_course():
    course_key = str(uuid.uuid4())
    ct = db.create_course( course_key, course_key + "course name", MAX_ENROLLMENT )
    assert ct>0                 # returns course_id
    yield course_key
    ct = db.delete_course(course_key)
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
    user_id = db.register_email( USER_EMAIL, course_key )
    assert user_id>0
    api_key = db.new_api_key( USER_EMAIL )
    assert len(api_key)>8
    yield ( USER_EMAIL, api_key)
    ct = db.delete_api_key(api_key)
    assert ct==1
    db.delete_user( USER_EMAIL )

def test_new_user(new_user):
    (email, api_key) = new_user
    logging.info("email=%s api_key=%s", email, api_key)

def test_movie_upload(new_user):
    """Create a new user, upload the movie, delete the movie, and shut down"""
    (email, api_key) = new_user

    MOVIE_TITLE = 'test movie title ' + str(uuid.uuid4())

    with open(MOVIE_FILENAME,"rb") as f:
        movie_base64_data = base64.b64encode(f.read())

   # Try to uplaod the movie with an invalid key
    with boddle(params = {"api_key":api_key+'invalid',
                          "title": MOVIE_TITLE,
                          "description":"test movie description",
                          "movie_base64_data":movie_base64_data} ):
        bottle_app.expand_memfile_max()
        try:
            res = bottle_app.api_new_movie()
            assert res['error']==True
        except bottle.HTTPResponse as e:
            pass


    # Try to uplaod the movie all at once
    with boddle(params = {"api_key":api_key,
                          "title": MOVIE_TITLE,
                          "description":"test movie description",
                          "movie_base64_data":movie_base64_data} ):
        res = bottle_app.api_new_movie()
    assert res['error']==False
    movie_id = res['movie_id']
    assert movie_id > 0

    # Did the movie appear in the list?
    with boddle(params = {"api_key":api_key}):
        res = bottle_app.api_list_movies()
    assert res['error']==False
    print("res:",res)
    movies = res['movies']
    assert len( [movie for movie in movies if movie['deleted']==0 and movie['published']==0 and movie['title']==MOVIE_TITLE] ) == 1


    # Make sure that we cannot delete the movie with a bad key
    with boddle(params ={'api_key':'invalid',
                         'movie_id':movie_id}):
        try:
            res = bottle_app.api_delete_movie()
            assert res['error']==True
        except bottle.HTTPResponse as e:
            pass

    # Delete the movie we uploaded
    with boddle(params ={'api_key':api_key,
                         'movie_id':movie_id}):
        res = bottle_app.api_delete_movie()
    assert res['error']==False

    # And purge the movie that we have deleted
    db.purge_movie(movie_id);
