"""
Test the various functions in the database involving movie creation.
"""

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
import json
from os.path import abspath, dirname

from boddle import boddle
import filetype

sys.path.append(dirname(dirname(abspath(__file__))))

from paths import TEST_DATA_DIR
from constants import C
import lib.ctools.dbfile as dbfile
import db
import bottle_app

from auth import get_dbreader,get_dbwriter

# Get the fixtures from user_test
from user_test import new_user,new_course,API_KEY,MOVIE_ID,MOVIE_TITLE,USER_ID,DBWRITER,TEST_MOVIE_FILENAME
from constants import MIME,Engines
import tracker

@pytest.fixture
def new_movie(new_user):
    """Create a new movie_id and return it.
    When we are finished with the movie, purge it and all of its child data.
    """
    cfg = copy.copy(new_user)

    api_key = cfg[API_KEY]
    api_key_invalid = api_key+"invalid"
    movie_title = f'test-movie title {str(uuid.uuid4())}'

    logging.debug("new_movie fixture: Opening %s",TEST_MOVIE_FILENAME)
    with open(TEST_MOVIE_FILENAME, "rb") as f:
        movie_data = f.read()
    assert len(movie_data) == os.path.getsize(TEST_MOVIE_FILENAME)
    assert len(movie_data) > 0

    # This generates an error, which is why it needs to be caught with pytest.raises():
    logging.debug("new_movie fixture: Try to uplaod the movie with an invalid key")
    with boddle(params={'api_key': api_key_invalid,
                        "title": movie_title,
                        "description": "test movie description",
                        "movie_base64_data": base64.b64encode(movie_data)}):
        bottle_app.expand_memfile_max()
        with pytest.raises(bottle.HTTPResponse):
            res = bottle_app.api_new_movie()

    # This generates an error --- movie too big
    movie_data_big = b"*" * (C.MAX_FILE_UPLOAD + 1)
    with boddle(params={'api_key': api_key_invalid,
                        "title": movie_title,
                        "description": "test movie description",
                        "movie_base64_data": base64.b64encode(movie_data_big)}):
        bottle_app.expand_memfile_max()
        with pytest.raises(bottle.HTTPResponse):
            res = bottle_app.api_new_movie()



    # This does not raise an error
    logging.debug("new_movie fixture: Create the movie in the database and upload the movie_data all at once")
    with boddle(params={'api_key': api_key,
                        "title": movie_title,
                        "description": "test movie description",
                        "movie_base64_data": base64.b64encode(movie_data)}):
        res = bottle_app.api_new_movie()
    assert res['error'] == False
    movie_id = res['movie_id']
    assert movie_id > 0

    cfg[MOVIE_ID] = movie_id
    cfg[MOVIE_TITLE] = movie_title

    logging.debug("new_movie fixture: movie_id=%s",movie_id)

    retrieved_movie_data = db.get_movie_data(movie_id=movie_id)
    assert len(movie_data) == len(retrieved_movie_data)
    assert movie_data == retrieved_movie_data
    logging.debug("new_movie fixture: yield %s",cfg)
    yield cfg

    logging.debug("new_movie fixture: Delete the movie we uploaded")
    with boddle(params={'api_key': api_key,
                        'movie_id': movie_id}):
        res = bottle_app.api_delete_movie()
    assert res['error'] == False

    logging.debug("new_movie fixture: Purge the movie that we have deleted")
    db.purge_movie(movie_id=movie_id)
    logging.debug("new_movie fixture: done")


def test_new_movie(new_movie):
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
            res = bottle_app.api_delete_movie()

    # Make sure that we can get data for the movie
    with boddle(params={'api_key': api_key,
                        'movie_id': movie_id}):
        res = bottle_app.api_get_movie_data()
    # res must be a movie. We should validate it.
    assert len(res)>0

    # Make sure that we can get the metadata
    with boddle(params={'api_key': api_key,
                        'movie_id': movie_id}):
        res = bottle_app.api_get_movie_metadata()
    assert res['error']==False
    assert res['metadata']['title'] == movie_title



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
        res = bottle_app.api_set_metadata()
    assert res['error'] == False

    # Get the list of movies
    assert get_movie(api_key, movie_id)['title'] == new_title

    new_description = 'special new description ' + str(uuid.uuid4())
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'description',
                        'value': new_description}):
        res = bottle_app.api_set_metadata()
    assert res['error'] == False
    assert get_movie(api_key, movie_id)['description'] == new_description

    # Try to delete the movie
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'deleted',
                        'value': 1}):
        res = bottle_app.api_set_metadata()
    assert res['error'] == False
    assert get_movie(api_key, movie_id)['deleted'] == 1

    # Undelete the movie
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'deleted',
                        'value': 0}):
        res = bottle_app.api_set_metadata()
    assert res['error'] == False
    assert get_movie(api_key, movie_id)['deleted'] == 0

    # Try to publish the movie under the user's API key. This should not work
    assert get_movie(api_key, movie_id)['published'] == 0
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'published',
                        'value': 1}):
        res = bottle_app.api_set_metadata()
    assert res['error'] == False
    assert get_movie(api_key, movie_id)['published'] == 0


def test_movie_extract(new_movie):
    """Try extracting individual movie frames"""
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key = cfg[API_KEY]
    user_id = cfg[USER_ID]

    movie_data = db.get_movie_data(movie_id = movie_id)
    assert filetype.guess(movie_data).mime==MIME.MP4

    # Grab three frames with the tracker and make sure they are different
    def get_movie_data_jpeg(frame_number):
        data =  tracker.extract_frame(movie_data=movie_data,frame_number=frame_number,fmt='jpeg')
        logging.debug("len(data)=%s",len(data))
        assert filetype.guess(data).mime==MIME.JPEG
        return data

    frame0 = get_movie_data_jpeg(0)
    frame1 = get_movie_data_jpeg(1)
    frame2 = get_movie_data_jpeg(2)

    assert frame0 != frame1 != frame2

    # Grab three frames with the API and see if they are different
    def get_jpeg_frame(number):
        with boddle(params={'api_key': api_key,
                            'movie_id': str(movie_id),
                            'frame_number': str(number),
                            'format':'jpeg' }):
            r =  bottle_app.api_get_frame()
            assert isinstance(r,dict) is False
            assert filetype.guess(r).mime==MIME.JPEG
            return r

    jpeg0 = get_jpeg_frame(0)
    jpeg1 = get_jpeg_frame(1)
    jpeg2 = get_jpeg_frame(2)
    assert jpeg0 != jpeg1 != jpeg2

    # Make sure it properly handles frames out-of-range
    with boddle(params={'api_key': api_key,
                        'movie_id': str(movie_id),
                        'frame_number': str(-1),
                        'format':'json' }):
        r =  bottle_app.api_get_frame()
    assert r['error']==True
    assert 'out of range' in r['message']

    with boddle(params={'api_key': api_key,
                        'movie_id': str(movie_id),
                        'frame_number': str(1_000_000),
                        'format':'json' }):
        r =  bottle_app.api_get_frame()
    assert r['error']==True
    assert 'out of range' in r['message']

    # Grab three frames with metadata
    def get_jpeg_json(frame_number):
        with boddle(params={'api_key': api_key,
                            'movie_id': str(movie_id),
                            'frame_number': str(frame_number),
                            'format':'json' }):
            ret =  bottle_app.api_get_frame()
            logging.debug("2. ret=%s",ret)
            logging.debug("2. movie_id=%s frame_number=%s ret[frame_id]=%s",movie_id,frame_number,ret['frame_id'])
            assert isinstance(ret,dict) is True
            return ret
    r0 = get_jpeg_json(0)
    r1 = get_jpeg_json(1)
    r2 = get_jpeg_json(2)
    assert r0['frame_id'] != r1['frame_id'] != r2['frame_id']

"""
test frame annotations ---
    # get the frame with the JSON interface, asking for annotations
    with boddle(params={'api_key': api_key,
                        'movie_id': str(movie_id),
                        'frame_number':1,
                        'format':'json',
                        'get_annotations':True}):
        ret = bottle_app.api_get_frame()
    annotations = ret['annotations']
    # analysis_stored is a list of dictionaries where each dictionary contains a JSON string called 'annotations'
    # turn the strings into dictionary objects and compare then with our original dictionaries to see if we can
    # effectively round-trip through multiple layers of parsers, unparsers, encoders and decoders
    logging.debug("annotations[0]=%s",annotations[0])
    logging.debug("annotations1=%s",annotations1)
    assert ret['annotations'][0]['annotations']==annotations1
    assert ret['annotations'][1]['annotations']==annotations2
    engine_id   = ret['annotations'][0]['engine_id']

    # See if we can get the frame by id without the annotations
    r2 = db.get_frame(frame_id=frame_id)
    assert r2['frame_id'] == frame_id
    assert magic.from_buffer(r2['frame_data'],mime=True)==MIME.JPEG
    assert 'annotations' not in r2

    # See if we can get the frame by id with the analysis
    r2 = db.get_frame(frame_id=frame_id, get_annotations=True)
    assert 'annotations' in r2

    # Validate the bottle interface

    # See if we can get the frame by id without the analysis
    r2 = db.get_frame(frame_id=frame_id,get_annotations=False)
    assert 'annotations' not in r2
    assert r2['frame_id'] == frame_id

    # get 1 frame with the JSON interface and test the result.
    with boddle(params={'api_key': api_key,
                        'movie_id': str(movie_id),
                        'frame_number': '1',
                        'format':'json' }):
        ret = bottle_app.api_get_frame()
    assert ret['data_url'].startswith('data:image/jpeg;base64,')
    assert base64.b64decode(ret['data_url'][23:])==jpeg1

    # Create a random engine and upload two analysis for it
    engine_name = "test-engine " + str(uuid.uuid4())[0:8]
    annotations1 = {'guid':str(uuid.uuid4()),
                 "key1": "value with 'single' quotes",
                 "key2": 'value with "double" quotes',
                 "key3": "value with 'single' and \"double\" quotes" }
    annotations2 = {'guid':str(uuid.uuid4()),
                 "key1": "value with 'single' quotes",
                 "key2": 'value with "double" quotes',
                 "key3": "value with 'single' and \"double\" quotes" }

    # Check for error if all three are none
    with pytest.raises(RuntimeError):
        db.put_frame_annotations(frame_id=frame_id, annotations=annotations1)

    # Check for error if engine_name is provided but engine_version is not
    with pytest.raises(RuntimeError):
        db.put_frame_annotations(frame_id=frame_id, engine_name=engine_name, annotations=annotations1)

    # Check for error if both engine_id and engine_name are provided
    with pytest.raises(RuntimeError):
        db.put_frame_annotations(frame_id=frame_id, engine_id=1, engine_name=engine_name, engine_version='1', annotations=annotations1)

    # Now test putting frame analysis
    db.put_frame_annotations(frame_id=frame_id,
                          engine_name=engine_name,
                          engine_version="1",
                          annotations=annotations1)

    # Now test with the Bottle API
    with boddle(params={'api_key': api_key,
                        'frame_id': str(frame_id),
                        'engine_name': engine_name,
                        'engine_version':'2',
                        'annotations':json.dumps(annotations2)}):
        bottle_app.api_put_frame_analysis()
"""

################################################################
## support functions
################################################################


def movie_list(api_key):
    """Return a list of the movies"""
    with boddle(params={'api_key': api_key}):
        res = bottle_app.api_list_movies()
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


def test_log_search_movie(new_movie):
    cfg        = copy.copy(new_movie)
    api_key    = cfg[API_KEY]
    movie_id   = cfg[MOVIE_ID]
    movie_title= cfg[MOVIE_TITLE]

    dbreader = get_dbreader()
    res = dbfile.DBMySQL.csfr(dbreader, "select user_id from movies where id=%s", (movie_id,))
    user_id = res[0][0]
    res = db.get_logs( user_id=user_id, movie_id = movie_id)
    logging.info("log entries for movie:")
    for r in res:
        logging.info("%s",r)
