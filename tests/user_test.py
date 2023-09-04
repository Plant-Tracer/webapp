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

TEST_USER_EMAIL  = 'simsong@gmail.com'           # from configure
TEST_ADMIN_EMAIL = 'simsong+admin@gmail.com'     # configuration

MOVIE_FILENAME = os.path.join(MYDIR, "data", "2019-07-31 plantmovie.mov")

@pytest.fixture
def new_course():
    course_key = str(uuid.uuid4())
    ct = db.create_course( course_key, course_key + "course name", MAX_ENROLLMENT )
    assert ct>0                 # returns course_id
    db.make_course_admin( TEST_ADMIN_EMAIL, course_key=course_key )
    yield course_key
    db.remove_course_admin( TEST_ADMIN_EMAIL, course_key=course_key )
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
    user_email = TEST_USER_EMAIL.replace('@','+'+str(uuid.uuid4())+'@')
    course_key = new_course
    user_id = db.register_email( user_email, course_key )
    assert user_id>0
    api_key = db.new_api_key( user_email )
    assert len(api_key)>8
    yield ( user_email, api_key)
    ct = db.delete_api_key(api_key)
    assert ct==1
    db.delete_user( user_email )

def test_new_user(new_user):
    (email, api_key) = new_user
    logging.info("email=%s api_key=%s", email, api_key)

@pytest.fixture
def new_movie(new_user):
    """Create a new movie_id and return it"""
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
        with pytest.raises(bottle.HTTPResponse):
            res = bottle_app.api_new_movie()


    # Try to uplaod the movie all at once
    with boddle(params = {"api_key":api_key,
                          "title": MOVIE_TITLE,
                          "description":"test movie description",
                          "movie_base64_data":movie_base64_data} ):
        res = bottle_app.api_new_movie()
    assert res['error']==False
    movie_id = res['movie_id']
    assert movie_id > 0
    yield (movie_id, MOVIE_TITLE, api_key)

    # Delete the movie we uploaded
    with boddle(params ={'api_key':api_key,
                         'movie_id':movie_id}):
        res = bottle_app.api_delete_movie()
    assert res['error']==False

    # And purge the movie that we have deleted
    db.purge_movie(movie_id);


def movie_list(api_key):
    """Return a list of the movies"""
    with boddle(params = {"api_key":api_key}):
        res = bottle_app.api_list_movies()
    assert res['error']==False
    return res['movies']

def get_movie( api_key, movie_id):
    """Used for testing. Just pull the specific movie"""
    movies = movie_list(api_key)
    try:
        return [movie for movie in movies if movie['id']==movie_id][0]
    except IndexError as e:
        user_id = bottle_app.validate_api_key( api_key )['user_id']
        logging.error("api_key=%s movie_id=%s user_id=",api_key,movie_id,user_id)
        logging.error("len(movies)=%s",len(movies))
        for movie in movies:
            logging.error("%s",str(movie))
        logging.error("Full database:")
        for movie in dbfile.DBMySQL.csfr( db.get_dbreader(), "select * from movies",(),asDicts=True):
            logging.error("%s",str(movie))
        raise


def test_movie_upload(new_movie):
    """Create a new user, upload the movie, delete the movie, and shut down"""
    (movie_id, movie_title, api_key) = new_movie

    # Did the movie appear in the list?
    movies = movie_list( api_key )
    assert len( [movie for movie in movies if movie['deleted']==0 and movie['published']==0 and movie['title']==movie_title] ) == 1


    # Make sure that we cannot delete the movie with a bad key
    with boddle(params ={'api_key':'invalid',
                         'movie_id':movie_id}):
        with pytest.raises(bottle.HTTPResponse):
            res = bottle_app.api_delete_movie()


def test_movie_update_metadata(new_movie):
    """try updating the metadata, and making sure some updates fail."""

    (movie_id, movie_title, api_key) = new_movie

    # Validate the old title
    assert get_movie( api_key, movie_id)['title'] == movie_title

    new_title = 'special new title ' + str(uuid.uuid4())
    with boddle(params = {'api_key':api_key,
                          'set_movie_id':movie_id,
                          'property':'title',
                          'value':new_title}):
        res = bottle_app.api_set_metadata()
    logging.error('res=%s',res)
    assert res['error']==False

    # Get the list of movies
    assert get_movie( api_key, movie_id)['title'] == new_title

    new_description = 'special new description ' + str(uuid.uuid4())
    with boddle(params = {'api_key':api_key,
                          'set_movie_id':movie_id,
                          'property':'description',
                          'value':new_description}):
        res = bottle_app.api_set_metadata()
    assert res['error']==False
    assert get_movie( api_key, movie_id)['description'] == new_description

    # Try to delete the movie
    with boddle(params = {'api_key':api_key,
                          'set_movie_id':movie_id,
                          'property':'deleted',
                          'value':1}):
        res = bottle_app.api_set_metadata()
    assert res['error']==False
    assert get_movie( api_key, movie_id)['deleted'] == 1

    # Undelete the movie
    with boddle(params = {'api_key':api_key,
                          'set_movie_id':movie_id,
                          'property':'deleted',
                          'value':0}):
        res = bottle_app.api_set_metadata()
    assert res['error']==False
    assert get_movie( api_key, movie_id)['deleted'] == 0

    # Try to publish the movie under the user's API key. This should not work
    assert get_movie( api_key, movie_id)['published'] == 0
    with boddle(params = {'api_key':api_key,
                          'set_movie_id':movie_id,
                          'property':'published',
                          'value':1}):
        res = bottle_app.api_set_metadata()
    assert res['error']==False
    assert get_movie( api_key, movie_id)['published'] == 0

    # Try to publish the movie with the course admin's API key. This should work
