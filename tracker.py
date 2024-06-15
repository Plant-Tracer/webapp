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
import os
from collections import defaultdict

import math
import cv2
import numpy as np
import paths

FFMPEG_PATH = paths.ffmpeg_path()
POINT_ARRAY_OUT='point_array_out'
RED = (0, 0, 255)
BLACK = (0,0,0)
TEXT_FACE = cv2.FONT_HERSHEY_DUPLEX
TEXT_SCALE = 0.75
TEXT_THICKNESS = 2
TEXT_MARGIN = 5
MIN_MOVIE_BYTES = 10

## JPEG support

class ConversionError(RuntimeError):
    """Special error"""

class MovieCorruptError(RuntimeError):
    """Special error"""

def cv2_track_frame(*,frame_prev, frame_this, trackpoints):
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
        gray_frame0 = cv2.cvtColor(frame_prev, cv2.COLOR_BGR2GRAY)
        gray_frame1 = cv2.cvtColor(frame_this, cv2.COLOR_BGR2GRAY)
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
    :param: trackpoints - array of dicts where each dict has at least an ['x'] and a ['y']
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

def convert_frame_to_jpeg(img, quality=90):
    """Use CV2 to convert a frame to a jpeg"""
    _,jpg_img = cv2.imencode('.jpg',img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return jpg_img.tobytes()

def extract_frame(*, movie_data, frame_number, fmt):
    """Extract a single frame from movie data using CV2. This is not an efficient approach to read the entire movie.
    Perhaps  make frame_number an array of frames to allow multiple frames to be extracted, with a callback?
    :param: movie_data - binary object of data
    :param: frame_number - frame to extract
    :param: fmt - format wanted. CV2-return a CV2 image; 'jpeg' - return a jpeg image as a byte array.
    """
    assert fmt in ['CV2','jpeg']
    assert movie_data is not None
    # CV2's VideoCapture method does not support reading from a memory buffer.
    # So perhaps we will change this to use a named pipe
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
                return convert_frame_to_jpeg(frame)
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


def render_tracked_movie(*, moviefile_input, moviefile_output, movie_trackpoints, label_frames=True):
    # Create a VideoWriter object to save the output video to a temporary file (which we will then transcode with ffmpeg)
    # movie_trackpoints is an array of records where each has the form:
    # {'x': 152.94203, 'y': 76.80803, 'status': 1, 'err': 0.08736111223697662, 'label': 'mypoint', 'frame_number': 189}

    cap = cv2.VideoCapture(moviefile_input)
    ret, current_frame_data = cap.read()
    # Get video properties
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS)

    logging.info("start movie rendering")
    trackpoints_by_frame = defaultdict(list)
    for tp in movie_trackpoints:
        trackpoints_by_frame[tp['frame_number']].append(tp)

    with tempfile.NamedTemporaryFile(suffix='.mp4') as tf:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(tf.name, fourcc, fps, (width, height))

        for frame_number in range(1_000_000):
            ret, current_frame_data = cap.read()
            if not ret:
                break

            # Label the output and write it
            if label_frames:
                cv2_label_frame(frame=current_frame_data, trackpoints=trackpoints_by_frame[frame_number], frame_label=frame_number)
            out.write(current_frame_data)

        cap.release()
        out.release()

        # Finally, use ffmpeg to transcode the output to a proper mp4 file (This shouldn't be necessary)
        cleanup_mp4(infile=tf.name, outfile=moviefile_output)
    logging.info("rendered movie")


def prototype_callback(*,frame_number,frame_data,frame_trackpoints):
    logging.debug("frame_number=%s len(frame_data)=%s frame_trackpoints=%s",frame_number,len(frame_data),frame_trackpoints)

def track_movie(*, moviefile_input, input_trackpoints, frame_start=0, label_frames=False, callback=prototype_callback):
    """
    Summary - takes in a movie(cap) and returns annotatted movie with red dots on all the trackpoints.
    Draws frame numbers on each frame
    :param: moviefile_input  - file name of an MP4 to track. Must not be annotated. CV2 cannot read movies from memory; this is a known problem.
    :param: trackpoints - a list all current trackpoints.
                        - Each trackpoint is dictionary {'x', 'y', 'label', 'frame_number'} to track.
                        - code would be cleaner if this were a dictionary keyed by label!
    :param: frame_start - the frame to start tracking out (frames 0..(frame_start-1) are just copied to output)
    :param: callback - a function to callback with (*, frame_number, jpeg, trackpoints)

    Note - no longer renders the tracked movie. That's now in render_tracked_movie().
         - no longer returns trackpoints; that's the job of the callback

         - Frame0 is never tracked. It's trackpoints are the provided trackpoints.
    """
    cap = cv2.VideoCapture(moviefile_input)
    frame_this = None

    # should be movie name + tracked

    # Create a VideoWriter object to save the output video to a temporary file (which we will then transcode with ffmpeg)
    logging.info("start movie tracking")
    for frame_number in range(1_000_000):
        frame_prev = frame_this
        result, frame_this = cap.read()
        if not result:
            break

        # Copy over the trackpoints for the current frame if this was previously tracked or is the first frame to track
        # This also copies over frame_prev at start (when frame_number=0 and frame_start=0, it is <= frame_start)
        frame_show = frame_this # frame to show
        if frame_number <= frame_start:
            current_trackpoints = [tp for tp in input_trackpoints if tp['frame_number']==frame_number]
            # Call the callback if we have one
            if label_frames:
                frame_show = frame_this.copy()
                cv2_label_frame(frame=frame_show, trackpoints=current_trackpoints, frame_label=frame_number)
            callback(frame_number=frame_number, frame_data=frame_show, frame_trackpoints=current_trackpoints)
            continue

        # If this is after the starting frame, then track it
        # This is run every time through the loop except the first time.
        assert frame_prev is not None
        trackpoints_by_label = { tp['label']:tp for tp in current_trackpoints }
        new_trackpoints = cv2_track_frame(frame_prev=frame_prev, frame_this=frame_this, trackpoints=current_trackpoints)

        # Copy in updated trackpoints
        for tp in new_trackpoints:
            trackpoints_by_label[tp['label']] = tp

        # create new list of trackpoints
        current_trackpoints = trackpoints_by_label.values()

        # And set their new frame numbers
        for tp in current_trackpoints:
            tp['frame_number'] = frame_number # set the frame number

        # Call the callback if we have one
        if callback is not None:
            if label_frames:
                frame_show = frame_this.copy()
                cv2_label_frame(frame=frame_show, trackpoints=[], frame_label=frame_number)
            callback(frame_number=frame_number, frame_data=frame_show, frame_trackpoints=current_trackpoints)

    cap.release()

def rotate_movie(movie_input, movie_output, transpose=1):
    assert os.path.getsize(movie_input) > MIN_MOVIE_BYTES
    assert os.path.getsize(movie_output) == 0
    subprocess.call([FFMPEG_PATH,'-hide_banner','-loglevel','error',
                     '-i',movie_input,'-vf',f'transpose={int(transpose)}','-c:a','copy','-y',movie_output])
    assert os.path.getsize(movie_output) > MIN_MOVIE_BYTES

################################################################
### Code to figure convert from screen coordinatrs to actual mm
### Given that two points are labeled "ruler xx mm" where xx is the ruler position in milimeters

RULER_POINT_RE = re.compile(r'ruler? +([0-9]+) *mm')
def identify_calibration_labels(label):
    """returns the position on the ruler in mm or returns None"""
    m = RULER_POINT_RE.searh(label)
    return m.group(1) if m else None

def compute_distance(pt1, pt2):
    """Returns the distance between point1 and point2. Points are {'x':x,'y':y} dicts."""
    return math.sqrt( (pt1['x']-pt1['x']) ** 2 + (pt1['y']-pt2['y'])**2)

def calibrate_point(pt, calibration_label1, calibration_label2):
    """Given a point and two calibration labels, compute the distance,
    and return the point calibrated. (So in addition to having a 'x'
    and 'y' property in dictionary, it also has a 'x_mm' and a 'y_mm'
    in the dictionary.)
    """

    ### TODO - Evan - write the code here


def calibrate_trackpoint_frames(trackpoints):
    """
    Given an array of many trackpoints for many frames, epeat for every frame:
    Find the trackpoints for the frame, identify the the calibration points,
    pass each trackpoint to calibrate_point with the two calibration points,
    and create a new trackpoints list that has the non-calibration points calibrated for each frame.
    """

    ### TODO - Evan - write code here


### OLD CODE
#def pixels_to_mm(*, pt, calibration_points):
#
#    pixel_distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
#    mm_per_pixel = straight_line_distance_mm / pixel_distance
#
#    X1_mm = x1 * mm_per_pixel
#    Y1_mm = y1 * mm_per_pixel
#    X2_mm = x2 * mm_per_pixel
#    Y2_mm = y2 * mm_per_pixel
#
#    return round(X1_mm, 4), round(Y1_mm, 4), round(X2_mm, 4), round(Y2_mm, 4)


if __name__ == "__main__":
    # the only requirement for calling track_movie() would be the "control points" and the movie
    parser = argparse.ArgumentParser(description="Run Track movie with specified movies and initial points",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

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
    input_trackpoints = [ {**tp,**{'frame_number':0}} for tp in trackpoints]

    # Get the new trackpoints
    trackpoints = []
    # pylint: disable=unused-argument
    def callback(*,frame_number,frame_data,frame_trackpoints):
        trackpoints.extend(frame_trackpoints)


    track_movie(moviefile_input=args.moviefile,
                input_trackpoints=input_trackpoints,
                callback=callback )
    # Now render the movie
    render_tracked_movie( moviefile_input= args.moviefile, moviefile_output='tracked.mp4',
                          movie_trackpoints=trackpoints)
    subprocess.call(['open','tracked.mp4'])
