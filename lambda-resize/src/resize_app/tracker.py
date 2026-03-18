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
import numpy as np

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


class ConversionError(RuntimeError):
    """Special error"""


class MovieCorruptError(RuntimeError):
    """Special error"""


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

    logger.info("output_trackpoints=%s",trackpoints)
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
        cv2.circle(frame, (int(point['x']), int(point['y'])), 3, RED, -1)  # pylint: disable=no-member

    if frame_label is not None:
        # Label in upper right hand corner
        text = str(frame_label)
        WHITE = (255, 255, 255)  # pylint: disable=invalid-name
        text_size, _ = cv2.getTextSize(text, TEXT_FACE, TEXT_SCALE, TEXT_THICKNESS)
        text_origin = (frame_width - text_size[0] - TEXT_MARGIN, text_size[1] + TEXT_MARGIN)
        cv2.rectangle(frame, text_origin, (text_origin[0] + text_size[0], text_origin[1] - text_size[1]), RED, -1)
        cv2.putText(frame, text, text_origin, TEXT_FACE, TEXT_SCALE, WHITE, TEXT_THICKNESS, cv2.LINE_4)


def extract_movie_metadata(*, movie_path):
    """Use OpenCV to get movie metadata from a local file path.
    Width, height, fps and usually frame count come from container/stream metadata.
    Only if frame count is missing do we fall back to counting frames."""
    cap = cv2.VideoCapture(movie_path)
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if frame_count is not None and frame_count > 0:
            total_frames = int(frame_count)
        else:
            total_frames = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if len(frame) == 0:
                    raise MovieCorruptError()
                total_frames += 1
    finally:
        cap.release()
    return {
        'total_frames': total_frames,
        'total_bytes': os.path.getsize(movie_path),
        'width': width,
        'height': height,
        'fps': fps,
    }


def convert_frame_to_jpeg(img, quality=90):
    """Use CV2 to convert a frame to a jpeg"""
    _, jpg_img = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return jpg_img.tobytes()


def get_jpeg_dimensions(jpeg_bytes):
    """Return (width, height) of a JPEG image, or None if decode fails."""
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    return (w, h)


def resize_jpeg_to_fit(jpeg_bytes, max_width, max_height, quality=90):
    """Resize JPEG bytes to fit inside (max_width, max_height), preserving aspect. Returns JPEG bytes."""
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jpeg_bytes
    h, w = img.shape[:2]
    if w <= max_width and h <= max_height:
        return jpeg_bytes
    scale = min(max_width / w, max_height / h)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    _, jpg_img = cv2.imencode('.jpg', resized, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return jpg_img.tobytes()


def extract_frame(*, movie_data, frame_number, fmt):
    """Extract a single frame from movie data using CV2. This is not an efficient approach to read the entire movie.
    Perhaps  make frame_number an array of frames to allow multiple frames to be extracted, with a callback?
    :param: movie_data - binary object of data
    :param: frame_number - frame to extract
    :param: fmt - format wanted. CV2-return a CV2 image; 'jpeg' - return a jpeg image as a byte array.
    """
    assert fmt in ['CV2', 'jpeg']
    assert movie_data is not None
    # CV2's VideoCapture method does not support reading from a memory buffer.
    # So perhaps we will change this to use a named pipe
    with tempfile.NamedTemporaryFile(mode='ab') as tf:
        tf.write(movie_data)
        tf.flush()
        cap = cv2.VideoCapture(tf.name)

    # skip to frame_number (first frame is #0)
    for _ in range(frame_number + 1):
        ret, frame = cap.read()
        if not ret:
            raise ValueError(f"invalid frame_number {frame_number}")
        match fmt:
            case 'CV2':
                return frame
            case 'jpeg':
                return convert_frame_to_jpeg(frame)
            case _:
                raise ValueError("Invalid fmt: " + fmt)
    raise ValueError(f"invalid frame_number {frame_number}")


def cleanup_mp4(*, infile, outfile):
    """LEGACY: Transcode to h264 with ffmpeg. Requires ffmpeg binary. Used only by render_tracked_movie."""
    if not FFMPEG_PATH or not os.path.exists(FFMPEG_PATH):
        raise RuntimeError("ffmpeg required for cleanup_mp4 (not available in this environment)")
    if not os.path.exists(infile):
        raise FileNotFoundError(infile)

    cargs = ['-y', '-hide_banner', '-loglevel', 'error', '-i', infile, '-vcodec', 'h264', outfile]
    subprocess.call([FFMPEG_PATH] + cargs)


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
        result, frame_this = cap.read()
        if not result:
            break

        # Copy over the trackpoints for the current frame if this was previously tracked or is the first frame to track
        # This also copies over frame_prev at start (when frame_number=0 and frame_start=0, it is <= frame_start)
        frame_show = frame_this  # frame to show
        if frame_number <= frame_start:
            current_trackpoints = [tp for tp in input_trackpoints if tp['frame_number'] == frame_number]
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

def run_tracking(*, user_id, movie_id, frame_start, max_frame=None):
    """Run full tracking pipeline using module-level Lambda helpers."""
    input_trackpoints = get_movie_trackpoints(movie_id=movie_id)
    movie_record = get_movie_metadata(movie_id=movie_id)
    research_comment = mp4_metadata_lib.build_comment(
        movie_record.get("research_use", 0) or 0,
        movie_record.get("credit_by_name", 0) or 0,
        movie_record.get("attribution_name"),
    )

    if not input_trackpoints:
        raise RuntimeError("Cannot track movie with no trackpoints")

    logger.info("run_tracking user_id=%s movie_id=%s frame_start=%s input_trackpoints=%s",user_id,movie_id,frame_start,input_trackpoints)
    # Derive true movie dimensions from the file so shrink/rotate decisions are
    # based on the real stream size, not any analysis/display size that may have
    # been written into DB width/height by get-frame(size=analysis).
    movie_urn = movie_record.get(MOVIE_DATA_URN)
    if not movie_urn:
        raise RuntimeError(f"movie {movie_id} has no movie data URN")
    movie_path = None
    extracted = None
    with tempfile.NamedTemporaryFile(suffix=".mp4", mode="wb", delete=False) as movie_tf:
        movie_path = movie_tf.name
    copy_object_to_path(urn=movie_urn, path=movie_path)
    extracted = extract_movie_metadata(movie_path=movie_path)
    movie_metadata = {
        "width": extracted.get("width"),
        "height": extracted.get("height"),
        "total_frames": extracted.get("total_frames"),
        "total_bytes": extracted.get("total_bytes"),
        "fps": extracted.get("fps"),
    }
    # Persist missing metadata back to the movie record for later callers.
    to_set = {}
    for key in ("width", "height", "total_frames", "total_bytes", "fps"):
        if movie_record.get(key) is None and movie_metadata.get(key) is not None:
            to_set[key] = movie_metadata[key]
    if to_set.get("fps") is not None and not isinstance(to_set["fps"], str):
        to_set["fps"] = str(to_set["fps"])
        movie_metadata["fps"] = to_set["fps"]
    ddbo = DDBO()
    if to_set:
        ddbo.update_table(ddbo.movies, movie_id, to_set)

    existing_zip_path = None
    if frame_start > 0:
        zip_urn = movie_record.get(MOVIE_ZIPFILE_URN)
        if not zip_urn:
            raise RuntimeError(
                f"Cannot continue tracking from frame {frame_start} without an existing zipfile URN"
            )
        with tempfile.NamedTemporaryFile(suffix=".zip", mode="wb", delete=False) as existing_zip_tf:
            existing_zip_path = existing_zip_tf.name
        copy_object_to_path(urn=zip_urn, path=existing_zip_path)

    rotation_steps = int(movie_record.get("rotation_steps") or 0)
    rotation_steps = max(0, min(3, rotation_steps))
    w = movie_metadata.get("width") or 0
    h = movie_metadata.get("height") or 0
    need_process = (
        rotation_steps > 0
        or w > C.ANALYSIS_FRAME_MAX_WIDTH
        or h > C.ANALYSIS_FRAME_MAX_HEIGHT
    )

    in_path = movie_path
    out_path = None
    moviefile_input = None
    try:
        if need_process:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as out_tf:
                out_path = out_tf.name
            rotate_zip.prepare_movie_for_tracking_cv2(
                in_path,
                out_path,
                rotation_steps,
                C.ANALYSIS_FRAME_MAX_WIDTH,
                C.ANALYSIS_FRAME_MAX_HEIGHT,
            )
            mp4_metadata_lib.set_comment(out_path, research_comment)
            processed_oname = make_object_name(
                course_id=course_id_for_movie_id(movie_id),
                movie_id=movie_id,
                ext=C.MOVIE_PROCESSED_EXTENSION,
            )
            processed_urn = make_urn(object_name=processed_oname)
            write_object_from_path(urn=processed_urn, path=out_path)
            ddbo.update_table(ddbo.movies, movie_id, {MOVIE_DATA_URN: processed_urn})
            moviefile_input = out_path
        else:
            moviefile_input = in_path

        total_frames = movie_metadata.get("total_frames") or 0
        callback = TrackingCallback(
            ddbo=ddbo,
            user_id=user_id,
            movie_id=movie_id,
            research_comment=research_comment,
            total_frames=total_frames,
            existing_zip_path=existing_zip_path,
        )
        # If max_frame is provided, clamp it to a hard safety cap of 9999 and, if
        # we know total_frames, to the last real frame.
        effective_max = None
        if max_frame is not None:
            hard_cap = 9999
            if total_frames:
                hard_cap = min(hard_cap, int(total_frames) - 1)
            effective_max = min(int(max_frame), hard_cap)

        track_movie(
            input_trackpoints=input_trackpoints,
            frame_start=frame_start,
            moviefile_input=moviefile_input,
            callback=callback.notify,
            max_frame=effective_max,
        )
        callback.close()
        ddbo.update_table(ddbo.movies, movie_id, {LAST_FRAME_TRACKED: callback.last_frame_tracked})
        zip_oname = make_object_name(
            course_id=course_id_for_movie_id(movie_id),
            movie_id=movie_id,
            ext=C.ZIP_MOVIE_EXTENSION,
        )
        zip_urn = make_urn(object_name=zip_oname)
        write_object(urn=zip_urn, object_data=callback.zipfile_data)
        ddbo.update_table(ddbo.movies, movie_id, {MOVIE_ZIPFILE_URN: zip_urn})
        callback.done()
    finally:
        if in_path and os.path.exists(in_path):
            os.unlink(in_path)
        if out_path and os.path.exists(out_path):
            os.unlink(out_path)


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
