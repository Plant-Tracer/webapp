"""Assemble camera JPEG uploads into the source MP4 and run normal processing."""

# pylint: disable=no-member  # cv2 exposes C extension members pylint cannot see

import os
import time
import tempfile
from pathlib import Path

import cv2
import numpy as np
from aws_lambda_powertools import Logger

from . import async_work, local_queue, movie_glue
from .src.app import odb, mp4_metadata_lib, s3_presigned
from .src.app.constants import storage_deployment_id
from .video_writer import H264Writer

LOGGER = Logger(service="planttracer")
CAMERA_PLAYBACK_FPS = 15
CAMERA_FRAME_PREFIX_NUMBER = 0


def _frame_objects(*, movie):
    """List the uploaded camera frames in their stable numeric order."""
    first_frame_urn = s3_presigned.make_urn(
        object_name=s3_presigned.frame_object_key(
            deployment_id=storage_deployment_id(),
            course_id=movie[odb.COURSE_ID],
            movie_id=movie[odb.MOVIE_ID],
            frame_number=CAMERA_FRAME_PREFIX_NUMBER,
        ),
    )
    bucket, first_key = s3_presigned.parse_s3_urn(urn=first_frame_urn)
    prefix = first_key.rsplit("/", 1)[0] + "/"
    objects = []
    paginator = s3_presigned.s3_client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            name = key.rsplit("/", 1)[-1]
            if name.endswith(".jpg") and name[:-4].isdigit():
                objects.append((int(name[:-4]), key))
    objects.sort()
    if not objects:
        raise ValueError("No camera frames were uploaded")
    if [number for number, _key in objects] != list(range(len(objects))):
        raise ValueError("Camera frame uploads are incomplete")
    return bucket, [key for _number, key in objects]


def finish(*, api_key: str, movie_id: str) -> dict:
    """Claim and queue camera finalization after validating its uploaded frames."""
    ddbo, _user_id, movie = movie_glue.validate_movie_access(
        api_key=api_key,
        movie_id=movie_id,
        require_edit=True,
    )
    if not movie.get(odb.CAMERA_CAPTURE):
        raise ValueError("movie is not a camera recording")
    if movie.get(odb.MOVIE_STATUS) != odb.MOVIE_STATE_UPLOADING:
        raise ValueError("camera recording is no longer accepting frames")
    _frame_objects(movie=movie)
    attempt = ddbo.claim_movie_processing(movie_id)
    if attempt is None:
        raise ValueError("camera movie is already processed")
    job = async_work.CameraMovieJob(movie_id=movie_id, attempt=attempt)
    queue_mode = movie_glue.async_queue_mode()
    if queue_mode == "local":
        local_queue.enqueue_message(job.model_dump())
    elif not queue_mode and os.environ.get(odb.C.AWS_REGION) == "local":
        process(job)
    else:
        try:
            async_work.publish_job(job)
        except Exception:
            ddbo.update_movie(
                movie_id,
                {
                    odb.MOVIE_STATUS: odb.MOVIE_STATE_UPLOADING,
                    odb.WORK_PURPOSE: None,
                    odb.PROCESSING_ATTEMPT: None,
                    odb.PROCESSING_EXPIRES_AT: None,
                    odb.RESIZE_STARTED_AT: None,
                },
                expected_processing_attempt=attempt,
            )
            raise
    return {"movie_id": movie_id, "status": odb.MOVIE_STATE_PROCESSING}


def _write_source_movie(*, movie, bucket, frame_keys, path):
    """Encode ordered JPEG frames into the durable source MP4 object."""
    client = s3_presigned.s3_client()
    writer = H264Writer(path, fps=CAMERA_PLAYBACK_FPS, quality=5)
    frame_size = None
    try:
        for key in frame_keys:
            frame_bytes = client.get_object(Bucket=bucket, Key=key)["Body"].read()
            frame = cv2.imdecode(np.frombuffer(frame_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError(f"Camera frame is not a decodable JPEG: {key.rsplit('/', 1)[-1]}")
            height, width = frame.shape[:2]
            if frame_size is None:
                frame_size = (width, height)
                if frame_size not in ((640, 480), (480, 640)):
                    raise ValueError("Camera frames must be 640x480 or 480x640")
            elif frame_size != (width, height):
                raise ValueError("Camera frames changed dimensions during recording")
            writer.append_data(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        writer.close()

    mp4_metadata_lib.set_fpm(str(path), movie.get(odb.FPM) or "4")
    mp4_metadata_lib.set_comment(
        str(path),
        mp4_metadata_lib.build_comment(
            movie.get("research_use", 0) or 0,
            movie.get("credit_by_name", 0) or 0,
            movie.get("attribution_name"),
        ),
    )
    bucket_name, object_key = s3_presigned.parse_s3_urn(urn=movie[odb.MOVIE_DATA_URN])
    with path.open("rb") as source_file:
        client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=source_file,
            ContentType="video/mp4",
        )


def process(job: async_work.CameraMovieJob) -> None:
    """Encode a claimed camera recording, then use standard MP4 processing."""
    ddbo = odb.DDBO()
    movie = ddbo.get_movie(job.movie_id)
    if not movie.get(odb.CAMERA_CAPTURE):
        raise ValueError("movie is not a camera recording")
    if movie.get(odb.RESIZED_AT) and movie.get(odb.ANALYSIS_MP4):
        return
    if movie.get(odb.MOVIE_STATUS) == odb.MOVIE_STATE_PROCESSING_FAILED:
        LOGGER.info("Ignoring stale camera movie job movie_id=%s", job.movie_id)
        return
    expires_at = int(movie.get(odb.PROCESSING_EXPIRES_AT) or 0)
    if expires_at <= int(time.time()):
        attempt = ddbo.claim_movie_processing(job.movie_id)
        if attempt is None:
            return
        job = async_work.CameraMovieJob(movie_id=job.movie_id, attempt=attempt)
    elif movie.get(odb.PROCESSING_ATTEMPT) != job.attempt:
        raise odb.MovieProcessingLocked(job.movie_id)
    try:
        bucket, frame_keys = _frame_objects(movie=movie)
        with tempfile.TemporaryDirectory() as output_dir:
            source_path = Path(output_dir) / "camera.mp4"
            _write_source_movie(movie=movie, bucket=bucket, frame_keys=frame_keys, path=source_path)
            uploaded_at = int(time.time())
            ddbo.update_movie(
                job.movie_id,
                {
                    odb.UPLOADED_AT: uploaded_at,
                    odb.TOTAL_BYTES: source_path.stat().st_size,
                    odb.TOTAL_FRAMES: len(frame_keys),
                },
                expected_processing_attempt=job.attempt,
            )
        movie_glue.process_uploaded_movie(movie_id=job.movie_id, processing_attempt=job.attempt)
    except Exception as exc:
        try:
            ddbo.update_movie(
                job.movie_id,
                {
                    odb.MOVIE_STATUS: odb.MOVIE_STATE_PROCESSING_FAILED,
                    odb.PROCESSING_FAILED_AT: int(time.time()),
                    odb.PROCESSING_FAILURE_SUMMARY: f"{type(exc).__name__}: {exc}"[:500],
                    odb.WORK_PURPOSE: None,
                    odb.PROCESSING_ATTEMPT: None,
                    odb.PROCESSING_EXPIRES_AT: None,
                },
                expected_processing_attempt=job.attempt,
            )
        except odb.MovieProcessingLeaseLost:
            LOGGER.info("Discarding stale camera movie failure movie_id=%s", job.movie_id)
        raise
