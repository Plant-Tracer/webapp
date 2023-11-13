# pylint: disable=no-member
import cv2
import numpy as np
import sys
from os.path import dirname, abspath

sys.path.append(dirname(dirname(abspath(__file__))))

from track_blockmatching import track_frame

def test_track_frame():
    
    photo0, photo1 = read_frames()
    point_array = np.array([[279, 223]], dtype=np.float32)
    point_array, status_array, err = track_frame(photo0, photo1, point_array)
    
    assert (status_array == 1)
    assert len(status_array) == 1
    assert len(point_array) == 1
    assert abs(point_array[0][0] - 279) <= 5
    assert abs(point_array[0][1] - 223) <= 5
    
def read_frames():
    
    cap = cv2.VideoCapture('tests/data/frame_%04d.jpg')
    ret, photo0 = cap.read()
    ret, photo1 = cap.read()
        
    return photo0, photo1        