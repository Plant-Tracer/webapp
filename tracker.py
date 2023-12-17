"""
Implements blockmatching algorithm in OpenCV.
"""

# pylint: disable=no-member
import json
import argparse
import tempfile
import logging

import magic
import cv2
import numpy as np
from constants import Engines,MIME

POINT_ARRAY_OUT='point_array_out'
RED = (0, 0, 255)
BLACK = (0,0,0)
TEXT_FACE = cv2.FONT_HERSHEY_DUPLEX
TEXT_SCALE = 0.75
TEXT_THICKNESS = 2

## JPEG support

class ConversionError(RuntimeError):
    """Special error"""
    def __init__(self,msg):
        super().__init__(msg)

def is_jpeg(buffer):
    return magic.from_buffer(buffer,mime=True) in [ MIME.JPEG ]

def cv2_track_frame(*,frame0, frame1, trackpoints):
    """
    Summary - Takes the original marked marked_frame and new frame and returns a frame that is annotated.
    :param: frame0 - cv2 image of the previous frame
    :param: frame1 - cv2 image of the current frame
    :param: trackpoints   - array of poins
    :return: dict with point_array, status array, and error condition array

    """
    winSize=(15, 15)
    maxLevel=2
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
    try:
        gray_frame0 = cv2.cvtColor(frame0, cv2.COLOR_BGR2GRAY)
        gray_frame1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        point_array_out, status_array, err = cv2.calcOpticalFlowPyrLK(gray_frame0, gray_frame1, trackpoints, None,
                                                                      winSize=winSize, maxLevel=maxLevel, criteria=criteria)
    except cv2.error:
        point_array_out = []
        status_array = []
        err = []

    return {POINT_ARRAY_OUT: point_array_out, 'status_array': status_array, 'err': err}

def cv2_label_frame(*, frame, trackpoints):
    # use the points to annotate the colored frames. write to colored tracked video
    # https://stackoverflow.com/questions/55904418/draw-text-inside-circle-opencv
    for point in trackpoints:
        x, y = point.ravel()
        cv2.circle(current_frame, (int(x), int(y)), 3, RED, -1) # pylint: disable=no-member

    text = str(frame_number)
    WHITE = (255,255,255)
    text_size, _ = cv2.getTextSize(text, TEXT_FACE, TEXT_SCALE, TEXT_THICKNESS)
    text_origin = ( 5, len(current_frame)-5)
    cv2.rectangle(current_frame, text_origin, (text_origin[0]+text_size[0],text_origin[1]-text_size[1]), RED, -1)
    cv2.putText(current_frame, text, text_origin, TEXT_FACE, TEXT_SCALE, WHITE, TEXT_THICKNESS, cv2.LINE_4)


def track_movie(*, engine, engine_version=None, moviefile_input, input_trackpoints, moviefile_output):
    """
    Summary - takes in a movie(cap) and returns annotatted movie with red dots on all the trackpoints.
    Draws frame numbers on each frame
    :param: engine - the engine to use. CV2 is the only supported engine at the moment.
    :param: moviefile - an MP4 to track. CV2 cannot read movies from memory; this is a known problem.
    :param: trackpoints - an array of (x,y) points to track. [pt#][0], [pt#][1]
    :param: frame_start - the frame to start tracking out (frames 0..(frame_start-1) are just copied to output)
    :return: dict 'output_trackpoints' = [frame][pt#][0], [frame][pt#][1]

    """
    if engine!=Engines.CV2:
        raise RuntimeError("This only runs with CV2")

    video_coordinates = np.array(trackpoints)
    p0  = trackpoints
    cap = cv2.VideoCapture(moviefile_input)
    ret, current_frame = cap.read()

    output_trackpoints = []

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


    for frame_number in range(1_000_000):
        prev_frame = current_frame
        ret, current_frame = cap.read()
        if not ret:
            break

        ret = cv2_track_frame(frame0=prev_frame, frame1=current_frame, trackpoints=p0)
        p0  = ret[POINT_ARRAY_OUT]
        cv2_label_frame(frame=frame1, trackpoints=p0)

        out.write(current_frame)
        output_trackpoints.append(p0)

    cap.release()
    out.release()
    return {'output_trackpoints':output_trackpoints}


def extract_frame(*, movie_data, frame_number, format):
    """Download movie_id to a temporary file, find frame_number and return it in the request format.
    """
    with tempfile.NamedTemporaryFile(mode='ab') as tf:
        tf.write(movie_data)
        tf.flush()
        cap = cv2.VideoCapture(tf.name)

    # skip to frame_number (first frame is #0)
    for fn in range(frame_number+1):
        ret, frame = cap.read()
        if not ret:
            return None
        if fn==frame_number:
            if format=='CV2':
                return frame
            elif format=='jpeg':
                with tempfile.NamedTemporaryFile(suffix='.jpg',mode='rwb') as tf:
                    cv2.imwrite(tf.name, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                    tf.seek(0)
                    return tf.read()
            else:
                raise ValueError("Invalid format: "+format)
    raise RuntimeError("invalid frame_number")

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
