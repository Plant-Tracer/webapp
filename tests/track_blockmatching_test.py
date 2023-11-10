import cv2
import numpy as np
import sys
from os.path import dirname, abspath

sys.path.append(dirname(dirname(abspath(__file__))))

from track_blockmatching import track_frame

def test_track_frame():
    cap = cv2.VideoCapture('tests/data/2019-07-12 circumnutation.mp4')
    ret, photo0 = cap.read()
    ret, photo1 = cap.read()
    point_array = np.array([[137, 86]], dtype=np.float32)
    point_array, status_array, err = track_frame(photo0, photo1, point_array)
    
    assert (status_array == 1)
    assert len(status_array) == 1
    assert len(point_array) == 1
    assert abs(point_array[0][0] - 137) <= 5
    assert abs(point_array[0][1] - 86) <= 5