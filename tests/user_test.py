"""
Test the various functions in the database involving user creation.
"""

from boddle import boddle
import sys
import os
import uuid
import logging
import pytest
import uuid
import base64
import time
import bottle
import copy
import hashlib
from os.path import abspath, dirname

sys.path.append(dirname(dirname(abspath(__file__))))

from auth import get_dbreader,get_dbwriter
import db
import dbmaint
import bottle_api
import bottle_app
import ctools.dbfile as dbfile
from paths import TEST_DIR

TEST_USER_EMAIL = 'simsong@gmail.com'           # from configure
TEST_USER_NAME = 'Test User Name'
TEST_ADMIN_EMAIL = 'simsong+admin@gmail.com'     # configuration
TEST_DEMO_EMAIL  = 'demo+admin@gmail.com'        # completely bogus
TEST_ADMIN_NAME = 'Test User Name'

# keys for scaffolding dictionary
ADMIN_EMAIL = 'admin_email'
DEMO_EMAIL = 'demo_mail'
ADMIN_ID = 'admin_id'
API_KEY  = 'api_key'
COURSE_KEY = 'course_key'
COURSE_NAME = 'course_name'
USER_EMAIL = 'user_email'
USER_ID    = 'user_id'
MOVIE_ID = 'movie_id'
MOVIE_TITLE = 'movie_title'
ENGINE_ID = 'engine_id'
DBREADER = 'dbreader'
DBWRITER = 'dbwriter'
TEST_MOVIE_FILENAME = os.path.join(TEST_DIR, "data", "2019-07-31 plantmovie.mov")

################################################################

@pytest.fixture
def new_course():
    """Fixture to create a new course and then delete it.
    New course creates a new course admin and a new user for it"""

    course_key = 'test-'+str(uuid.uuid4())[0:32]
    admin_email = TEST_ADMIN_EMAIL.replace('@', '+test-'+str(uuid.uuid4())[0:4]+'@')
    demo_email  = TEST_DEMO_EMAIL.replace('@', '+test-'+str(uuid.uuid4())[0:4]+'@')
    course_name = f"test-{course_key} course name"

    admin_id = dbmaint.create_course(course_key = course_key,
                                     admin_email = admin_email,
                                     admin_name = 'Dr. Admin',
                                     course_name = course_name,
                                     demo_email = demo_email)

    yield {COURSE_KEY:course_key,
           COURSE_NAME:course_name,
           ADMIN_EMAIL:admin_email,
           ADMIN_ID:admin_id,
           DEMO_EMAIL:demo_email,
           DBREADER:get_dbreader(),
           DBWRITER:get_dbwriter() }

    db.remove_course_admin(email=admin_email, course_key=course_key)
    db.delete_user(email=admin_email, purge_movies=True)
    db.delete_user(email=demo_email, purge_movies=True)
    ct = db.delete_course(course_key=course_key)
    assert ct == 1                # returns number of courses deleted

@pytest.fixture
def new_user(new_course):
    """Creates a new course and a new user and yields (USER_EMAIL, api_key)
    Then deletes them. The course gets deleted by the new_course fixture.
    """
    cfg = copy.copy(new_course)

    user_email = TEST_USER_EMAIL.replace('@', '+test-'+str(uuid.uuid4())[0:6]+'@')
    user_id = db.register_email(email=user_email,
                                course_key=cfg[COURSE_KEY],
                                name=TEST_USER_NAME)['user_id']
    logging.info("generated user_email=%s user_id=%s",user_email, user_id)

    api_key = db.make_new_api_key(email=user_email)
    assert len(api_key) > 8

    cfg[API_KEY] = api_key
    cfg[USER_EMAIL] = user_email
    cfg[USER_ID] = user_id

    yield cfg
    ct = db.delete_api_key(api_key)
    assert ct == 1
    db.delete_user(email=user_email)

@pytest.fixture
def api_key(new_user):
    """Simple fixture that just returns a valid api_key"""
    yield new_user[API_KEY]

@pytest.fixture
def new_movie(new_user):
    """Create a new movie_id and return it"""
    cfg = copy.copy(new_user)

    api_key = cfg[API_KEY]
    api_key_invalid = api_key+"invalid"

    movie_title = 'test movie title ' + str(uuid.uuid4())

    with open(TEST_MOVIE_FILENAME, "rb") as f:
        movie_base64_data = base64.b64encode(f.read())

   # Try to uplaod the movie with an invalid key
    with boddle(params={"api_key": api_key_invalid,
                        "title": movie_title,
                        "description": "test movie description",
                        "movie_base64_data": movie_base64_data}):
        bottle_api.expand_memfile_max()
        with pytest.raises(bottle.HTTPResponse):
            res = bottle_api.api_new_movie()

    # Try to uplaod the movie all at once
    with boddle(params={"api_key": api_key,
                        "title": movie_title,
                        "description": "test movie description",
                        "movie_base64_data": movie_base64_data}):
        res = bottle_api.api_new_movie()
    assert res['error'] == False
    movie_id = res['movie_id']
    assert movie_id > 0

    cfg[MOVIE_ID] = movie_id
    cfg[MOVIE_TITLE] = movie_title

    yield cfg

    # Delete the movie we uploaded
    with boddle(params={'api_key': api_key,
                        'movie_id': movie_id}):
        res = bottle_api.api_delete_movie()
    assert res['error'] == False

    # And purge the movie that we have deleted
    db.purge_movie(movie_id=movie_id)

@pytest.fixture
def new_engine(new_movie):
    cfg = copy.copy(new_movie)

    engine_name = 'pytest-engine'
    engine_version = 'VTest'
    engine_id = db.get_analysis_engine_id(engine_name=engine_name, engine_version=engine_version)
    cfg[ENGINE_ID] = engine_id
    yield cfg
    db.purge_engine(engine_id=engine_id)

################################################################
## fixture tests
################################################################

def test_new_course(new_course):
    cfg = copy.copy(new_course)
    course_key = cfg[COURSE_KEY]
    admin_email = cfg[ADMIN_EMAIL]
    demo_email  = cfg[DEMO_EMAIL]
    logging.info("Created course %s", course_key)

    # Check the demo user got created
    res = db.list_demo_users()
    logging.debug("len(res)=%s",len(res))
    for (ct,r) in enumerate(res):
        logging.debug("%s: %s",ct,r)
    assert len(res)>=1
    assert len([r for r in res if r['email']==demo_email and r['api_key'] is not None])>0

def test_new_user(new_user):
    cfg = copy.copy(new_user)
    user_email = cfg[USER_EMAIL]
    api_key = cfg[API_KEY]
    logging.info("user_email=%s api_key=%s", user_email, api_key)

    # Try looking up the user
    ret1 = db.lookup_user(email=user_email)
    ret2 = db.lookup_user(user_id=ret1['user_id'], get_admin=True)
    ret3 = db.lookup_user(user_id=ret1['user_id'], get_courses=True)

    assert 'admin' in ret2
    assert 'courses' in ret3

def test_movie_upload(new_movie):
    """Create a new user, upload the movie, delete the movie, and shut down"""
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key = cfg[API_KEY]

    # Did the movie appear in the list?
    movies = movie_list(api_key)
    assert len([movie for movie in movies if movie['deleted'] ==
               0 and movie['published'] == 0 and movie['title'] == movie_title]) == 1

    # Make sure that we cannot delete the movie with a bad key
    with boddle(params={'api_key': 'invalid',
                        'movie_id': movie_id}):
        with pytest.raises(bottle.HTTPResponse):
            res = bottle_api.api_delete_movie()


def test_movie_update_metadata(new_movie):
    """try updating the metadata, and making sure some updates fail."""
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key = cfg[API_KEY]

    # Validate the old title
    assert get_movie(api_key, movie_id)['title'] == movie_title

    new_title = 'special new title ' + str(uuid.uuid4())
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'title',
                        'value': new_title}):
        res = bottle_api.api_set_metadata()
    assert res['error'] == False

    # Get the list of movies
    assert get_movie(api_key, movie_id)['title'] == new_title

    new_description = 'special new description ' + str(uuid.uuid4())
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'description',
                        'value': new_description}):
        res = bottle_api.api_set_metadata()
    assert res['error'] == False
    assert get_movie(api_key, movie_id)['description'] == new_description

    # Try to delete the movie
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'deleted',
                        'value': 1}):
        res = bottle_api.api_set_metadata()
    assert res['error'] == False
    assert get_movie(api_key, movie_id)['deleted'] == 1

    # Undelete the movie
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'deleted',
                        'value': 0}):
        res = bottle_api.api_set_metadata()
    assert res['error'] == False
    assert get_movie(api_key, movie_id)['deleted'] == 0

    # Try to publish the movie under the user's API key. This should not work
    assert get_movie(api_key, movie_id)['published'] == 0
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'published',
                        'value': 1}):
        res = bottle_api.api_set_metadata()
    assert res['error'] == False
    assert get_movie(api_key, movie_id)['published'] == 0

    # Try to publish the movie with the course admin's API key. This should work

################################################################
## support functions
################################################################


def movie_list(api_key):
    """Return a list of the movies"""
    with boddle(params={"api_key": api_key}):
        res = bottle_api.api_list_movies()
    assert res['error'] == False
    return res['movies']

def get_movie(api_key, movie_id):
    """Used for testing. Just pull the specific movie"""
    movies = movie_list(api_key)
    for movie in movies:
        return movie

    user_id = db.validate_api_key(api_key)['user_id']
    logging.error("api_key=%s movie_id=%s user_id=%s",
                  api_key, movie_id, user_id)
    logging.error("len(movies)=%s", len(movies))
    for movie in movies:
        logging.error("%s", str(movie))
    dbreader = get_dbreader()
    logging.error("Full database: (dbreader: %s)", dbreader)
    for movie in dbfile.DBMySQL.csfr(dbreader, "select * from movies", (), asDicts=True):
        logging.error("%s", str(movie))
    raise RuntimeError(f"No movie has movie_id {movie_id}")

def test_new_movie_analysis(new_engine):
    cfg = copy.copy(new_engine)
    movie_id = cfg[MOVIE_ID]
    engine_id = cfg[ENGINE_ID]

    annotations='{"key": "aKey", "value": "aValue" }'

    #create movie_analysis
    movie_analysis_id = db.create_new_movie_analysis(movie_id=movie_id,
                                 engine_id=engine_id,
                                 annotations=annotations
                                 )['movie_analysis_id']
    #verify movie_analysis exists
    #TODO

    # delete the created movie_analysis
    db.delete_movie_analysis(movie_analysis_id=movie_analysis_id)

def test_get_logs(new_user):
    """Incrementally test each part of the get_logs functions. We don't really care what the returns are"""
    dbreader = get_dbreader()
    for security in [False,True]:
        logging.info("security=%s",security)
        db.get_logs( user_id=0 , security=security)
        db.get_logs( user_id=0, start_time = 0 , security=security)
        db.get_logs( user_id=0, end_time = 0 , security=security)
        db.get_logs( user_id=0, course_key = 0 , security=security)
        db.get_logs( user_id=0, movie_id = 0, security=security)
        db.get_logs( user_id=0, log_user_id = 0, security=security)
        db.get_logs( user_id=0, ipaddr = "", security=security)

    api_key = new_user[API_KEY]
    user_id   = new_user['user_id']
    with boddle(params={'api_key': api_key, 'user_id':user_id}):
        res = bottle_api.api_get_logs()

    # Turns out that there are no logs with this user, since the scaffolding calls register_email
    # for the new_user with a NULL user_id....

def test_course_list(new_user):
    cfg        = copy.copy(new_user)
    user_email = cfg[USER_EMAIL]
    api_key    = cfg[API_KEY]

    user_dict = db.validate_api_key(api_key)
    user_id   = user_dict['user_id']
    primary_course_id = user_dict['primary_course_id']

    recs1 = db.list_users(user_id=user_id)
    users1 = recs1['users']

    matches = [user for user in users1 if user['user_id']==user_id]
    assert(len(matches)>0)

    # Make sure that there is an admin in the course who is not the user
    recs2 = db.list_admins()
    matches = [rec for rec in recs2 if rec['course_id']==primary_course_id and rec['user_id']!=user_id]
    assert len(matches)==1

    # Make sure that the endpoint works
    with boddle(params={'api_key': api_key}):
        res = bottle_api.api_list_users()
    assert res['error'] is False
    users2 = res['users']
    # There is the user and the admin; there may also be a demo user
    assert len(users2) in [2,3]
    assert users1[0]['name'] == users2[0]['name']
    assert users1[0]['email'] == users2[0]['email']


def test_log_search_user(new_user):
    """Currently we just run logfile queries and count the number of results."""
    cfg        = copy.copy(new_user)
    user_email = cfg[USER_EMAIL]
    api_key    = cfg[API_KEY]

    user_id  = db.validate_api_key(api_key)['user_id']
    dbreader = get_dbreader()

    ret = db.get_logs( user_id=user_id )
    logging.info("search for user_email=%s user_id=%s returns %s logs",user_email,user_id, len(ret))

    assert len(ret) > 0
    assert len(db.get_logs( user_id=user_id, start_time = 10)) > 0
    assert len(db.get_logs( user_id=user_id, end_time = time.time())) > 0

    # Make sure that restricting the time to something that happened more than a day ago fails,
    # because we just created this user.
    assert len(db.get_logs( user_id=user_id, end_time = time.time()-24*60*60)) ==0

    # Find the course that this user is in
    res = dbfile.DBMySQL.csfr(dbreader, "select primary_course_id from users where id=%s", (user_id,))
    assert(len(res)==1)
    course_id = res[0][0]

    res = dbfile.DBMySQL.csfr(dbreader, "select course_key from courses where id=%s", (course_id,))
    assert(len(res)==1)
    course_key = res[0][0]

    assert(len(db.get_logs( user_id=user_id, course_id = course_id)) > 0)
    assert(len(db.get_logs( user_id=user_id, course_key = course_key)) > 0)

    # Test to make sure that the course admin gets access to this user
    admin_id = dbfile.DBMySQL.csfr(dbreader,
                                   "SELECT user_id FROM admins WHERE course_id=%s LIMIT 1",
                                   (course_id,))[0]
    assert(len(db.get_logs( user_id=admin_id, log_user_id=user_id, course_id = course_id)) > 0)
    assert(len(db.get_logs( user_id=admin_id, log_user_id=user_id, course_key = course_key)) > 0)

    # We should have nothing with this IP address
    assert(len(db.get_logs( user_id=user_id, ipaddr="0.0.0.0"))==0)
