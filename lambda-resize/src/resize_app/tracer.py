"""
Implements blockmatching algorithm in OpenCV.
Includes all code for getting the entire movie (get_movie_data) and getting individual
frames (extract_frame, get_jpeg_dimensions, resize_jpeg_to_fit).
Shared entry point run_tracing(...) uses module-level Lambda helpers directly.
Frame serving (get-frame API) runs in this Lambda (resize); the VM uses this module only for
run_tracing and for api_get_movie_data (full movie download).
Lives in lambda-resize.

OpenCV decodes, transforms, annotates, and traces frames. The traced H.264 derivative is
encoded with the libx264 executable bundled by imageio-ffmpeg because the OpenCV wheel's
embedded FFmpeg libraries do not include a software H.264 encoder.

"""

# pylint: disable=no-member
from typing import List,Optional,NamedTuple
import hashlib
import json
import argparse
import subprocess
import logging
import re
from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .src.app.schema import Trackpoint
from .src.app.constants import C
from .mpeg_jpeg_zip import get_frames_from_url
from .analysis_mp4 import AnalysisMp4Options, unlabelled_analysis_frames
from .video_writer import H264Writer

logging.basicConfig(format=C.LOGGING_CONFIG, level=C.LOGGING_LEVEL)
logger = logging.getLogger(__name__)
POINT_ARRAY_OUT = 'point_array_out'
RED = (0, 0, 255)
ORANGE = (0, 165, 255)
MAGENTA = (255, 0, 255)
MUSTARD = (0, 137, 181)
BRIGHT_BLUE = (255, 150, 0)
BLACK = (0, 0, 0)
TEXT_FACE = cv2.FONT_HERSHEY_DUPLEX
TEXT_SCALE = 0.75
TEXT_THICKNESS = 2
TEXT_MARGIN = 5
CIRCLE_WIDTH = 6
CIRCLE_COLOR = RED
LINE_WIDTH = 2
FIXED_PLANT_MARKER_COLORS = [MAGENTA, MUSTARD, BRIGHT_BLUE]
CSS_COLORS_BGR = {
    "red": RED,
    "orange": ORANGE,
    "magenta": MAGENTA,
}
MIN_MOVIE_BYTES = 10
RULER_LABEL_RE = re.compile(r"^Ruler\s*\d+mm$")

## JPEG support

class TracerCallbackArg(NamedTuple):
    frame_number:int
    frame_data:np.ndarray
    frame_trackpoints:List[Trackpoint] | None


class TrackpointSegment(NamedTuple):
    label:str
    x1:float
    y1:float
    x2:float
    y2:float


class TracedMovieFrameRange(BaseModel):
    """Export bounds and optional capture interval, independent of playback FPS."""
    start:int = 0
    end:int | None = None
    seconds_per_frame: float | None = Field(default=None, gt=0)


class TracePathOverlay(BaseModel):
    """Cache thin paths once; opaque past segments subsequently cover them."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    colors: np.ndarray
    mask: np.ndarray

    def draw(self, frame):
        """Blend only path pixels, leaving source pixels unchanged elsewhere."""
        blended = cv2.addWeighted(frame, 0.5, self.colors, 0.5, 0)
        frame[self.mask != 0] = blended[self.mask != 0]


def trace_path_overlay(frame, points_by_frame, first, last, colors_by_label):
    """Rasterize complete paths inside the trim without connecting missing frames."""
    overlay = TracePathOverlay(colors=np.zeros_like(frame), mask=np.zeros(frame.shape[:2], dtype=np.uint8))
    for number in sorted(points_by_frame):
        if number <= first or (last is not None and number > last):
            continue
        segments = []
        update_trackpoint_segments(previous_trackpoints=points_by_frame.get(number - 1),
                                   current_trackpoints=points_by_frame[number], segments=segments)
        for segment in segments:
            start, end = (int(segment.x1), int(segment.y1)), (int(segment.x2), int(segment.y2))
            cv2.line(overlay.colors, start, end, colors_by_label.get(segment.label, CIRCLE_COLOR), 1)
            cv2.line(overlay.mask, start, end, 255, 1)
    return overlay


def trackpoint_with_updates(trackpoint: Trackpoint, **updates):
    return Trackpoint(**{**trackpoint.model_dump(), **updates})


def preserve_missing_trackpoints(*,
                                 previous_trackpoints:List[Trackpoint],
                                 output_trackpoints:List[Trackpoint],
                                 frame_number:int):
    """Carry unresolved markers forward instead of deleting them from later frames."""
    output_labels = {trackpoint.label for trackpoint in output_trackpoints}
    missing_trackpoints = [
        trackpoint_with_updates(trackpoint, frame_number=frame_number)
        for trackpoint in previous_trackpoints
        if trackpoint.label not in output_labels
    ]
    return output_trackpoints + missing_trackpoints


def graphable_trackpoint_label(label:str):
    return bool(label) and not RULER_LABEL_RE.match(label)


def css_color_to_bgr(color:str | None):
    if not color:
        return None
    normalized = color.strip().lower()
    if normalized in CSS_COLORS_BGR:
        return CSS_COLORS_BGR[normalized]
    if re.match(r"^#[0-9a-f]{6}$", normalized):
        red = int(normalized[1:3], 16)
        green = int(normalized[3:5], 16)
        blue = int(normalized[5:7], 16)
        return (blue, green, red)
    return None


def stable_color_for_label(label:str):
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    red = digest[0]
    green = digest[1]
    blue = digest[2]
    return (blue, green, red)


def trackpoint_colors(trackpoints:List[Trackpoint]):
    """Return BGR colors by label, preferring stored browser marker colors."""
    labels = []
    colors_by_label = {}
    for trackpoint in trackpoints:
        if RULER_LABEL_RE.match(trackpoint.label):
            colors_by_label.setdefault(trackpoint.label, RED)
            continue
        if trackpoint.label == "Apex":
            colors_by_label.setdefault(trackpoint.label, ORANGE)
            continue
        stored_color = css_color_to_bgr(trackpoint.color)
        if stored_color:
            colors_by_label[trackpoint.label] = stored_color
            continue
        if graphable_trackpoint_label(trackpoint.label) and trackpoint.label not in labels:
            labels.append(trackpoint.label)
    for index, label in enumerate(labels):
        colors_by_label[label] = (
            FIXED_PLANT_MARKER_COLORS[index]
            if index < len(FIXED_PLANT_MARKER_COLORS)
            else stable_color_for_label(label)
        )
    return colors_by_label


def update_trackpoint_segments(*,
                               previous_trackpoints:List[Trackpoint] | None,
                               current_trackpoints:List[Trackpoint] | None,
                               segments:List[TrackpointSegment]):
    if not previous_trackpoints or not current_trackpoints:
        return
    current_by_label = {trackpoint.label: trackpoint for trackpoint in current_trackpoints}
    for previous in previous_trackpoints:
        current = current_by_label.get(previous.label)
        if current is not None:
            segments.append(TrackpointSegment(label=previous.label,
                                              x1=previous.x,
                                              y1=previous.y,
                                              x2=current.x,
                                              y2=current.y))


def cv2_trace_frame(*, gray_frame_prev:np.ndarray, gray_frame:np.ndarray, trackpoints:List[Trackpoint], frame_number:int):
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
                trackpoints_out.append(trackpoint_with_updates(pt,
                                                               x=point_array_out[i][0],
                                                               y=point_array_out[i][1],
                                                               frame_number=frame_number))
        trackpoints_out = preserve_missing_trackpoints(previous_trackpoints=trackpoints,
                                                       output_trackpoints=trackpoints_out,
                                                       frame_number=frame_number)
    except cv2.error as e:  # pylint: disable=catching-non-exception
        logger.error("Optical flow failed: %s",e)
        # Don't return empty! Return the previous trackpoints but update their frame_number
        trackpoints_out = [trackpoint_with_updates(pt, frame_number=frame_number) for pt in trackpoints]
    logger.info("cv2_trace_frame output_trackpoints=%s", trackpoints_out)
    return trackpoints_out


def cv2_label_frame(*,
                    frame:np.ndarray,
                    trackpoints:List[Trackpoint],
                    frame_label=None,
                    trackpoint_segments:List[TrackpointSegment] | None = None,
                    colors_by_label:dict[str, tuple[int, int, int]] | None = None,
                    path_overlay:TracePathOverlay | None = None):
    """
    :param: frame - cv2 frame
    :param: trackpoints - array of dicts where each dict has at least an ['x'] and a ['y']
    :param frame_label - if present, label for frame number (can be int or string)
    """

    # frame_height = len(frame)
    frame_width = len(frame[0])

    colors_by_label = colors_by_label or {}

    if path_overlay is not None:
        path_overlay.draw(frame)
    # Use the points to annotate the colored frames. Write to colored tracked video.
    for segment in trackpoint_segments or []:
        cv2.line(frame,
                 (int(segment.x1), int(segment.y1)),
                 (int(segment.x2), int(segment.y2)),
                 colors_by_label.get(segment.label, CIRCLE_COLOR),
                 LINE_WIDTH)

    # https://stackoverflow.com/questions/55904418/draw-text-inside-circle-opencv
    for pt in trackpoints:
        if RULER_LABEL_RE.match(pt.label):
            color = RED
        elif pt.label == "Apex":
            color = ORANGE
        else:
            color = colors_by_label.get(pt.label) or css_color_to_bgr(pt.color) or CIRCLE_COLOR
        cv2.circle(frame, (int(pt.x), int(pt.y)), CIRCLE_WIDTH, color, -1)     # pylint: disable=no-member

    if frame_label is not None:
        # Label in upper right hand corner
        text = str(frame_label)
        WHITE = (255, 255, 255)  # pylint: disable=invalid-name
        text_size, _ = cv2.getTextSize(text, TEXT_FACE, TEXT_SCALE, TEXT_THICKNESS)
        text_origin = (frame_width - text_size[0] - TEXT_MARGIN, text_size[1] + TEXT_MARGIN)
        cv2.rectangle(frame, text_origin, (text_origin[0] + text_size[0], text_origin[1] - text_size[1]), (255, 0, 0), -1)
        cv2.putText(frame, text, text_origin, TEXT_FACE, TEXT_SCALE, WHITE, TEXT_THICKNESS, cv2.LINE_4)


def prototype_callback(obj:TracerCallbackArg):
    """Demo"""
    logging.debug("frame_number=%s len(frame_data)=%s frame_trackpoints=%s", obj.frame_number, len(obj.frame_data), obj.frame_trackpoints)

def trace_movie_v2(*, movie_url,  # pylint: disable=too-many-arguments
                   frame_start:int,
                   frame_end:int | None = None,
                   trackpoints:List[Trackpoint],
                   movie_traced_path:Optional[Path] = None,
                   movie_traced_frame_range:TracedMovieFrameRange | None = None,
                   rotation=0,
                   render_source: tuple[str, AnalysisMp4Options] | None = None,
                   render_only: bool = False,
                   render_callback = None,
                   callback = prototype_callback,
                   comment="Processed by PlantTracer AWS Lambda"):
    """
    Trace from frame_start to frame_end, or to the end of movie when frame_end is not provided.
    If frame_start==0, the movie is untracked. frame_start is set to 1.

    :param movie_url: filename or URL of an MPEG4
    :param frame_start: first frame to track.
    :param frame_end: optional inclusive final frame to track.
    :param trackpoints: a trackpoints data structure. Trackpoints for frame_start-1 must be provided.
    :param movie_traced_frame_range: inclusive frame range to include in the traced MP4.
    :param render_source: original URL and shared transform options when movie_url is an untraced MP4.
    :param render_only: draw existing points without tracking or requiring a seed.
    :param render_callback: rendering progress/lease heartbeat, never a trackpoint writer.
    :param rotation: the rotation (in degrees) to apply to the movie before scaling
    """

    seconds_per_frame = movie_traced_frame_range.seconds_per_frame if movie_traced_frame_range else None

    # frame_start is the first computed frame; its predecessor supplies the seed.

    if frame_start==0:
        frame_start=1
    if frame_end is not None:
        frame_end = int(frame_end)
        if frame_end < frame_start - 1:
            raise ValueError(f"frame_end {frame_end} must be at least source frame {frame_start - 1}")
    movie_traced_frame_start = int(movie_traced_frame_range.start) if movie_traced_frame_range else 0
    if movie_traced_frame_start < 0:
        raise ValueError("movie_traced_frame_start must be >= 0")
    movie_traced_frame_end = movie_traced_frame_range.end if movie_traced_frame_range else None
    if movie_traced_frame_end is None:
        movie_traced_frame_end = frame_end
    else:
        movie_traced_frame_end = int(movie_traced_frame_end)
    if movie_traced_frame_end is not None and movie_traced_frame_end < movie_traced_frame_start:
        raise ValueError("movie_traced_frame_end must be >= movie_traced_frame_start")

    # if the movie_url is a file, make sure it exists
    if not str(movie_url).startswith("http"):
        if not Path(movie_url).exists():
            raise FileNotFoundError(movie_url)

    trackpoints_output = list(trackpoints) if render_only else [
        tp for tp in trackpoints if tp.frame_number < frame_start or (frame_end is not None and tp.frame_number > frame_end)]
    points_by_frame = {}
    for point in trackpoints:
        points_by_frame.setdefault(point.frame_number, []).append(point)
    # make sure we have trackpoints for frame_start-1
    if not render_only and not any((tp for tp in trackpoints if tp.frame_number == frame_start-1)):
        raise ValueError(f"len(trackpoints)={len(trackpoints)} but no tracked points for frame {frame_start-1}")

    # Validate before invoking callbacks, then compute future positions before
    # rendering frame zero. Each phase streams frames without retaining the movie.
    if movie_traced_path is not None and not render_only:
        points = trace_movie_v2(movie_url=movie_url, frame_start=frame_start, frame_end=frame_end,
                                trackpoints=trackpoints, rotation=rotation, render_source=render_source,
                                callback=callback)
        trace_movie_v2(movie_url=movie_url, frame_start=frame_start, frame_end=frame_end,
                       trackpoints=points, rotation=rotation, render_source=render_source,
                       movie_traced_path=movie_traced_path, movie_traced_frame_range=movie_traced_frame_range,
                       render_only=True, callback=render_callback, comment=comment)
        return points

    # Check to see if we are making a movie_traced
    movie_traced_writer = None
    if movie_traced_path is not None:
        movie_traced_writer = H264Writer(
            movie_traced_path,
            fps=15,
            output_params=['-metadata', f'comment={comment}'],
        )
    source_frames = (unlabelled_analysis_frames(*render_source) if render_source and render_only
                     else get_frames_from_url(movie_url, rotation, transform=render_source is None))
    trackpoints_prev = None
    gray_frame_prev = None
    trackpoints_this = None
    trackpoint_segments:list[TrackpointSegment] = []
    colors_by_label = trackpoint_colors(trackpoints)
    written_frames = 0
    path_overlay = None
    try:
        for (frame_number, frame) in enumerate(source_frames):
            if render_only and movie_traced_frame_end is not None and frame_number > movie_traced_frame_end:
                break
            # Trace only in the requested range; outside it use existing trackpoints for rendering/callbacks.
            gray_frame = None if render_only else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if not render_only and frame_number >= frame_start and (frame_end is None or frame_number <= frame_end):
                trackpoints_this = cv2_trace_frame(
                    gray_frame_prev = gray_frame_prev,
                    gray_frame = gray_frame,
                    trackpoints = trackpoints_prev,
                    frame_number=frame_number,
                )
                trackpoints_output.extend(trackpoints_this) # add to the output
            else:
                trackpoints_this = points_by_frame.get(frame_number, [])

            frame_in_traced_movie = (
                frame_number >= movie_traced_frame_start
                and (movie_traced_frame_end is None or frame_number <= movie_traced_frame_end)
            )
            prior_frame_in_traced_movie = frame_number > movie_traced_frame_start
            if frame_in_traced_movie and prior_frame_in_traced_movie:
                update_trackpoint_segments(previous_trackpoints=trackpoints_prev,
                                           current_trackpoints=trackpoints_this,
                                           segments=trackpoint_segments)

            # Label the frame and write to the mp4 output if we are doing that
            if movie_traced_writer and frame_in_traced_movie:
                if path_overlay is None:
                    path_overlay = trace_path_overlay(frame, points_by_frame, movie_traced_frame_start,
                                                      movie_traced_frame_end, colors_by_label)
                frame_to_label = frame.copy()
                cv2_label_frame(frame=frame_to_label,
                                trackpoints=trackpoints_this,
                                frame_label=(f"{frame_number}  {frame_number * seconds_per_frame:g} s"
                                             if seconds_per_frame else str(frame_number)),
                                trackpoint_segments=trackpoint_segments,
                                path_overlay=path_overlay,
                                colors_by_label=colors_by_label)
                # IMPORTANT: OpenCV uses BGR colors, but the H.264 writer expects RGB.
                frame_rgb = cv2.cvtColor(frame_to_label, cv2.COLOR_BGR2RGB)
                movie_traced_writer.append_data(frame_rgb)
                written_frames += 1

            if callback is not None:
                callback(TracerCallbackArg(frame_number=frame_number, frame_data=frame,
                                           frame_trackpoints=trackpoints_this))

            # Advance
            trackpoints_prev = trackpoints_this
            gray_frame_prev = gray_frame
    finally:
        if hasattr(source_frames, "close"):
            source_frames.close()
        if movie_traced_writer:
            movie_traced_writer.close()
    if render_only and movie_traced_writer and movie_traced_frame_end is not None:
        if written_frames != movie_traced_frame_end - movie_traced_frame_start + 1:
            raise ValueError("Source movie ended before the requested trim range")
    return trackpoints_output


if __name__ == "__main__":
    # the only requirement for calling trace_movie() would be the "control points" and the movie
    parser = argparse.ArgumentParser(
        description="Run Trace movie with specified movies and initial points",
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
    trace_movie_v2(movie_url=Path(args.moviefile),
                   trackpoints=ipts,
                   frame_start=0,
                   movie_traced_path='traced.mp4')
    subprocess.call(['open', 'traced.mp4'])
