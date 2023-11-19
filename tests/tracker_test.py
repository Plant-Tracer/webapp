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
import magic

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

# Get the fixtures from user_test
from user_test import new_user,new_course,API_KEY,MOVIE_ID,MOVIE_TITLE,USER_ID,DBWRITER

from endpoint_test import TEST_MOVIE_FILENAME
import movietool
import track_blockmatching

# https://superuser.com/questions/984850/linux-how-to-extract-frames-from-a-video-lossless

@pytest.fixture
def extracted_jpeg_frames():
    """Fixture that returns a dictionary containing two frames - 'frame0' and 'frame1'. Both are JPEGs"""
    with tempfile.TemporaryDirectory() as td:
        output_template = os.path.join(td, movietool.JPEG_TEMPLATE)
        logging.info("output_template=%s",output_template)
        (stdout,stderr) = movietool.extract_all_frames_from_file_with_ffmpeg(TEST_MOVIE_FILENAME, output_template)
        jpegs = movietool.frames_matching_template(output_template)
        logging.info("extracted jpegs: %s",jpegs)
        assert len(jpegs)>0
        yield {'jpegs':jpegs}
    logging.info("Done with frames; temporary directory deleted")

def test_extracted_jpeg_frames(extracted_jpeg_frames):
    frames = extracted_jpeg_frames['jpegs']
    assert len(frames)>2

    # Make sure that the files exist and that they have the correct mime type
    for i in [0,1]:
        assert os.path.exists( frames[i] )
        assert magic.from_file( frames[i], mime=True) == 'image/jpeg'


def test_blocktrack(extracted_jpeg_frames):
    frames = extracted_jpeg_frames['jpegs']
    count = 0
    context = None
    logging.info("frames=%s",frames)
    for infile in frames:
        logging.info("process %s", infile)
        with open(infile, 'rb') as infile:
            img = Image.open(infile)
            context = blocktrack.blocktrack(context, img)
            count += 1
        logging.info("frame %d output: %s", count, context)
    logging.info("total frames processed: %d", count)
    if count == 0:
        raise RuntimeError("no frames processed")


@pytest.fixture
def first_two_frames(extracted_jpeg_frames):
    """Returns the first two extracted frames as CV2 images"""
    frames = extracted_jpeg_frames['jpegs']
    return ( cv2.imread(frames[0]), cv2.imread(frames[1]))


def test_track_frame(first_two_frames):
    photo0, photo1 = first_two_frames
    point_array = np.array([[279, 223]], dtype=np.float32)
    point_array, status_array, err = track_blockmatching.track_frame(photo0, photo1, point_array)

    assert (status_array == 1)
    assert len(status_array) == 1
    assert len(point_array) == 1
    assert abs(point_array[0][0] - 279) <= 5
    assert abs(point_array[0][1] - 223) <= 5


def test_api_track_frame(new_user, first_two_frames):
    """test track_frame """
    cfg = new_user
    api_key = cfg[API_KEY]

    photo0, photo1 = first_two_frames
    photo0_base64_data = base64.b64encode(photo0)
    photo1_base64_data = base64.b64encode(photo1)
    point_array = json.dumps([[279, 223]])

    with boddle(params={"api_key": api_key,
                        "photo0": photo0_base64_data,
                        "photo1": photo1_base64_data,
                        "point_array": point_array
                        }):
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
