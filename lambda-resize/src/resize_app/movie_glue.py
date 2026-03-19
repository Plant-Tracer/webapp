"""
movie_glue.py
Routines for providing access to the movies for the lambda
"""

import os
import json
from typing import NamedTuple
import boto3
import urllib

from . import mpeg_jpeg_zip

from aws_lambda_powertools import Logger

from .src.app import odb
from .src.app.odb import (
    DDBO,
    ENABLED,
    MOVIE_DATA_URN,
    MOVIE_ROTATION,
    MOVIE_MAX_WIDTH,
    MOVIE_JPEG_QUALITY,
    TOTAL_BYTES,
    FPS,
    WIDTH,
    HEIGHT,
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
    queue_url = os.environ.get("TRACKING_QUEUE_URL", "").strip()
    if not queue_url:
        LOGGER.error("TRACKING_QUEUE_URL not configured for follow-up batch")
        raise RuntimeError("TRACKING_QUEUE_URL not configured for follow-up batch")
    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION"))
    msg = { "api_key": api_key,
            "movie_id": movie_id,
            "frame_start": frame_start }
    LOGGER.info("Enqueuing follow-up SQS batch: %s", msg)
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(msg))
    return {"error":False,
            "message": msg}

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


def trace_movie(api_key, movie_id, first_frame):
    url = get_movie_url(api_key=api_key, movie_id=movie_id)
