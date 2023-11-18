# pylint: disable=no-member
import cv2
import numpy as np
import sys
import json

import boddle

from os.path import dirname, abspath


sys.path.append(dirname(dirname(abspath(__file__))))

# Get the fixtures from user_test
from user_test import new_user,new_course,API_KEY,MOVIE_FILENAME,MOVIE_ID,MOVIE_TITLE,USER_ID,DBWRITER,PHOTO_SEQUENCE_NAME

import track_blockmatching

PHOTO_SEQUENCE_NAME = os.path.join(MYDIR, "data", "frame_%04d.jpg")

def read_frames():
    """What does this do? Why are we reading from PHOTO_SEQUENCE_NAME?  Who set up `frame_%04d.jpg` ???"""

    cap = cv2.VideoCapture(PHOTO_SEQUENCE_NAME)
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

    photo0, photo1 = track_blockmatching_test.read_frames()

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
