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

from aws_lambda_powertools import Logger

from .src.app import odb
from .src.app.odb import (
    DDBO,
    ENABLED,
    MOVIE_DATA_URN,
    MOVIE_ROTATION,
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


def run_tracking(*, movie_url, frame_start, trackpoints, zipfile_path:Path = None, rotation=0):
    """
    :param movie_url: filename or URL of an MPEG4
    :param frame_start: first frame to track.
    :param trackpoints: a trackpoints data structure. Trackpoints for frame_start must be provided.
    :param zipfile_path: If provided, where the zipfile of scaled, rotated images goes.
    :param rotation: the rotation (in degrees) to apply to the movie before scaling
    """

    # track from frame frame_start+1 to end using data from frame_start

    output_trackpoints = [tp for tp in trackpoints if tp['frame_number'] <= frame_start]
    last_trackpoints = [tp for tp in trackpoints if tp['frame_number'] == frame_start]

    if len(last_trackpoints) == 0:
        raise ValueError(f"len(trackpoints)={len(trackpoints)} but no tracked points for frame {frame_start}")

    zf = None
    if zipfile_path is not None:
        # pylint: disable=consider-using-with
        zf = zipfile.ZipFile(zipfile_path, mode='w', compression=zipfile.ZIP_DEFLATED, compresslevel=9)

    for (frame_number, frame) in enumerate(mpeg_jpeg_zip.get_frames_as_jpegs_from_url(movie_url, rotation)):
        pass



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
