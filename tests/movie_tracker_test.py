"""
movie_tracker_test.py - test the api tracking
"""
import sys
import json
import tempfile
import csv
import math
from zipfile import ZipFile
import copy

import filetype


from app import odb
from app import odb_movie_data
from app.constants import MIME,E,C
from app.odb import API_KEY,MOVIE_ID
from app.odb_movie_data import read_object,create_new_movie_frame

# Fixtures are in conftest.py
from .conftest import logger

# Bogus labels for generic test
TEST_LABEL1 = 'test-label1'
TEST_LABEL2 = 'test-label2'
TEST_LABEL3 = 'test-label3'

def is_zipfile(buf):
    try:
        return filetype.guess(buf).mime==MIME.ZIP
    except AttributeError:
        logger.error("buf=%s",buf)
        raise


def test_track_point_annotations(client, new_movie):
    """See if we can save two trackpoints in the frame and get them back"""
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    api_key = cfg[API_KEY]

    tp0 = {'x':10,'y':11,'label':TEST_LABEL1}
    tp1 = {'x':20,'y':21,'label':TEST_LABEL2}
    tp2 = {'x':25,'y':25,'label':TEST_LABEL3}
    frame_urn = create_new_movie_frame(movie_id=movie_id, frame_number=0)
    logger.debug("frame_urn=%s",frame_urn)
    odb.put_frame_trackpoints(movie_id=movie_id, frame_number=0, trackpoints=[ tp0, tp1 ])

    # See if I can get it back
    tps = odb.get_movie_trackpoints(movie_id=movie_id, frame_start=0, frame_count=1)
    assert len(tps)==2
    logger.debug("tps[0]=%s",tps[0])
    logger.debug("tp0=%s",tp0)
    assert tps[0]['x'] == tp0['x']
    assert tps[0]['y'] == tp0['y']
    assert tps[0]['label'] == tp0['label']
    assert tps[0]['frame_number'] == 0

    assert tps[1]['x'] == tp1['x']
    assert tps[1]['y'] == tp1['y']
    assert tps[1]['label'] == tp1['label']
    assert tps[1]['frame_number'] == 0

    # Try the other interface; this time send two trackpoints through
    response = client.post('/api/put-frame-trackpoints',
                           data = {'api_key': api_key,
                                   'movie_id': movie_id,
                                   'frame_number':1,
                                   'trackpoints':json.dumps([tp0,tp1,tp2])})
    assert response.status_code == 200

    # Validate that the trackpoints were written into the database
    tps = odb.get_movie_trackpoints(movie_id=movie_id, frame_start=1, frame_count=1)
    assert len(tps)==3
    assert tps[0]['x'] == tp0['x']
    assert tps[0]['y'] == tp0['y']
    assert tps[0]['label'] == tp0['label']
    assert tps[0]['frame_number'] == 1

    assert tps[1]['x'] == tp1['x']
    assert tps[1]['y'] == tp1['y']
    assert tps[1]['label'] == tp1['label']
    assert tps[1]['frame_number'] == 1

    assert tps[2]['x'] == tp2['x']
    assert tps[2]['y'] == tp2['y']
    assert tps[2]['label'] == tp2['label']
    assert tps[2]['frame_number'] == 1


# pylint: disable=too-many-statements
def test_movie_tracking(client, new_movie):
    """
    Load up our favorite trackpoint ask the API to track a movie!
    Tests for:
    - all frames tracked
    - trackpoints near correct end location
    - zipfile created
    """
    cfg      = copy.copy(new_movie)
    movie_id    = cfg[MOVIE_ID]
    #movie_title = cfg[MOVIE_TITLE]
    api_key  = cfg[API_KEY]
    #user_id  = cfg[USER_ID]
    tpts     = [{"x":275,"y":215,"label":"track1"},{"x":410,"y":175,"label":"track2"}]

    # save the trackpoints
    response = client.post('/api/put-frame-trackpoints',
                           data = {'api_key': api_key,
                                   'movie_id': movie_id,
                                   'frame_number': '0',
                                   'trackpoints' : json.dumps(tpts)
                                   })
    assert response.status_code == 200
    ret = response.get_json()
    logger.debug("save trackpoints ret=%s",ret)
    assert ret['error'] is False

    # Now track with the tracking API.
    response = client.post('/api/track-movie-queue',
                           data = {'api_key': api_key,
                                   'movie_id': str(movie_id),
                                   'frame_start': '0' })
    assert response.status_code == 200
    ret = response.get_json()
    logger.debug("track movie ret=%s",ret)
    assert ret['error'] is False

    response = client.post('/api/get-movie-metadata',
                           data = {'api_key': api_key,
                                   'movie_id': str(movie_id),
                                   'get_all_if_tracking_completed': True})
    assert response.status_code == 200
    ret = response.get_json()
    logger.debug("/api/get-movie-metadata() = %s",ret)

    movie_metadata = ret['metadata']
    assert movie_metadata['movie_zipfile_urn'].startswith('s3')
    assert movie_metadata['movie_zipfile_url'].startswith('http') # might be https
    assert movie_metadata['last_frame_tracked'] == 53             # 0..53
    assert len(ret['frames']) == 54


    # check the metadata in the database
    dbmovie_metadata = odb.get_movie_metadata(movie_id=movie_id, get_last_frame_tracked=True)
    logger.debug('movie_metadata=%s',movie_metadata)
    assert dbmovie_metadata['status'] == C.TRACKING_COMPLETED
    assert dbmovie_metadata['last_frame_tracked'] == 53
    assert dbmovie_metadata['movie_zipfile_urn'].startswith('s3')
    assert 'movie_zipfile_url' not in dbmovie_metadata # don't put signed URLs in the database

    # Get the zipfile and make sure it is a zipfile
    zipdata = read_object(movie_metadata['movie_zipfile_urn'])
    assert is_zipfile(zipdata)

    # Download the trackpoints as a CSV and make sure it is formatted okay.
    # The trackpoints go with the original movie, not the tracked one.
    response = client.post('/api/get-movie-trackpoints',
                           data={'api_key': api_key,
                                 'movie_id': movie_id})
    assert response.status_code == 200
    lines = response.text.splitlines()

    # Verify a ZIP file with the individual frames was created
    zipfile_data = odb_movie_data.get_movie_data(movie_id=movie_id, zipfile=True)
    with tempfile.NamedTemporaryFile(suffix='.zip') as tf:
        tf.write(zipfile_data)
        tf.flush()
        with ZipFile(tf.name, 'r') as myzip:
            logger.info("names of files in zipfile: %s",myzip.namelist())
            frame_count = len(myzip.namelist())

    assert frame_count==54


    # Check that the CSV header is set
    fields = lines[0].split(",")
    logger.info("fields: %s",fields)
    assert fields==['frame_number','track1 x','track1 y','track2 x','track2 y']

    sr = csv.DictReader(lines,delimiter=',')
    dictlines = list(sr)
    # Make sure that the first line hasn't moved
    assert (dictlines[0]['track1 x']=='275') and (dictlines[0]['track1 y']=='215')
    assert (dictlines[0]['track2 x']=='410') and (dictlines[0]['track2 y']=='175')

    # This is where the 10th point ends up, more or less
    def close(a,b):
        return math.fabs(float(a)-float(b)) < 1.0

    assert close(dictlines[10]['track1 x'], 272.28845)
    assert close(dictlines[10]['track1 y'], 188.73012)
    assert close(dictlines[10]['track2 x'], 408.65558)
    assert close(dictlines[10]['track2 y'], 171.97594)

    # Make sure we got a lot back
    assert len(lines) > 50

    # Make sure that we got a line for every frame
    assert frame_count+1 == len(lines) # one line for the header

    # Check error conditions for getting incomplete metadata
    response = client.post('/api/get-movie-metadata',
                           data={'api_key': api_key,
                                 'movie_id': movie_id,
                                 'frame_start': 0})
    assert response.get_json() == E.FRAME_START_NO_FRAME_COUNT

    response = client.post('/api/get-movie-metadata',
                           data = {'api_key': api_key,
                                   'movie_id': movie_id,
                                   'frame_start': 0,
                                   'frame_count': 0})
    assert response.get_json() == E.FRAME_COUNT_GT_0

    # Get the movie metadata
    response = client.post('/api/get-movie-metadata',
                           data = {'api_key': api_key,
                                 'movie_id': movie_id,
                                 'frame_start': 0,
                                 'frame_count': 1000})
    ret = response.get_json()
    logger.debug("r10=%s",ret)
    print(json.dumps(ret,indent=4),file=sys.stderr)
    assert ret['error'] is False
    movie_id = ret['metadata']['movie_id']
    frame0 = ret['frames']['0']


    # See if we can find our starting data
    track1 = [tp for tp in frame0['markers'] if tp['label']=='track1'][0]
    assert track1['x']==275
    assert track1['y']==215
    assert track1['label']=='track1'

    track2 = [tp for tp in frame0['markers'] if tp['label']=='track2'][0]
    assert track2['x']==410
    assert track2['y']==175
    assert track2['label']=='track2'
