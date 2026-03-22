"""
Implements blockmatching algorithm in OpenCV.
Includes all code for getting the entire movie (get_movie_data) and getting individual
frames (extract_frame, get_jpeg_dimensions, resize_jpeg_to_fit).
Shared entry point run_tracking(...) uses module-level Lambda helpers directly.
Frame serving (get-frame API) runs in this Lambda (resize); the VM uses this module only for
run_tracking and for api_get_movie_data (full movie download).
Lives in lambda-resize; main app imports via app.tracker shim (re-exports from resize_app.tracker).

All production paths use cv2 + Pillow only (no ffmpeg). cleanup_mp4, rotate_movie, and
prepare_movie_for_tracking are LEGACY: they require an ffmpeg binary and are kept for
optional/local use (e.g. CLI render_movie_traced, tests). run_tracking always uses
prepare_movie_for_tracking_cv2 (rotate_zip) for rotate+scale.

Uses imageio to write tracked movie, which does not have H.264 licensing issues

"""

# pylint: disable=no-member
from typing import List,Optional,NamedTuple
import json
import argparse
import subprocess
import logging
import zipfile
from pathlib import Path

import cv2
import imageio
import numpy as np

from .src.app.schema import Trackpoint
from .src.app import paths
from .src.app.constants import C
from .mpeg_jpeg_zip import convert_frame_to_jpeg,add_jpeg_comment,get_frames_from_url


logging.basicConfig(format=C.LOGGING_CONFIG, level=C.LOGGING_LEVEL)
logger = logging.getLogger(__name__)
# Legacy: only used by cleanup_mp4, rotate_movie, prepare_movie_for_tracking. run_tracking uses cv2 only.
FFMPEG_PATH = paths.ffmpeg_path()
POINT_ARRAY_OUT = 'point_array_out'
RED = (0, 0, 255)
BLACK = (0, 0, 0)
TEXT_FACE = cv2.FONT_HERSHEY_DUPLEX
TEXT_SCALE = 0.75
TEXT_THICKNESS = 2
TEXT_MARGIN = 5
CIRCLE_WIDTH = 6
CIRCLE_COLOR = RED
MIN_MOVIE_BYTES = 10

## JPEG support

class TrackerCallbackArg(NamedTuple):
    frame_number:int
    frame_data:np.ndarray
    frame_trackpoints:List[Trackpoint] | None


def cv2_track_frame(*, gray_frame_prev:np.ndarray, gray_frame:np.ndarray, trackpoints:List[Trackpoint], frame_number:int):
    """
    Summary - Takes the original marked marked_frame and new frame and returns a frame that is annotated.
    :param: frame_prev - cv2 image of the previous frame in CV2 format.
    :param: frame_this - cv2 image of the current frame in CV2 format
    :param: trackpoints  - array of Trackpoint objects
    :return: array of trackpoints

    Note: frames must be grayscale converted with:
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    """
    winSize = (15, 15)  # pylint: disable=invalid-name
    max_level = 2
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
    cv2_tpts = np.array([[pt.x, pt.y] for pt in trackpoints], dtype=np.float32)

    try:
        point_array_out, status_array, _err = cv2.calcOpticalFlowPyrLK(
            gray_frame_prev, gray_frame, cv2_tpts, None,
            winSize=winSize, maxLevel=max_level, criteria=criteria
        )
        trackpoints_out = []
        for (i, pt) in enumerate(trackpoints):
            if status_array[i] == 1:
                trackpoints_out.append(Trackpoint(x=point_array_out[i][0],
                                                  y=point_array_out[i][1],
                                                  label=pt.label,
                                                  frame_number = frame_number ))
    except cv2.error as e:  # pylint: disable=catching-non-exception
        logger.error("Optical flow failed: %s",e)
        # Don't return empty! Return the previous trackpoints but update their frame_number
        trackpoints_out = [ Trackpoint(x=pt.x, y=pt.y, label=pt.label, frame_number=frame_number) for pt in trackpoints ]
    logger.info("cv2_track_frame output_trackpoints=%s", trackpoints_out)
    return trackpoints_out


def cv2_label_frame(*, frame:np.ndarray, trackpoints:List[Trackpoint], frame_label=None):
    """
    :param: frame - cv2 frame
    :param: trackpoints - array of dicts where each dict has at least an ['x'] and a ['y']
    :param frame_label - if present, label for frame number (can be int or string)
    """

    # frame_height = len(frame)
    frame_width = len(frame[0])

    # use the points to annotate the colored frames. write to colored tracked video
    # https://stackoverflow.com/questions/55904418/draw-text-inside-circle-opencv
    for pt in trackpoints:
        cv2.circle(frame, (int(pt.x), int(pt.y)), CIRCLE_WIDTH, CIRCLE_COLOR, -1)     # pylint: disable=no-member

    if frame_label is not None:
        # Label in upper right hand corner
        text = str(frame_label)
        WHITE = (255, 255, 255)  # pylint: disable=invalid-name
        text_size, _ = cv2.getTextSize(text, TEXT_FACE, TEXT_SCALE, TEXT_THICKNESS)
        text_origin = (frame_width - text_size[0] - TEXT_MARGIN, text_size[1] + TEXT_MARGIN)
        cv2.rectangle(frame, text_origin, (text_origin[0] + text_size[0], text_origin[1] - text_size[1]), RED, -1)
        cv2.putText(frame, text, text_origin, TEXT_FACE, TEXT_SCALE, WHITE, TEXT_THICKNESS, cv2.LINE_4)


def prototype_callback(obj:TrackerCallbackArg):
    """Demo"""
    logging.debug("frame_number=%s len(frame_data)=%s frame_trackpoints=%s", obj.frame_number, len(obj.frame_data), obj.frame_trackpoints)

def track_movie_v2(*, movie_url,
                   frame_start:int,
                   trackpoints:List[Trackpoint],
                   movie_zipfile_path:Optional[Path] = None,
                   movie_traced_path:Optional[Path] = None,
                   rotation=0,
                   callback = prototype_callback,
                   comment="Processed by PlantTracer AWS Lambda"):
    """
    Track from frame_start to end of movie.
    If frame_start==0, the movie is untracked. frame_start is set to 1.

    :param movie_url: filename or URL of an MPEG4
    :param frame_start: first frame to track.
    :param trackpoints: a trackpoints data structure. Trackpoints for frame_start-1 must be provided.
    :param movie_zipfile_path: If provided, where the movie_zipfile of scaled, rotated images goes.
    :param rotation: the rotation (in degrees) to apply to the movie before scaling
    """

    # track from frame frame_start+1 to end using data from frame_start

    if frame_start==0:
        frame_start=1

    # if the movie_url is a file, make sure it exists
    if not str(movie_url).startswith("http"):
        if not Path(movie_url).exists():
            raise FileNotFoundError(movie_url)

    trackpoints_output = [tp for tp in trackpoints if tp.frame_number <= frame_start]
    # make sure we have trackpoints for frame_start-1
    if not any((tp for tp in trackpoints if tp.frame_number == frame_start-1)):
        raise ValueError(f"len(trackpoints)={len(trackpoints)} but no tracked points for frame {frame_start-1}")

    # Check to see if we are making a movie_zipfile
    zf = None
    if movie_zipfile_path is not None:
        # pylint: disable=consider-using-with
        zf = zipfile.ZipFile(movie_zipfile_path, mode='w', compression=zipfile.ZIP_DEFLATED, compresslevel=9)

    # Check to see if we are making a movie_traced
    movie_traced_writer = None
    if movie_traced_path is not None:
        movie_traced_writer = imageio.get_writer(movie_traced_path, format='FFMPEG', mode='I',
                                                  fps=15, codec='libx264',
                                                  macro_block_size=None,
                                                  output_params=['-metadata', f'comment={comment}'])
    trackpoints_prev = None
    gray_frame_prev = None
    trackpoints_this = None
    for (frame_number, frame) in enumerate(get_frames_from_url(movie_url, rotation)):
        # Track if in tracking time, else get trackpoints_this from the history
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if frame_number >= frame_start:
            trackpoints_this = cv2_track_frame(gray_frame_prev = gray_frame_prev, gray_frame = gray_frame, trackpoints = trackpoints_prev, frame_number=frame_number)
            trackpoints_output.extend(trackpoints_this) # add to the output
        else:
            trackpoints_this = [tp for tp in trackpoints if tp.frame_number == frame_number]

        # Create the movie_zipfile if asked
        if zf is not None:
            jpeg = convert_frame_to_jpeg(frame)
            if comment is not None:
                jpeg = add_jpeg_comment(jpeg, comment)
            zf.writestr(f"frame_{frame_number:04d}.jpeg", jpeg)

        # Label the frame and write to the mp4 output if we are doing that
        if movie_traced_writer:
            frame_to_label = frame.copy()
            cv2_label_frame(frame=frame_to_label, trackpoints=trackpoints_this,frame_label=frame_number)
            # IMPORTANT: OpenCV uses BGR colors, but ImageIO expects RGB!
            frame_rgb = cv2.cvtColor(frame_to_label, cv2.COLOR_BGR2RGB)
            movie_traced_writer.append_data(frame_rgb)

        if callback is not None:
            callback(TrackerCallbackArg(frame_number=frame_number, frame_data=frame, frame_trackpoints=trackpoints_this))

        # Advance
        trackpoints_prev = trackpoints_this
        gray_frame_prev = gray_frame
    # Done
    if movie_traced_writer:
        movie_traced_writer.close()
    return trackpoints_output


if __name__ == "__main__":
    # the only requirement for calling track_movie() would be the "control points" and the movie
    parser = argparse.ArgumentParser(
        description="Run Track movie with specified movies and initial points",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--moviefile", default='tests/data/2019-07-12 circumnutation.mp4', help='mpeg4 file')
    parser.add_argument(
        "--points_to_track", default='[{"x":276,"y":172,"label":"mypoint"}]',
        help="list of points to track as json 2D array.")
    parser.add_argument('--outfile', default='tracked_output.mp4')
    args = parser.parse_args()

    # Get the trackpoints
    tpts = json.loads(args.points_to_track)
    # Make sure every trackpoint is for frame 0
    ipts = [Trackpoint(**{**tp, **{'frame_number': 0}}) for tp in tpts]

    # Get the new trackpoints
    track_movie_v2(movie_url=Path(args.moviefile),
                   trackpoints=ipts,
                   frame_start=0,
                   movie_traced_path='traced.mp4')
    subprocess.call(['open', 'traced.mp4'])
