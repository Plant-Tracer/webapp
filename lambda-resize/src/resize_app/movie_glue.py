"""
movie_glue.py
Routines for providing access to the movies for the lambda
"""

import os
import json
from typing import NamedTuple
import boto3
import urllib
from pathlib import Path
import zipfile

from .src.app.schema import Trackpoint
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
from . import mpeg_jpeg_zip
from .mpeg_jpeg_zip import add_jpeg_comment, convert_frame_to_jpeg

from aws_lambda_powertools import Logger

from .src.app import odb
from .src.app.odb import (
    DDBO,
    ENABLED,
    MOVIE_DATA_URN,
    MOVIE_ROTATION,
    MOVIE_TRACED_URN,
    MOVIE_ZIPFILE_URN,
    TOTAL_FRAMES,
    USER_ID,
)

__version__ = "0.1.0"
LOG_ID_STATUS_PING = "lambda-status-ping"
LOGGER = Logger(service="planttracer")

class MovieInfo(NamedTuple):
    signed_url: str                    #
    signed_zipfile_url: str            # TODO
    rotation: int

def queue_tracking(api_key, movie_id, frame_start):
    """Send a tracking request through the SQS"""
    queue_url = os.environ.get("TRACKING_QUEUE_URL", "").strip()
    if not queue_url:
        LOGGER.error("TRACKING_QUEUE_URL not configured for follow-up batch")
        raise RuntimeError("TRACKING_QUEUE_URL not configured for follow-up batch")
    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION"))
    msg = { "api_key": api_key, "movie_id": movie_id, "frame_start": frame_start }
    LOGGER.info("Enqueuing follow-up SQS batch: %s", msg)
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(msg))
    return {"error":False, "message": msg}

def get_movie_url(*,api_key=None,movie_id=None) -> MovieInfo:
    """
    Given an api_key and a movie_id, return a signed URL and the desired movie rotation
    """
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

    rotation = int(movie.get(MOVIE_ROTATION,0))
    urn = movie.get(MOVIE_DATA_URN)
    if not urn or not urn.strip():
        raise ValueError("MOVIE_DATA_URN not set")

    parsed = urllib.parse.urlparse(urn)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise ValueError(f"invalid {MOVIE_DATA_URN}: {urn}")
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    s3 = boto3.client('s3')
    signed_url = s3.generate_presigned_url( ClientMethod='get_object',
                                            Params={'Bucket': bucket, 'Key': key},
                                            ExpiresIn=300 )
    return MovieInfo(url=signed_url, rotation=rotation)


def run_tracking(*, user_id, movie_id, frame_start):
    """Run tracking pipeline and create both zipfile and tracked mp4."""
    ddbo = DDBO()
    input_trackpoints = [Trackpoint(**tpdict) for tpdict in get_movie_trackpoints(movie_id=movie_id)]
    movie_record = get_movie_metadata(movie_id=movie_id)
    research_comment = mp4_metadata_lib.build_comment(
        movie_record.get("research_use", 0) or 0,
        movie_record.get("credit_by_name", 0) or 0,
        movie_record.get("attribution_name"),
    )

    if not input_trackpoints:
        raise RuntimeError("Cannot track movie with no trackpoints")

    LOGGER.info("run_tracking user_id=%s movie_id=%s frame_start=%s input_trackpoints=%s",user_id,movie_id,frame_start,input_trackpoints)

    # Derive true movie dimensions from the file so shrink/rotate decisions are
    # based on the real stream size, not any analysis/display size that may have
    # been written into DB width/height by get-frame(size=analysis).
    movie_urn = movie_record.get(MOVIE_DATA_URN)
    if not movie_urn:
        raise RuntimeError(f"movie {movie_id} has no movie data URN")

    zipfile_path = None
    movie_traced_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", mode="wb") as tf:
            zipfile_path = Path(tf.name)

        with tempfile.NamedTemporaryFile(suffix=".mp4", mode="wb") as tf:
            movie_traced_path = Path(tf.name)

        def trackercallback(obj:TrackerCallbackArg):
            if obj.frame_trackpoints:
                ddbo.update_table(ddbo.movies, movie_id, {LAST_FRAME_TRACKED: obj.frame_number})
                put_frame_trackpoints(movie_id=self.movie_id, frame_number=frame_number, trackpoints=frame_trackpoints)


        tracker.track_movie_v2(movie_url = s3_presigned.make_signed_url(movie_urn),
                               frame_start = frame_start,
                               trackpoints = input_trackpoints,
                               movie_zipfile_path = movie_zipfile_path,
                               movie_traced_path = movie_traced_path,
                               rotate = movie_record.get("rotate",0) or 0,
                               comment = research_comment,
                               callback = tracker_callback )

        # Upload the zipfile and the traced movie
        total_frames = max([tp.frame_number for tp in trackpoints])
        movie_zipfile_urn = movie_urn.replace(".","_zipfile.")
        write_object_from_path(urn=movie_zipfile_urn, path=zipfile_path)

        movie_traced_urn = movie_urn.replace(".","_traced.")
        write_object_from_path(urn=movie_traced_urn, path=movie_traced_path)

        # Update the database
        # note: should we update width, height and fps?
        ddbo.update_table(ddbo.movies, movie_id, {TOTAL_FRAMES:total_frames,
                                                  MOVIE_TRACED_URN: movie_traced_urn,
                                                  MOVIE_ZIPFILE_URN: movie_zipfile_urn})

    finally:
        if zipfile_path and zipfile_path.exists():
            zipfile_path.unlink()
        if movie_traced_path and movie_traced_path.exists():
            movie_traced_path.unlink()
