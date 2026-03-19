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
optional/local use (e.g. CLI render_tracked_movie, tests). run_tracking always uses
prepare_movie_for_tracking_cv2 (rotate_zip) for rotate+scale.
"""

# pylint: disable=no-member
import json
import argparse
import tempfile
import subprocess
import logging
import os
import zipfile
from collections import defaultdict

import cv2
import os
import cv2
import numpy as np

from . import mpeg_jpeg_zip

from .src.app import paths
from .src.app import mp4_metadata_lib
from .src.app.constants import C
from .src.app.odb import (
    DDBO,
    LAST_FRAME_TRACKED,
    MOVIE_DATA_URN,
    MOVIE_ZIPFILE_URN,
    PROCESSING_STATE,
    PROCESSING_STATE_TRACKED,
    STATUS,
)
from .src.app.odb import get_movie_metadata, get_movie_trackpoints, put_frame_trackpoints
from .src.app.odb_movie_data import (
    copy_object_to_path,
    course_id_for_movie_id,
    make_object_name,
    make_urn,
    write_object,
    write_object_from_path,
)
from . import rotate_zip

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
MIN_MOVIE_BYTES = 10

## JPEG support


def cv2_track_frame(*, frame_prev, frame_this, trackpoints):
    """
    Summary - Takes the original marked marked_frame and new frame and returns a frame that is annotated.
    :param: frame0 - cv2 image of the previous frame in CV2 format
    :param: frame1 - cv2 image of the current frame in CV2 format
    :param: trackpoints  - array of trackpoints (dicts of x,y and label)
    :return: array of trackpoints

    """
    winSize = (15, 15)  # pylint: disable=invalid-name
    max_level = 2
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
    cv2_tpts = np.array([[pt['x'], pt['y']] for pt in trackpoints], dtype=np.float32)

    try:
        gray_frame0 = cv2.cvtColor(frame_prev, cv2.COLOR_BGR2GRAY)
        gray_frame1 = cv2.cvtColor(frame_this, cv2.COLOR_BGR2GRAY)
        point_array_out, status_array, err = cv2.calcOpticalFlowPyrLK(
            gray_frame0, gray_frame1, cv2_tpts, None,
            winSize=winSize, maxLevel=max_level, criteria=criteria
        )
        trackpoints_out = []
        for (i, pt) in enumerate(trackpoints):
            if status_array[i] == 1:
                trackpoints_out.append({
                    'x': point_array_out[i][0],
                    'y': point_array_out[i][1],
                    'status': int(status_array[i][0]),
                    'err': float(err[i][0]),
                    'label': pt['label']
                })
    except cv2.error:  # pylint: disable=catching-non-exception
        trackpoints_out = []

    logger.info("cv2_track_frame output_trackpoints=%s", trackpoints_out)
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
        cv2.circle(frame, (int(point['x']), int(point['y'])), 3, RED, -1)     # pylint: disable=no-member

    if frame_label is not None:
        # Label in upper right hand corner
        text = str(frame_label)
        WHITE = (255, 255, 255)  # pylint: disable=invalid-name
        text_size, _ = cv2.getTextSize(text, TEXT_FACE, TEXT_SCALE, TEXT_THICKNESS)
        text_origin = (frame_width - text_size[0] - TEXT_MARGIN, text_size[1] + TEXT_MARGIN)
        cv2.rectangle(frame, text_origin, (text_origin[0] + text_size[0], text_origin[1] - text_size[1]), RED, -1)
        cv2.putText(frame, text, text_origin, TEXT_FACE, TEXT_SCALE, WHITE, TEXT_THICKNESS, cv2.LINE_4)


def cleanup_mp4(*, infile: str, outfile: str):
    """Transcode video to H.264 MP4 using pure OpenCV (no external binary)."""
    if not os.path.exists(infile):
        raise FileNotFoundError(infile)

    # 1. Open the input video
    cap = cv2.VideoCapture(infile)
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV could not open input video: {infile}")

    # 2. Grab video properties
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # 3. Initialize the VideoWriter
    # 'avc1' is the FourCC code for H.264 encoding.
    fourcc = cv2.VideoWriter_fourcc(*'avc1')

    out = cv2.VideoWriter(outfile, fourcc, fps, (width, height))

    if not out.isOpened():
        cap.release()
        raise RuntimeError(
            f"OpenCV failed to initialize the VideoWriter for {outfile}. "
            "Your OpenCV build might lack H.264 support."
        )

    # 4. Read and write frame-by-frame
    while True:
        ret, frame = cap.read()
        if not ret:
            break  # End of video stream
        out.write(frame)

    # 5. Clean up
    cap.release()
    out.release()


# pylint: disable=too-many-locals
def render_tracked_movie(*, moviefile_input, moviefile_output, movie_trackpoints, label_frames=True):
    """LEGACY: Renders tracked video with dots; uses ffmpeg for final transcode. Not used in web/Lambda flow."""
    # Create a VideoWriter object to save the output video to a temporary file (which we will then transcode with ffmpeg)
    # movie_trackpoints is an array of records where each has the form:
    # {'x': 152.94203, 'y': 76.80803, 'status': 1, 'err': 0.08736111223697662, 'label': 'mypoint', 'frame_number': 189}

    cap = cv2.VideoCapture(moviefile_input)
    ret, current_frame_data = cap.read()
    # Get video properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

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


def prototype_callback(*, frame_number, frame_data, frame_trackpoints):
    logging.debug("frame_number=%s len(frame_data)=%s frame_trackpoints=%s", frame_number, len(frame_data), frame_trackpoints)


def track_movie(
    *,
    moviefile_input,
    input_trackpoints,
    frame_start=0,
    label_frames=False,
    callback=prototype_callback,
    max_frame=None ):
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
    logger.info("track_movie moviefile_input=%s frame_start=%s",moviefile_input, frame_start)
    cap = cv2.VideoCapture(moviefile_input)
    frame_this = None

    # should be movie name + tracked

    # Create a VideoWriter object to save the output video to a temporary file (which we will then transcode with ffmpeg)
    logging.info("start movie tracking")
    for frame_number in range(1_000_000):
        logger.info("frame_number=%s",frame_number)
        if max_frame is not None and frame_number > max_frame:
            break
        frame_prev = frame_this
        success, frame_this = cap.read()
        if not success:
            break

        # Copy over the trackpoints for the current frame if this was previously tracked or is the first frame to track
        # This also copies over frame_prev at start (when frame_number=0 and frame_start=0, it is <= frame_start)
        frame_show = frame_this  # frame to show
        if frame_number <= frame_start:
            current_trackpoints = [tp for tp in input_trackpoints if tp['frame_number'] == frame_number]
            if frame_number == 0:
                logger.info(
                    "frame 0: using input_trackpoints from DB: total=%d for frame 0=%d",
                    len(input_trackpoints),
                    len(current_trackpoints),
                )
            # Call the callback if we have one
            if label_frames:
                frame_show = frame_this.copy()
                cv2_label_frame(frame=frame_show, trackpoints=current_trackpoints, frame_label=frame_number)
            callback(frame_number=frame_number, frame_data=frame_show, frame_trackpoints=current_trackpoints)
            continue

        # If this is after the starting frame, then track it
        # This is run every time through the loop except the first time.
        assert frame_prev is not None
        trackpoints_by_label = {tp['label']: tp for tp in current_trackpoints}
        new_trackpoints = cv2_track_frame(frame_prev=frame_prev, frame_this=frame_this, trackpoints=current_trackpoints)

        # Copy in updated trackpoints
        for tp in new_trackpoints:
            trackpoints_by_label[tp['label']] = tp

        # create new list of trackpoints
        current_trackpoints = list(trackpoints_by_label.values())
        # And set their new frame numbers
        for tp in current_trackpoints:
            tp['frame_number'] = frame_number  # set the frame number

        # Call the callback if we have one
        logger.info("frame_number=%s current_trackpoints=%s",frame_number,current_trackpoints)
        if callback is not None:
            if label_frames:
                frame_show = frame_this.copy()
                cv2_label_frame(frame=frame_show, trackpoints=[], frame_label=frame_number)
            callback(frame_number=frame_number, frame_data=frame_show, frame_trackpoints=current_trackpoints)

    cap.release()


def rotate_movie(movie_input, movie_output, transpose=1):
    """LEGACY: Rotate video with ffmpeg. Use rotate_zip.rotate_video_av for cv2-only."""
    if not FFMPEG_PATH or not os.path.exists(FFMPEG_PATH):
        raise RuntimeError("ffmpeg required for rotate_movie (not available in this environment)")
    assert os.path.getsize(movie_input) > MIN_MOVIE_BYTES
    assert os.path.getsize(movie_output) == 0
    subprocess.call([FFMPEG_PATH, '-hide_banner', '-loglevel', 'error',
                     '-i', movie_input, '-vf', f'transpose={int(transpose)}', '-c:a', 'copy', '-y', movie_output])
    assert os.path.getsize(movie_output) > MIN_MOVIE_BYTES


def prepare_movie_for_tracking(
    input_path: str,
    output_path: str,
    rotation_steps: int,
    max_width: int,
    max_height: int,
) -> None:
    """LEGACY: Rotate and/or scale with ffmpeg. Production uses rotate_zip.prepare_movie_for_tracking_cv2."""
    if not FFMPEG_PATH or not os.path.exists(FFMPEG_PATH):
        raise RuntimeError("ffmpeg required for prepare_movie_for_tracking (not available in this environment)")
    if rotation_steps < 0 or rotation_steps > 3:
        raise ValueError("rotation_steps must be 0–3")
    if os.path.getsize(input_path) <= MIN_MOVIE_BYTES:
        raise ValueError("input movie too small")
    with open(output_path, "wb"):
        pass
    vf_parts = []
    if rotation_steps == 1:
        vf_parts.append("transpose=1")
    elif rotation_steps == 2:
        vf_parts.append("transpose=2,transpose=2")
    elif rotation_steps == 3:
        vf_parts.append("transpose=2")
    # Fit inside (max_width, max_height) preserving aspect (ffmpeg scale filter)
    vf_parts.append(f"scale={max_width}:{max_height}:force_original_aspect_ratio=decrease")
    vf = ",".join(vf_parts)
    rc = subprocess.call(
        [
            FFMPEG_PATH,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            input_path,
            "-vf",
            vf,
            "-c:a",
            "copy",
            "-y",
            output_path,
        ]
    )
    if rc != 0 or os.path.getsize(output_path) <= MIN_MOVIE_BYTES:
        raise RuntimeError("prepare_movie_for_tracking failed")


# pylint: disable=too-many-instance-attributes
class TrackingCallback:
    """Callback used during track_movie that writes frames to a zip and persists tracking data.

    The zip is always rebuilt into a fresh temporary archive. When tracking continues
    from a later frame, the caller can supply the prior zip bytes so we copy those
    frames into the new archive before appending the current batch.
    """

    def __init__(
        self,
        *,
        ddbo,
        user_id,
        movie_id,
        research_comment: str,
        total_frames: int,
        existing_zip_path=None,
    ):
        self.ddbo = ddbo
        self.user_id = user_id
        self.movie_id = movie_id
        self.research_comment = research_comment or ""
        self.total_frames = total_frames
        self.last_frame_tracked = -1
        with tempfile.NamedTemporaryFile(  # pylint: disable=consider-using-with
            suffix=".zip", prefix=f"movie_{movie_id}", delete=False
        ) as tmp:
            self._zip_tf = tmp
            self._zipfile = zipfile.ZipFile(  # pylint: disable=consider-using-with
                self._zip_tf.name, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            )
        if existing_zip_path:
            with zipfile.ZipFile(existing_zip_path, mode="r") as old_zip:
                for info in old_zip.infolist():
                    self._zipfile.writestr(info, old_zip.read(info.filename))
            os.unlink(existing_zip_path)

    def notify(self, *, frame_number, frame_data, frame_trackpoints):
        frame_jpeg = convert_frame_to_jpeg(frame_data, quality=60)
        if self.research_comment:
            frame_jpeg = mp4_metadata_lib.add_comment_to_jpeg(
                frame_jpeg, self.research_comment, quality=60
            )
        self.last_frame_tracked = max(self.last_frame_tracked, frame_number)
        self._zipfile.writestr(f"frame_{frame_number:04}.jpg", frame_jpeg)
        put_frame_trackpoints(movie_id=self.movie_id, frame_number=frame_number, trackpoints=frame_trackpoints)
        message = f"Tracked frames {frame_number + 1} of {self.total_frames}"
        self.ddbo.update_table(self.ddbo.movies, self.movie_id, {STATUS: message})

    def close(self):
        self._zipfile.close()

    @property
    def zipfile_data(self):
        with open(self._zip_tf.name, "rb") as f:
            return f.read()

    def done(self):
        self.ddbo.update_table(self.ddbo.movies, self.movie_id, {STATUS: C.TRACKING_COMPLETED})
        self.ddbo.update_table(self.ddbo.movies, self.movie_id, {PROCESSING_STATE: PROCESSING_STATE_TRACKED})
        if os.path.exists(self._zip_tf.name):
            os.unlink(self._zip_tf.name)


if __name__ == "__main__":
    # the only requirement for calling track_movie() would be the "control points" and the movie
    parser = argparse.ArgumentParser(
        description="Run Track movie with specified movies and initial points",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--moviefile", default='tests/data/2019-07-12 circumnutation.mp4', help='mpeg4 file')
    parser.add_argument(
        "--points_to_track", default='[{"x":138,"y":86,"label":"mypoint"}]',
        help="list of points to track as json 2D array.")
    parser.add_argument('--outfile', default='tracked_output.mp4')
    args = parser.parse_args()

    # Get the trackpoints
    tpts = json.loads(args.points_to_track)
    # Make sure every trackpoint is for frame 0
    ipts = [{**tp, **{'frame_number': 0}} for tp in tpts]

    # Get the new trackpoints
    tpts = []
    def cb2(*, frame_number, frame_data, frame_trackpoints):
        del frame_number, frame_data  # unused in this CLI helper
        tpts.extend(frame_trackpoints)

    track_movie(moviefile_input=args.moviefile,
                input_trackpoints=ipts,
                callback=cb2)
    # Now render the movie
    render_tracked_movie(moviefile_input=args.moviefile, moviefile_output='tracked.mp4',
                        movie_trackpoints=tpts)
    subprocess.call(['open', 'tracked.mp4'])
