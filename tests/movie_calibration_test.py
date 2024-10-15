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
import re

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
from constants import MIME,Engines
import tracker

# Regular expression to match ruler position.
# User might label points "rule 00mm" or "ruler 00 mm" or "ruler 10 mm"
# so the regular expression accepts a variety of options
def test_identify_calibration_labels_label():
    assert tracker.identify_ruler_label("") is None
    assert tracker.identify_ruler_label("nope") is None
    assert tracker.identify_ruler_label("ruler 1 mm") is 1
    assert tracker.identify_ruler_label("rule 10 mm") is 10
    assert tracker.identify_ruler_label("ruler 20mm") is 20

def test_compute_distance():
    ### TODO - Evan write this

### Evan - create a test set of trackpoints here that has a list with three trackpoints and two
### calibration points for two frames

TEST_TRACKPOINTS = [ ... ]

def test_calibrate_point():
    ### TODO - Evan - write this test that uses your test data above for a single point

def test_calibrate_trackpoint_frames():
    ### TODO - Evan - write this test that uses your test data above for all of the trackpoints


def test_get_actual_distance_mm():
    label = 'ruler 20 mm'
    actual_distance_mm = -1
    if re.match(pattern_without_zero, label):
        actual_distance_mm = int(re.search(pattern_without_zero, label).group(1))
        assert actual_distance_mm == 20
    else:
        assert actual_distance_mm == -1

    pattern = r'ruler (\d+) mm'  # ruler xx mm pattern
    label_0 = 'ruler 0 mm'
    label_20 = 'ruler 20 mm'
    assert re.match(pattern, label_0) is not None
    assert re.match(pattern, label_20) is not None


def test_pixels_to_mm():
    x1, y1 = 100, 150
    x2, y2 = 200, 250
    straight_line_distance_mm = 50.0

    x1_mm, y1_mm, x2_mm, y2_mm = tracker.pixels_to_mm(
        x1, y1, x2, y2, straight_line_distance_mm)
    EPSILON=0.0001
    assert math.fabs(x1_mm - 35.3553) <= EPSILON
    assert math.fabs(y1_mm - 53.033)  <= EPSILON
    assert math.fabs(x2_mm - 70.7107) <= EPSILON
    assert math.fabs(y2_mm - 88.3883) <= EPSILON
