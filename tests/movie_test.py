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
import magic
import json
from os.path import abspath, dirname

from boddle import boddle

sys.path.append(dirname(dirname(abspath(__file__))))

from paths import TEST_DATA_DIR
import lib.ctools.dbfile as dbfile
import db
import bottle_app

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

    # Make sure that we can get data base the movie
    with boddle(params={'api_key': api_key,
                        'movie_id': movie_id}):
        res = bottle_app.api_get_movie_data()
    # res must be a movie
    assert len(res)>0

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


TEST_LABEL1 = 'test-label1'
TEST_LABEL2 = 'test-label2'
TEST_LABEL3 = 'test-label3'
def test_movie_extract(new_movie):
    """Try extracting individual movie frames"""
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key = cfg[API_KEY]
    user_id = cfg[USER_ID]

    movie_data = db.get_movie_data(movie_id = movie_id)
    frame0 = tracker.extract_frame(movie_data = movie_data, frame_number=0, fmt='jpeg')
    frame1 = tracker.extract_frame(movie_data = movie_data, frame_number=1, fmt='jpeg')
    frame2 = tracker.extract_frame(movie_data = movie_data, frame_number=2, fmt='jpeg')

    assert frame0 is not None
    assert frame1 is not None
    assert frame2 is not None
    assert frame0 != frame1
    assert frame1 != frame2
    assert magic.from_buffer(frame0,mime=True)== MIME.JPEG
    assert magic.from_buffer(frame1,mime=True)== MIME.JPEG
    assert magic.from_buffer(frame2,mime=True)== MIME.JPEG

    # Grab three frames and see if they are different
    def get_jpeg_frame(number):
        with boddle(params={'api_key': api_key,
                            'movie_id': str(movie_id),
                            'frame_number': str(number),
                            'format':'jpeg' }):
            return bottle_app.api_get_frame()

    jpeg0 = get_jpeg_frame(0)
    assert jpeg0 is not None
    jpeg1 = get_jpeg_frame(1)
    assert jpeg1 is not None
    jpeg2 = get_jpeg_frame(2)
    assert jpeg2 is not None
    assert jpeg0 != jpeg1
    assert jpeg1 != jpeg2

    assert magic.from_buffer(jpeg0,mime=True)== MIME.JPEG
    assert magic.from_buffer(jpeg1,mime=True)== MIME.JPEG
    assert magic.from_buffer(jpeg2,mime=True)== MIME.JPEG


def test_track_point_annotations(new_movie):
    """See if we can save two trackpoints in the frame and get them back"""
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key = cfg[API_KEY]
    user_id = cfg[USER_ID]

    tp0 = {'x':10,'y':11,'label':TEST_LABEL1}
    tp1 = {'x':20,'y':21,'label':TEST_LABEL2}
    tp2 = {'x':25,'y':25,'label':TEST_LABEL3}
    frame_id = db.create_new_frame(movie_id=movie_id, frame_number=0)
    db.put_frame_trackpoints(frame_id=frame_id, trackpoints=[ tp0, tp1 ])

    # See if I can get it back
    tps = db.get_frame_trackpoints(frame_id=frame_id)
    assert len(tps)==2
    logging.debug("tps[0]=%s",tps[0])
    logging.debug("tp0=%s",tp0)
    assert tps[0]['x'] == tp0['x']
    assert tps[0]['y'] == tp0['y']
    assert tps[0]['label'] == tp0['label']
    assert tps[0]['frame_id'] == frame_id

    assert tps[1]['x'] == tp1['x']
    assert tps[1]['y'] == tp1['y']
    assert tps[1]['label'] == tp1['label']
    assert tps[1]['frame_id'] == frame_id


    # Try the other interface; this time send two trackpoints through
    engine_name = 'CV2';
    engine_version = '2';
    with boddle(params={'api_key': api_key,
                        'frame_id': str(frame_id),
                        'engine_name': engine_name,
                        'engine_version':engine_version,
                        'trackpoints':json.dumps([tp0,tp1,tp2])}):
        bottle_app.api_put_frame_analysis()
    # See if I can get it back
    tps = db.get_frame_trackpoints(frame_id=frame_id)
    assert len(tps)==3
    assert tps[0]['x'] == tp0['x']
    assert tps[0]['y'] == tp0['y']
    assert tps[0]['label'] == tp0['label']
    assert tps[0]['frame_id'] == frame_id

    assert tps[1]['x'] == tp1['x']
    assert tps[1]['y'] == tp1['y']
    assert tps[1]['label'] == tp1['label']
    assert tps[1]['frame_id'] == frame_id

    assert tps[2]['x'] == tp2['x']
    assert tps[2]['y'] == tp2['y']
    assert tps[2]['label'] == tp2['label']
    assert tps[2]['frame_id'] == frame_id


def test_movie_tracking(new_movie):
    """
    Load up our favorite trackpoint ask the API to track a movie!
    """
    cfg      = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key  = cfg[API_KEY]
    user_id  = cfg[USER_ID]
    tpts     = [{"x":275,"y":215,"label":"track1"},{"x":410,"y":175,"label":"track2"}]

    # get frame_id with the api_new_frame
    with boddle(params={'api_key': api_key,
                        'movie_id': str(movie_id),
                        'frame_number': '0'}):
        ret = bottle_app.api_new_frame()
    logging.debug("new frame ret=%s",ret)
    assert ret['error']==False
    frame_id = int(ret['frame_id'])

    # save the trackpoints
    with boddle(params={'api_key': api_key,
                        'frame_id': str(frame_id),
                        'trackpoints' : json.dumps(tpts),
                        'frame_number': '0'}):
        ret = bottle_app.api_put_frame_analysis()
    logging.debug("save trackpoints ret=%s",ret)
    assert ret['error']==False

    # Now track with CV2
    with boddle(params={'api_key': api_key,
                        'movie_id': str(movie_id),
                        'frame_start': '0',
                        'engine_name':Engines.CV2,
                        'engine_version':0 }):
        ret = bottle_app.api_track_movie()
    logging.debug("track movie ret=%s",ret)
    assert ret['error']==False
    # Extract the trackpoints
    output_trackpoints = ret['output_trackpoints']
    new_movie_id       = ret['new_movie_id']
    assert len(output_trackpoints)>90

    # Download the trackpoints as as CSV
    with boddle(params={'api_key': api_key,
                        'movie_id': new_movie_id}):
        ret = bottle_app.api_download_movie_trackpoints()
    lines = ret.split("\n")
    assert "track1 x" in lines[0]
    assert "track1 y" in lines[0]
    assert "track2 x" in lines[0]
    assert "track2 y" in lines[0]
    assert "track1 x" not in lines[2]
    assert len(lines) > 50

    # Purge the new movie
    db.purge_movie( movie_id=new_movie_id )




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
    dbreader = db.get_dbreader()
    logging.error("Full database: (dbreader: %s)", dbreader)
    for movie in dbfile.DBMySQL.csfr(dbreader, "select * from movies", (), asDicts=True):
        logging.error("%s", str(movie))
    raise RuntimeError(f"No movie has movie_id {movie_id}")


def test_log_search_movie(new_movie):
    cfg        = copy.copy(new_movie)
    api_key    = cfg[API_KEY]
    movie_id   = cfg[MOVIE_ID]
    movie_title= cfg[MOVIE_TITLE]

    dbreader = db.get_dbreader()
    res = dbfile.DBMySQL.csfr(dbreader, "select user_id from movies where id=%s", (movie_id,))
    user_id = res[0][0]
    res = db.get_logs( user_id=user_id, movie_id = movie_id)
    logging.info("log entries for movie:")
    for r in res:
        logging.info("%s",r)
