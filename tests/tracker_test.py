"""
tracker_test.py - test the tracker.py module.
"""


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
import math
from os.path import abspath, dirname

import numpy as np
import cv2

# https://bottlepy.org/docs/dev/recipes.html#unit-testing-bottle-applications

from boddle import boddle

sys.path.append(dirname(dirname(abspath(__file__))))

import lib.ctools.dbfile as dbfile
import bottle_api
import bottle_app
import copy
import db

from PIL import Image

# get the first MOV

# Get the fixtures from user_test
from user_test import new_user,new_course,API_KEY,MOVIE_ID,MOVIE_TITLE,USER_ID,DBWRITER,TEST_PLANTMOVIE_PATH,TEST_CIRCUMNUTATION_PATH,TEST_PLANTMOVIE_ROTATED_PATH
from movie_test import new_movie
from constants import MIME
import tracker

# Actual labels for the circumnutation movie
TEST_MOVIE_START_TRACKPOINTS = [{'frame_number':0,'x':140,'y':82,'label':'apex'},
                                {'frame_number':0,'x':240,'y':96,'label':'ruler 0 mm'},
                                {'frame_number':0,'x':242,'y':135,'label':'ruler 20 mm'}]

TEST_MOVIE_END_TRACKPOINTS = [{'frame_number':295,'x':58,'y':75,'label':'apex'},
                              {'frame_number':295,'x':240,'y':96,'label':'ruler 0 mm'},
                              {'frame_number':295,'x':242,'y':135,'label':'ruler 20 mm'}]

def test_cleanup_mp4():
    with pytest.raises(FileNotFoundError):
        tracker.cleanup_mp4(infile='no-such-file',outfile='no-such-file')

def test_track_movie():
    """End-to-end test of the track_movie function call."""
    input_trackpoints = TEST_MOVIE_START_TRACKPOINTS

    # pylint: disable=unused-argument
    trackpoints = []
    def callback(*,frame_number,frame_data,frame_trackpoints):
        trackpoints.extend(frame_trackpoints)

    # Get the new trackpoints
    infile = TEST_CIRCUMNUTATION_PATH
    tracker.track_movie(moviefile_input=infile,
                        input_trackpoints=input_trackpoints,
                        callback = callback )
    # Now render the movie
    with tempfile.NamedTemporaryFile(suffix='.mp4') as tf:
        tracker.render_tracked_movie( moviefile_input= infile, moviefile_output=tf.name,
                                      movie_trackpoints=trackpoints)
        assert os.path.getsize(tf.name)>100

    #for tp in trackpoints:
    #    logging.info("tp=%s",tp)

    # Check the trackpoints
    assert len(trackpoints) == 3 * 296
    EPSILON = 1.0
    def close(tp1,tp2):
        logging.debug("tp1=%s tp2=%s",tp1,tp2)
        assert tp1['frame_number']==tp2['frame_number']
        assert tp1['label']==tp2['label']
        assert math.fabs(tp1['x']-tp2['x']) <= EPSILON
        assert math.fabs(tp1['y']-tp2['y']) <= EPSILON
        return True

    # Below we assume that order is preserved (or at least sorted by frame number and then label)
    assert close(trackpoints[0], TEST_MOVIE_START_TRACKPOINTS[0])
    assert close(trackpoints[1], TEST_MOVIE_START_TRACKPOINTS[1])
    assert close(trackpoints[2], TEST_MOVIE_START_TRACKPOINTS[2])

    assert close(trackpoints[-1], TEST_MOVIE_END_TRACKPOINTS[-1])
    assert close(trackpoints[-2], TEST_MOVIE_END_TRACKPOINTS[-2])
    assert close(trackpoints[-3], TEST_MOVIE_END_TRACKPOINTS[-3])

def test_movie_rotate():
    with tempfile.NamedTemporaryFile(suffix='.mp4') as tf:
        tracker.rotate_movie(TEST_PLANTMOVIE_PATH,tf.name)
        # Not sure how to test that the movie got rotated.
        # Check width and height?
