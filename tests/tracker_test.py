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
        yield {'jpeg_file_names':jpegs}
    logging.info("Done with frames; temporary directory deleted")

def test_extracted_jpeg_frames(extracted_jpeg_frames):
    """Test the fixture to make sure that it is good"""
    frames = extracted_jpeg_frames['jpeg_file_names']
    assert len(frames)>2

    # Make sure that the files exist and that they have the correct mime type
    for i in [0,1]:
        assert os.path.exists( frames[i] )
        assert magic.from_file( frames[i], mime=True) == 'image/jpeg'

@pytest.mark.skip(reason='blocktrack.py is not operational yet')
def test_blocktrack(extracted_jpeg_frames):
    """Using JPEGs from the fixture, test the blocktrack.blocktrack function"""
    frames = extracted_jpeg_frames['jpeg_file_names']
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


def test_track_frame_jpegs(extracted_jpeg_frames):
    """Test the track_frame_jpegs method by giving it two frames as JPEGs and validating its results"""

    frames = extracted_jpeg_frames['jpeg_file_names']
    jpegs = []
    for i in [0,1]:
        with open(frames[i],"rb") as f:
            jpegs.append(f.read())
            assert magic.from_buffer( jpegs[i], mime=True) == 'image/jpeg'

    point_array_in = [[279, 223]]
    res = track_blockmatching.track_frame_jpegs(jpegs[0], jpegs[1], point_array_in)

    status_array = res['status_array']
    assert len(status_array) == 1

    err = res['res']
    point_array_out = res['point_array_out']
    assert len(point_array_out) == 1
    assert len(point_array_out[0]) == 2
    assert abs(point_array_out[0][0] - 279) <= 5
    assert abs(point_array_out[0][1] - 223) <= 5

@pytest.fixture
def first_two_frames_as_cv2_images(extracted_jpeg_frames):
    """Returns the first two extracted frames as CV2 images."""
    frames = extracted_jpeg_frames['jpeg_file_names']
    return {'images':[cv2.imread(frames[0]), cv2.imread(frames[1])]}


def test_track_frame_cv2_images(first_two_frames_as_cv2_images):
    """Test the track_frame_cv2 method by giving it two frames as NP arrays and validating its results"""
    photo0, photo1 = first_two_frames_as_cv2_images['images']
    point_array_in = np.array([[279, 223]], dtype=np.float32)
    res = track_blockmatching.track_frame_cv2(photo0, photo1, point_array_in)
    logging.info("res=%s",json.dumps(res,default=str))

    status_array = res['status_array']
    assert len(status_array) == 1

    err = res['err']
    point_array_out = res['point_array_out']
    assert len(point_array_out) == 1
    assert len(point_array_out[0]) == 2
    assert abs(point_array_out[0][0] - 279) <= 5
    assert abs(point_array_out[0][1] - 223) <= 5



def test_api_track_frame(new_user, extracted_jpeg_frames):
    """Test the track_frame API. Note that the API requires base64-encoded JPEG files and NOT CV2 arrays. It also requires a valid API key"""
    cfg      = new_user
    fnames   = extracted_jpeg_frames['jpeg_file_names']

    # First check to make sure that the API generates an error when given an invalid API key
    with boddle(params={"api_key": 'invalid key'}):
        res = bottle_app.api_track_frame()
        assert res['error'] is True, res['message']

    # Now check with a valid API key but with no image parameters
    # Note that the error no longer comes from an exception
    params = {}
    params['api_key'] = cfg[API_KEY]
    with boddle(params={"api_key": 'invalid key'}):
        res = bottle_app.api_track_frame()
        assert res['error'] is True, res['message']

    # Now add the images but no point_array to track
    for i in [0,1]:
        with open(fnames[i],'rb') as f:
            params[f'frame{i}_base64_data'] = base64.b64encode(f.read())
    with boddle(params={"api_key": 'invalid key'}):
        res = bottle_app.api_track_frame()
        assert res['error'] is True, res['message']

    # point_array is a JSON-encoded array
    # All of these are uploaded as parameters, which are not JSON encoded by the API
    params['point_array'] = json.dumps([[279, 223]])

    # Now run the function and check the results
    logging.warning("params.keys()=%s",list(params.keys()))
    with boddle(params=params):
        res = bottle_app.api_track_frame()
        assert res['error'] is False, res['message']
        #assert res['status_array'][0] == 1
        #assert len(res['status_array']) == 2
        assert len(res['point_array_out']) == 1
        assert abs(res['point_array_out'][0][0] - 279) <= 5
        assert abs(res['point_array_out'][0][1] - 223) <= 5
