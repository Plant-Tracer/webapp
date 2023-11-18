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

from os.path import abspath, dirname

import numpy as np
import cv2

# https://bottlepy.org/docs/dev/recipes.html#unit-testing-bottle-applications

from boddle import boddle

sys.path.append(dirname(dirname(abspath(__file__))))

from paths import TEST_DATA_DIR
import blocktrack
import bottle_app

from PIL import Image

# get the first MOV

PHOTO_SEQUENCE_PATTERN = 'frame_%05d.jpeg'
PHOTO_SEQUENCE_PATH_PATTERN = os.path.join(TEST_DATA_DIR, PHOTO_SEQUENCE_PATTERN)

# Get the fixtures from user_test
from user_test import new_user,new_course,API_KEY,MOVIE_ID,MOVIE_TITLE,USER_ID,DBWRITER

from movie_test import TEST_MOVIE_FILENAME

import track_blockmatching

# https://superuser.com/questions/984850/linux-how-to-extract-frames-from-a-video-lossless
def extract_all_frames(infilename, pattern, destdir):
    ffmpeg_cmd = ['ffmpeg', '-i', infilename, os.path.join(destdir, pattern), '-hide_banner']
    logging.info(ffmpeg_cmd)
    ret = subprocess.call(ffmpeg_cmd)
    if ret > 0:
        raise RuntimeError("failed: "+ffmpeg_cmd.join(' '))

def test_blocktrack():
    count = 0
    with tempfile.TemporaryDirectory() as td:
        extract_all_frames(TEST_MOVIE_FILENAME, PHOTO_SEQUENCE_PATTERN, td)
        context = None
        for fn in sorted(glob.glob(os.path.join(td, "*.jpeg"))):
            logging.info("process %s", fn)
            with open(fn, 'rb') as infile:
                img = Image.open(infile)
                context = blocktrack.blocktrack(context, img)
                count += 1
            logging.info("frame %d output: %s", count, context)
    logging.info("total frames processed: %d", count)
    if count == 0:
        raise RuntimeError("no frames processed")


def read_frames():
    """What does this do? Why are we reading from PHOTO_SEQUENCE_PATH_PATTERN?  Who set up `frame_%04d.jpg` ???  WHY DOES IT ASSUME WHICH DIRECTORY IT IS RUNNING IN"""
    cap = cv2.VideoCapture(PHOTO_SEQUENCE_PATH_PATTERN)
    ret, photo0 = cap.read()
    ret, photo1 = cap.read()
    return photo0, photo1


def test_track_frame():
    photo0, photo1 = read_frames()
    point_array = np.array([[279, 223]], dtype=np.float32)
    point_array, status_array, err = track_blockmatching.track_frame(photo0, photo1, point_array)

    assert (status_array == 1)
    assert len(status_array) == 1
    assert len(point_array) == 1
    assert abs(point_array[0][0] - 279) <= 5
    assert abs(point_array[0][1] - 223) <= 5


def test_api_track_frame(new_user):
    """test track_frame """
    cfg = new_user
    api_key = cfg[API_KEY]

    photo0, photo1 = read_frames()

    photo0_base64_data = base64.b64encode(photo0)
    photo1_base64_data = base64.b64encode(photo1)
    point_array = json.dumps([[279, 223]])

    with boddle(params={"api_key": api_key,
                        "photo0": photo0_base64_data,
                        "photo1": photo1_base64_data,
                        "point_array": point_array
                        }):

        with pytest.raises(bottle.HTTPResponse):
            res = bottle_app.api_track_frame()

            assert res['error'] is False, res['message']
            assert (res['status_array'][0] == 1).all()
            assert len(res['point_array']) == 1
            assert len(res['status_array']) == 2
            assert abs(res['point_array'][0][0] - 279) <= 5
            assert abs(res['point_array'][0][1] - 223) <= 5

def test_api_track_frame_error(new_user):
    """test track_frame """
    cfg = new_user
    api_key = cfg[API_KEY]

    photo0_base64_data = None
    photo1_base64_data = None
    point_array = json.dumps([[279, 223]])

    with boddle(params={"api_key": api_key,
                        "photo0": photo0_base64_data,
                        "photo1": photo1_base64_data,
                        "point array": point_array
                        }):
        res = bottle_app.api_track_frame()

        assert res['error'] is True, res['message']
