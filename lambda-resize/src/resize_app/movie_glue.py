"""
movie_glue.py
Routines for providing access to the movies for the lambda
"""

import os
import json
from typing import NamedTuple
from pathlib import Path
import tempfile

import boto3
from aws_lambda_powertools import Logger

from .src.app.schema import Trackpoint
from .src.app.odb import (
    get_movie_metadata,
    get_movie_trackpoints,
    put_frame_trackpoints,
    clear_movie_tracking_after_frame,
    LAST_FRAME_TRACKED,
)
from .src.app.odb_movie_data import (write_object_from_path )
from .src.app import mp4_metadata_lib
from .src.app import s3_presigned
from .src.app import odb
from .src.app.odb import (
    DDBO,
    ENABLED,
    MOVIE_DATA_URN,
    MOVIE_ROTATION,
    MOVIE_TRACED_URN,
    MOVIE_ZIPFILE_URN,
    NEEDS_RETRACING,
    MOVIE_STATUS,
    MOVIE_STATE_READY,
    MOVIE_STATE_UPLOADING,
    MOVIE_STATE_TRACING,
    MOVIE_STATE_TRACING_COMPLETED,
    TOTAL_FRAMES,
    USER_ID
)

from . import local_queue
from . import mpeg_jpeg_zip
from . import tracer

__version__ = "0.1.0"
LOG_ID_STATUS_PING = "lambda-status-ping"
LOGGER = Logger(service="planttracer")

class MovieInfo(NamedTuple):
    signed_url: str                    #
    signed_zipfile_url: str            # TODO
    rotation: int


class MovieDownloadInfo(NamedTuple):
    signed_movie_url: str
    signed_zipfile_url: str | None


def sqs_client():
    return boto3.client(
        "sqs",
        region_name=os.environ.get("AWS_REGION"),
        endpoint_url=os.environ.get("AWS_ENDPOINT_URL_SQS"),
    )


def validate_movie_access(*, api_key=None, movie_id=None):
    if not api_key:
        raise ValueError("api_key required")
    if not odb.is_movie_id(movie_id):
        raise ValueError("movie_id is not valid")
    ddbo = DDBO()
    api_key_dict = ddbo.get_api_key_dict(api_key)
    if api_key_dict is None:
        raise ValueError("api_key is not valid")
    if not api_key_dict.get(ENABLED, True):
        raise ValueError("api_key is not enabled")
    user_id = api_key_dict.get(USER_ID)
    if not user_id:
        raise ValueError("user_id is required")
    try:
        user = ddbo.get_user(user_id)
        if not user.get(ENABLED, True):
            raise ValueError("user is not enabled")
    except odb.InvalidUser_Id as e:
        raise ValueError("user_id is invalid") from e
    try:
        movie = odb.can_access_movie(user_id=user_id, movie_id=movie_id)
    except odb.UnauthorizedUser as e:
        raise ValueError(f"user {user_id} is not authorized to access movie {movie_id}") from e
    except odb.InvalidMovie_Id as e:
        raise ValueError("movie_id is invalid") from e
    return ddbo, user_id, movie

def queue_tracing(api_key:str, movie_id:str, frame_start:int, frame_end:int|None=None):
    """Send a tracing request through SQS or the local debug queue."""
    msg = {"api_key": api_key, "movie_id": movie_id, "frame_start": frame_start}
    safe_msg = {"movie_id": movie_id, "frame_start": frame_start}
    if frame_end is not None:
        msg["frame_end"] = int(frame_end)
        safe_msg["frame_end"] = int(frame_end)
    queue_mode = (os.environ.get("TRACING_QUEUE_MODE")
                  or os.environ.get("TRACKING_QUEUE_MODE", "")).strip().lower()
    if queue_mode == "local":
        LOGGER.info("Enqueuing follow-up local batch: %s", safe_msg)
        local_queue.enqueue_message(msg)
        return {"error": False, "message": safe_msg}
    queue_url = (os.environ.get("TRACING_QUEUE_URL")
                 or os.environ.get("TRACKING_QUEUE_URL", "")).strip()
    if not queue_url:
        LOGGER.error("TRACING_QUEUE_URL not configured for follow-up batch")
        raise RuntimeError("TRACING_QUEUE_URL not configured for follow-up batch")
    LOGGER.info("Enqueuing follow-up SQS batch: %s", safe_msg)
    sqs_client().send_message(QueueUrl=queue_url, MessageBody=json.dumps(msg))
    return {"error":False, "message": safe_msg}


def prepare_tracing_request(*, api_key: str, movie_id: str, frame_start: int, frame_end: int|None=None) -> dict:
    """Validate access and mark the movie as retracing before queueing work.

    This closes the UI race where the browser polls before the worker has had
    a chance to flip the movie state away from ``tracing completed``.
    """
    ddbo, _user_id, _movie = validate_movie_access(api_key=api_key, movie_id=movie_id)
    source_frame_number = int(frame_start)
    frame_end_number = None if frame_end is None else int(frame_end)
    cleared_frames = clear_movie_tracking_after_frame(
        movie_id=movie_id,
        frame_number=source_frame_number,
        frame_end=frame_end_number,
    )
    ddbo.update_table(ddbo.movies, movie_id, {MOVIE_STATUS: MOVIE_STATE_TRACING})
    LOGGER.info(
        "Prepared tracing request: movie_id=%s source_frame=%s frame_end=%s cleared_frames=%s",
        movie_id,
        source_frame_number,
        frame_end_number,
        cleared_frames,
    )
    ret = {"movie_id": movie_id, "frame_start": source_frame_number, "cleared_frames": cleared_frames}
    if frame_end_number is not None:
        ret["frame_end"] = frame_end_number
    return ret

def movie_rotation(movie: dict) -> int:
    """Return a safe integer movie rotation, defaulting invalid metadata to 0."""
    rotation_value = movie.get(MOVIE_ROTATION, 0) or 0
    try:
        return int(rotation_value)
    except (TypeError, ValueError):
        return 0

def get_movie_url_and_rotation(*,api_key=None,movie_id=None) -> MovieInfo:
    """
    Given an api_key and a movie_id, return a signed URL and the desired movie rotation
    """
    _, _, movie = validate_movie_access(api_key=api_key, movie_id=movie_id)

    rotation = movie_rotation(movie)
    urn = movie.get(MOVIE_DATA_URN)
    if not urn or not urn.strip():
        raise ValueError("MOVIE_DATA_URN not set")

    if movie.get(MOVIE_STATUS,'')==MOVIE_STATE_UPLOADING:
        odb.set_movie_metadata(movie_id=movie_id, movie_metadata={MOVIE_STATUS:MOVIE_STATE_READY})

    return MovieInfo(
        signed_url=s3_presigned.make_signed_url(urn=urn, operation='get', expires=300),
        signed_zipfile_url=None,
        rotation=rotation,
    )


def get_movie_download_urls(*, api_key=None, movie_id=None) -> MovieDownloadInfo:
    """Return signed URLs for movie playback and optional frame ZIP download."""
    _, _, movie = validate_movie_access(api_key=api_key, movie_id=movie_id)
    movie_urn = (movie.get(MOVIE_DATA_URN) or "").strip()
    if not movie_urn:
        raise ValueError("MOVIE_DATA_URN not set")
    zip_urn = (movie.get(MOVIE_ZIPFILE_URN) or "").strip() or None
    return MovieDownloadInfo(
        signed_movie_url=s3_presigned.make_signed_url(urn=movie_urn, operation='get', expires=300),
        signed_zipfile_url=s3_presigned.make_signed_url(urn=zip_urn, operation='get', expires=300) if zip_urn else None,
    )


def first_frame_to_track(*, source_frame_number:int) -> int:
    """Translate a user-selected source frame into the first frame to recompute."""
    if source_frame_number < 0:
        raise ValueError("source_frame_number must be >= 0")
    return 1 if source_frame_number == 0 else source_frame_number + 1


def analysis_frame_height_from_movie(*, movie_url: str, rotation: int) -> int:
    """Return the frame height in the same rotated/scaled coordinate space used by tracer."""
    frame = mpeg_jpeg_zip.get_first_frame_from_url(movie_url, rotation)
    height = int(frame.shape[0])
    if height <= 0:
        raise RuntimeError("analysis frame height must be positive")
    return height


def run_tracing(*, movie_id, frame_start, frame_end=None):
    """Run tracing pipeline and create both zipfile and tracked mp4.

    ``frame_start`` is the frame the user edited and wants to retrace from.
    That frame remains the source of truth; tracing resumes at ``frame_start + 1``.
    """
    ddbo = DDBO()
    source_frame_number = int(frame_start)
    tracing_frame_start = first_frame_to_track(source_frame_number=source_frame_number)
    frame_end_number = None if frame_end is None else int(frame_end)
    cleared_frames = clear_movie_tracking_after_frame(
        movie_id=movie_id,
        frame_number=source_frame_number,
        frame_end=frame_end_number,
    )
    LOGGER.info("run_tracing movie_id=%s source_frame=%s tracing_frame_start=%s frame_end=%s cleared_frames=%s",
                movie_id, source_frame_number, tracing_frame_start, frame_end_number, cleared_frames)
    ddbo.update_table(ddbo.movies, movie_id, {MOVIE_STATUS: MOVIE_STATE_TRACING})

    movie_record = get_movie_metadata(movie_id=movie_id)
    movie_urn = movie_record.get(MOVIE_DATA_URN)
    if not movie_urn:
        raise RuntimeError(f"movie {movie_id} has no movie data URN")
    rotation = movie_rotation(movie_record)
    movie_url = s3_presigned.make_signed_url(urn=movie_urn)
    frame_height = analysis_frame_height_from_movie(movie_url=movie_url, rotation=rotation)
    odb.ensure_bottom_left_trackpoints(movie_id=movie_id, frame_height=frame_height)
    input_trackpoints = [Trackpoint(**tpdict) for tpdict in get_movie_trackpoints(movie_id=movie_id)]
    tracer_input_trackpoints = odb.flip_trackpoints_y(input_trackpoints, frame_height)
    research_comment = mp4_metadata_lib.build_comment(
        movie_record.get("research_use", 0) or 0,
        movie_record.get("credit_by_name", 0) or 0,
        movie_record.get("attribution_name"),
    )

    if not input_trackpoints:
        raise RuntimeError("Cannot trace movie with no trackpoints")

    LOGGER.info("run_tracing movie_id=%s source_frame=%s tracing_frame_start=%s frame_end=%s input_trackpoints=%s",
                movie_id, source_frame_number, tracing_frame_start, frame_end_number, tracer_input_trackpoints)
    movie_traced_frame_start, movie_traced_frame_end = odb.movie_trim_bounds(movie_record)
    if frame_end_number is not None:
        movie_traced_frame_end = (
            frame_end_number if movie_traced_frame_end is None
            else min(movie_traced_frame_end, frame_end_number)
        )
    LOGGER.info("run_tracing movie_id=%s traced_mp4_frame_start=%s traced_mp4_frame_end=%s",
                movie_id, movie_traced_frame_start, movie_traced_frame_end)

    movie_zipfile_path = None
    movie_traced_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", mode="wb") as tf:
            movie_zipfile_path = Path(tf.name)

        with tempfile.NamedTemporaryFile(suffix=".mp4", mode="wb") as tf:
            movie_traced_path = Path(tf.name)

        def tracer_callback(obj:tracer.TracerCallbackArg):
            frame_trackpoints = obj.frame_trackpoints or []
            LOGGER.info(
                "tracer_callback frame=%s trace_range=%s-%s traced_mp4_range=%s-%s trackpoint_count=%s labels=%s",
                obj.frame_number,
                tracing_frame_start,
                frame_end_number,
                movie_traced_frame_start,
                movie_traced_frame_end,
                len(frame_trackpoints),
                [trackpoint.label for trackpoint in frame_trackpoints],
            )
            if obj.frame_trackpoints and (frame_end_number is None or obj.frame_number <= frame_end_number):
                frame_trackpoints = odb.flip_trackpoints_y(obj.frame_trackpoints, frame_height)
                ddbo.update_table(ddbo.movies, movie_id, {LAST_FRAME_TRACKED: obj.frame_number})
                put_frame_trackpoints(movie_id=movie_id, frame_number=obj.frame_number, trackpoints=frame_trackpoints)


        trackpoints = tracer.trace_movie_v2(movie_url = movie_url,
                                            frame_start = tracing_frame_start,
                                            frame_end = frame_end_number,
                                            trackpoints = tracer_input_trackpoints,
                                            movie_zipfile_path = movie_zipfile_path,
                                            movie_traced_path = movie_traced_path,
                                            movie_traced_frame_range = tracer.TracedMovieFrameRange(
                                                start=movie_traced_frame_start,
                                                end=movie_traced_frame_end,
                                            ),
                                            rotation = rotation,
                                            callback = tracer_callback,
                                            comment = research_comment )

        # Upload the zipfile and the traced movie
        total_frames = int(movie_record.get(TOTAL_FRAMES) or max((tp.frame_number for tp in trackpoints)) + 1)
        (name,ext) = os.path.splitext(movie_urn)
        movie_zipfile_urn = name+"_zipfile"+ext
        write_object_from_path(urn=movie_zipfile_urn, path=movie_zipfile_path)

        # Best-effort snapshot of the capture interval into the traced MP4. DynamoDB remains
        # authoritative; later edits update only the DB (see docs/Development/MOVIE_METADATA.rst).
        movie_fpm = movie_record.get("fpm")
        if movie_fpm:
            try:
                mp4_metadata_lib.set_fpm(str(movie_traced_path), movie_fpm)
            except Exception:  # pylint: disable=broad-exception-caught
                LOGGER.exception("failed to write fpm metadata to traced movie movie_id=%s", movie_id)

        movie_traced_urn = name+"_traced"+ext
        write_object_from_path(urn=movie_traced_urn, path=movie_traced_path)

        # Update the database
        # note: should we update width, height and fps?
        ddbo.update_table(ddbo.movies, movie_id, {TOTAL_FRAMES:total_frames,
                                                  MOVIE_STATUS: MOVIE_STATE_TRACING_COMPLETED,
                                                  NEEDS_RETRACING: 0,
                                                  MOVIE_TRACED_URN: movie_traced_urn,
                                                  MOVIE_ZIPFILE_URN: movie_zipfile_urn})

    finally:
        if movie_zipfile_path and movie_zipfile_path.exists():
            movie_zipfile_path.unlink()
        if movie_traced_path and movie_traced_path.exists():
            movie_traced_path.unlink()
