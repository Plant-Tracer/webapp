import subprocess
import pytest
import sys
import os
import bottle
import logging
import json
import tempfile
import glob
import base64
import csv
from os.path import abspath, dirname

import numpy as np
import cv2

# https://bottlepy.org/docs/dev/recipes.html#unit-testing-bottle-applications

from boddle import boddle

sys.path.append(dirname(dirname(abspath(__file__))))

from paths import TEST_DATA_DIR
import lib.ctools.dbfile as dbfile
import blocktrack
import bottle_app
import copy
import db

from PIL import Image

# get the first MOV

# Get the fixtures from user_test
from user_test import new_user,new_course,API_KEY,MOVIE_ID,MOVIE_TITLE,USER_ID,DBWRITER,TEST_MOVIE_FILENAME
from movie_test import new_movie
from constants import MIME,Engines
import tracker


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
    assert isinstance(ret['tracked_movie_id'],int)
    tracked_movie_id = ret['tracked_movie_id']

    # Make sure that the tracked movie has its orig_movie set to movie_id
    new_movie_row = db.list_movies(user_id=0, movie_id=tracked_movie_id)
    assert new_movie_row[0]['orig_movie'] == movie_id

    # Download the trackpoints as as CSV and make sure it is formatted okay.
    # The trackpoints go with the original movie, not the tracked one.
    with boddle(params={'api_key': api_key,
                        'movie_id': movie_id}):
        ret = bottle_app.api_get_movie_trackpoints()
    lines = ret.splitlines()
    # Check that the header is set
    assert "track1 x" in lines[0]
    assert "track1 y" in lines[0]
    assert "track2 x" in lines[0]
    assert "track2 y" in lines[0]
    assert "track1 x" not in lines[2]

    sr = csv.DictReader(lines,delimiter=',')
    dictlines = [row for row in sr]
    # Make sure that the first line hasn't moved
    assert dictlines[0]['track1 x']==275
    assert dictlines[0]['track1 y']==215
    assert dictlines[0]['track2 x']==410
    assert dictlines[0]['track2 y']==175

    # Make sure that the secon line has moved
    assert dictlines[1]['track1 x']!=275
    assert dictlines[1]['track1 y']!=215

    assert len(lines) > 50

    # Purge the new movie
    db.purge_movie( movie_id=tracked_movie_id )
