"""
Implements blockmatching algorithm in OpenCV.
Also implements support movie routines
"""

# pylint: disable=no-member
import json
import argparse
import tempfile
import subprocess
import logging
import time
import os
import errno

import cv2
import numpy as np
from constants import Engines,C
import paths

FFMPEG_PATH = paths.ffmpeg_path()
POINT_ARRAY_OUT='point_array_out'
RED = (0, 0, 255)
BLACK = (0,0,0)
TEXT_FACE = cv2.FONT_HERSHEY_DUPLEX
TEXT_SCALE = 0.75
TEXT_THICKNESS = 2
TEXT_MARGIN = 5

## JPEG support

class ConversionError(RuntimeError):
    """Special error"""

class MovieCorruptError(RuntimeError):
    """Special error"""

def cv2_track_frame(*,frame0, frame1, trackpoints):
    """
    Summary - Takes the original marked marked_frame and new frame and returns a frame that is annotated.
    :param: frame0 - cv2 image of the previous frame in CV2 format
    :param: frame1 - cv2 image of the current frame in CV2 format
    :param: trackpoints  - array of trackpoints (dicts of x,y and label)
    :return: array of trackpoints

    """
    winSize=(15, 15)
    maxLevel=2
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
    tpts = np.array([[pt['x'],pt['y']] for pt in trackpoints],dtype=np.float32)

    try:
        gray_frame0 = cv2.cvtColor(frame0, cv2.COLOR_BGR2GRAY)
        gray_frame1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        point_array_out, status_array, err = cv2.calcOpticalFlowPyrLK(gray_frame0, gray_frame1, tpts, None,
                                                                      winSize=winSize, maxLevel=maxLevel, criteria=criteria)
        trackpoints_out = []
        for (i,pt) in enumerate(trackpoints):
            if status_array[i]==1:
                trackpoints_out.append({'x':point_array_out[i][0],
                                        'y':point_array_out[i][1],
                                        'status':int(status_array[i][0]),
                                        'err':float(err[i][0]),
                                        'label':pt['label']})
    except cv2.error:      # pylint: disable=catching-non-exception
        trackpoints_out = []

    return trackpoints_out

def cv2_label_frame(*, frame, trackpoints, frame_label=None):
    """
    :param: frame - cv2 frame
    :param: trackpoints - array of dicts
    :param frame_label - if present, label for frame number (can be int or string)
    """

    # frame_height = len(frame)
    frame_width = len(frame[0])

    # use the points to annotate the colored frames. write to colored tracked video
    # https://stackoverflow.com/questions/55904418/draw-text-inside-circle-opencv
    for point in trackpoints:
        cv2.circle(frame, (int(point['x']), int(point['y'])), 3, RED, -1) # pylint: disable=no-member

    if frame_label is not None:
        # Label in upper right hand corner
        text = str(frame_label)
        WHITE = (255,255,255)
        text_size, _ = cv2.getTextSize(text, TEXT_FACE, TEXT_SCALE, TEXT_THICKNESS)
        text_origin = ( frame_width - text_size[0] - TEXT_MARGIN, text_size[1]+TEXT_MARGIN)
        cv2.rectangle(frame, text_origin, (text_origin[0]+text_size[0],text_origin[1]-text_size[1]), RED, -1)
        cv2.putText(frame, text, text_origin, TEXT_FACE, TEXT_SCALE, WHITE, TEXT_THICKNESS, cv2.LINE_4)


def extract_movie_metadata(*, movie_data):
    """Use OpenCV to get the movie metadata"""
    with tempfile.NamedTemporaryFile(mode='ab') as tf:
        tf.write(movie_data)
        tf.flush()
        cap = cv2.VideoCapture(tf.name)
        total_frames = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if len(frame)==0:
                raise MovieCorruptError()

            total_frames += 1
    return {'total_frames':total_frames,
            'total_bytes':len(movie_data),
            'width':int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            'height':int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            'fps':cap.get(cv2.CAP_PROP_FPS)}

def extract_frame(*, movie_data, frame_number, fmt):
    """Download movie_id to a temporary file, find frame_number and return it in the request fmt.
    :param: movie_data - binary object of data
    :param: frame_nubmer - frame to extract
    :param: fmt - format wanted (should be CV2 or jpeg)
    """
    assert fmt in ['CV2','jpeg']
    with tempfile.NamedTemporaryFile(mode='ab') as tf:
        tf.write(movie_data)
        tf.flush()
        cap = cv2.VideoCapture(tf.name)

    # skip to frame_number (first frame is #0)
    for fn in range(frame_number+1):
        ret, frame = cap.read()
        if not ret:
            raise ValueError(f"invalid frame_number {frame_number}")
        if fn==frame_number:
            if fmt=='CV2':
                return frame
            elif fmt=='jpeg':
                with tempfile.NamedTemporaryFile(suffix='.jpg',mode='w+b') as tf:
                    cv2.imwrite(tf.name, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                    tf.seek(0)
                    return tf.read()
            else:
                raise ValueError("Invalid fmt: "+fmt)
    raise ValueError(f"invalid frame_number {frame_number}")

def cleanup_mp4(*,infile,outfile):
    """Given an import file, clean it up with ffmpeg"""

    # Make sure infile and FFMPEG_PATH exist
    for p in [infile, FFMPEG_PATH]:
        if not os.path.exists(p):
            raise FileNotFoundError(p)

    # If outfile exists, it will be overwritten
    args = ['-y','-hide_banner','-loglevel','error','-i',infile,'-vcodec','h264',outfile]
    subprocess.call([ FFMPEG_PATH ] + args)


def track_movie(*, engine_name, engine_version=None, moviefile_input, input_trackpoints, moviefile_output, frame_start=0, callback=None):
    """
    Summary - takes in a movie(cap) and returns annotatted movie with red dots on all the trackpoints.
    Draws frame numbers on each frame
    :param: engine - the engine to use. CV2 is the only supported engine at the moment.
    :param: moviefile_input  - file name of an MP4 to track. Must not be annotated. CV2 cannot read movies from memory; this is a known problem.
    :param: moviefile_output - file name of the tracked output, with annotations.
    :param: trackpoints - a list of dictionaries {'x', 'y', 'label', 'frame_number'} to track.  Those before frame_start will be copied to the output.
    :param: frame_start - the frame to start tracking out (frames 0..(frame_start-1) are just copied to output)
    :param: callback - a function to callback with (callback_arg, output_trackpoints)
    :return: dict 'output_trackpoints' = [frame][pt#][0], [frame][pt#][1]

    """
    if engine_name!=Engines.CV2:
        raise RuntimeError(f"Engine_name={engine_name} engine_version={engine_version} but this only runs with CV2")

    cap = cv2.VideoCapture(moviefile_input)
    ret, current_frame_data = cap.read()

    # should be movie name + tracked

    # Get video properties
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS)

    # Create a VideoWriter object to save the output video to a temporary file (which we will then transcode with ffmpeg)
    track_delay = float(os.environ.get(C.TRACK_DELAY,0))
    with tempfile.NamedTemporaryFile(suffix='.mp4') as tf:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(tf.name, fourcc, fps, (width, height))

        output_trackpoints = []
        for frame_number in range(1_000_000):
            prev_frame_data = current_frame_data
            ret, current_frame_data = cap.read()
            if not ret:
                break

            # Copy over the trackpoints for the current frame if this was previously tracked or is the first frame to track
            if frame_number <= frame_start:
                current_trackpoints = [tp for tp in input_trackpoints if tp['frame_number']==frame_number]

            # If this is after the starting frame, then track it
            if frame_number > frame_start:
                current_trackpoints = cv2_track_frame(frame0=prev_frame_data, frame1=current_frame_data, trackpoints=current_trackpoints)

            # Label the output and write it
            cv2_label_frame(frame=current_frame_data, trackpoints=current_trackpoints, frame_label=frame_number)
            out.write(current_frame_data)

            # Add the trackpionts to the output list, giving each a frame number
            output_trackpoints.extend( [ {**tp, **{'frame_number':frame_number}} for tp in current_trackpoints] )

            # Call the callback if we have one
            if callback is not None:
                callback(output_trackpoints)

            ### DEBUG CODE
            if track_delay:
                logging.debug("TRACK DELAY %s",track_delay)
                time.sleep(track_delay)

        cap.release()
        out.release()

        # Finally, use ffmpeg to transcode the output to a proper mp4 file (This shouldn't be necessary)
        cleanup_mp4(infile=tf.name, outfile=moviefile_output)

    return {'output_trackpoints':output_trackpoints}

if __name__ == "__main__":
    # the only requirement for calling track_movie() would be the "control points" and the movie
    parser = argparse.ArgumentParser(description="Run Track movie with specified movies and initial points",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('--engine',default='CV2')
    parser.add_argument(
        "--moviefile", default='tests/data/2019-07-12 circumnutation.mp4', help='mpeg4 file')
    parser.add_argument(
        "--points_to_track", default='[{"x":138,"y":86,"label":"mypoint"}]',
        help="list of points to track as json 2D array.")
    parser.add_argument('--outfile',default='tracked_output.mp4')
    args = parser.parse_args()

    # Get the trackpoints
    trackpoints = json.loads(args.points_to_track)
    # Make sure every trackpoint is for frame 0
    trackpoints = [ {**tp,**{'frame_number':0}} for tp in trackpoints]

    res = track_movie(engine_name=args.engine,
                      moviefile_input=args.moviefile,
                      input_trackpoints=trackpoints, moviefile_output=args.outfile)
    print("results:")
    print(json.dumps(res,default=str,indent=4))
