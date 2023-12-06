"""
Implements blockmatching algorithm in OpenCV.
"""

# pylint: disable=no-member
import json
import argparse
import tempfile

import cv2
import numpy as np
from constants import Engines

POINT_ARRAY_OUT='point_array_out'

#pylint: disable=unused-argument
def null_track_frame(*,frame0, frame1, trackpoints):
    return {POINT_ARRAY_OUT: trackpoints, 'status_array': None, 'err':None}
#pylint: enable=unused-argument


def cv2_track_frame(*,frame0, frame1, trackpoints):
    """
    Summary - Takes the original marked marked_frame and new frame and returns a frame that is annotated.
    :param: frame0    - cv2 image of the previous frame
    :param: frame1 - cv2 image of the current frame
    :param: trackpoints   - array of poins
    takes a     returns the new positions.

    """
    winSize=(15, 15)
    maxLevel=2
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)

    gray_frame0 = cv2.cvtColor(frame0, cv2.COLOR_BGR2GRAY)
    gray_frame1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
    point_array_out, status_array, err = cv2.calcOpticalFlowPyrLK(gray_frame0, gray_frame1, trackpoints, None,
                                               winSize=winSize, maxLevel=maxLevel, criteria=criteria)

    return {POINT_ARRAY_OUT: point_array_out, 'status_array': status_array, 'err': err}

#pylint: disable=unused-argument
def track_frame(*, engine, engine_version=None, frame0, frame1, trackpoints):
    if engine==Engines.NULL:
        return null_track_frame(frame0=frame0, frame1=frame1, trackpoints=trackpoints)
    elif engine==Engines.CV2:
        return cv2_track_frame(frame0=frame0, frame1=frame1, trackpoints=trackpoints)
    else:
        raise ValueError(f"No such engine: {engine}")
#pylint: enable=unused-argument


def track_frame_jpegs(*, engine, frame0_jpeg, frame1_jpeg, trackpoints):
    """
    :param: frame0_jpeg     - binary buffer containing a JPEG of previous frame
    :param: frame1_jpeg     - binary buffer containing a JPEG of current frame
    :param: trackpoints - an array of points that is being tracked.
    :return: a dictionary including:
       'points_array_out' - the input array of points
       'status' - a status message
       'error' - some kind of error message.
    """
    # This should work, but it didn't. So we are going to put them in tempoary files...
    # https://www.geeksforgeeks.org/python-opencv-imdecode-function/
    # image0 = np.asarray(bytearray(frame0_jpeg))
    # image1 = np.asarray(bytearray(frame1_jpeg))
    # return cv2_track_frame( image0, image1, trackpoints )
    with tempfile.NamedTemporaryFile(suffix='.jpeg',mode='wb') as tf0:
        with tempfile.NamedTemporaryFile(suffix='.jpeg',mode='wb') as tf1:
            tf0.write(frame0_jpeg)
            tf1.write(frame1_jpeg)
            return track_frame( engine=engine, frame0=cv2.imread(tf0.name),
                                frame1=cv2.imread(tf1.name), trackpoints=np.array(trackpoints,dtype=np.float32))


def track_movie(*, engine, moviefile, trackpoints, output_video_path):
    """
    Summary - takes in a movie(cap) and returns annotatted movie
    takes a annotated frame (marked_frame) that has the apex annotated
    takes the control points (trackpoints)
    initializes parameters to pass to track_frame
    returns a list of points
    TODO - What is movie? A filename? A movie?
    """
    if engine!=Engines.CV2:
        raise RuntimeError("This only runs with CV2")

    video_coordinates = np.array(trackpoints)
    p0  = trackpoints
    cap = cv2.VideoCapture(moviefile)
    ret, current_frame = cap.read()

    # should be movie name + tracked

    # Get video properties
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS)
    print(f"width: {width} height: {height} fps: {fps}  p0:{p0}")

    # Create a VideoWriter object to save the output video
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))

    # mark the current_frame with the initial trackpoints
    for point in trackpoints:
        x, y = point.ravel()
        tracked_current_frame = cv2.circle(current_frame, (int(x), int(y)), 3, (0, 0, 255), -1)
        out.write(tracked_current_frame)

    while ret:
        prev_frame = current_frame
        ret, current_frame = cap.read()
        if not ret:
            break

        ret = cv2_track_frame(frame0=prev_frame, frame1=current_frame, trackpoints=p0)
        p0 = ret[POINT_ARRAY_OUT]
        #, winSize=(15, 15), maxLevel=2, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
        video_coordinates = p0.tolist()

        # use the points to annotate the colored frames. write to colored tracked video
        for point in p0:
            x, y = point.ravel()
            tracked_current_frame = cv2.circle(current_frame,
                                               (int(x), int(y)), 3, (0, 0, 255), -1)# pylint: disable=no-member
            # Save the frame to the output video
            out.write(tracked_current_frame)

    cap.release()
    out.release()
    return video_coordinates


# The trackpoint is at (138,86) when the image is scaled to a width: 320 height: 240

if __name__ == "__main__":
    # the only requirement for calling track_movie() would be the "control points" and the movie
    parser = argparse.ArgumentParser(description="Run Track movie with specified movies and initial points",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('--engine',default='CV2')
    parser.add_argument(
        "--moviefile", default='tests/data/2019-07-12 circumnutation.mp4', help='mpeg4 file')
    parser.add_argument(
        "--points_to_track", default='[[138, 86]]', help="list of points to track as json 2D array.")
    parser.add_argument('--outfile',default='tracked_output.mp4')
    args = parser.parse_args()
    tpts = json.loads(args.points_to_track)
    trackpoints = np.array(tpts, dtype=np.float32)
    print("args.points_to_track=",args.points_to_track,tpts,trackpoints)
    track_movie(engine=args.engine, moviefile=args.moviefile, trackpoints=trackpoints, output_video_path=args.outfile)
