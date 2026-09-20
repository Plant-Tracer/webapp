"""Request-driven analysis MP4 repair without per-view duplicate encoding."""

import time
import uuid

from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
from pydantic import BaseModel

from . import async_work, local_queue, movie_glue
from .analysis_mp4 import ANALYSIS_ENCODER_VERSION
from .src.app import odb, s3_presigned

RECODE_STATE = 'recode_state'
RECODE_STATUS = 'recode_previous_status'
QUEUED = 'queued'
RUNNING = 'running'
MESSAGE = 'Recoding is in progress, come back in a few minutes.'
ERROR = 'Error'
CODE = 'Code'


class RecodeRequest(BaseModel):
    """Only the server chooses the job identifier and processing state."""

    movie_id: str


class RecodeResponse(BaseModel):
    """Preparation result; clients need not poll or hold an editing lease."""

    ready: bool = False
    message: str = MESSAGE
    error: bool = False


def reserve(movie):
    """Reserve one encode atomically; duplicate viewers create no queue traffic."""
    now = int(time.time())
    if movie.get(odb.PROCESSING_EXPIRES_AT, 0) > now:
        return None
    if movie.get(odb.PROCESSING_FAILED_AT):
        raise ValueError('Recoding failed. Contact an administrator: '
                         + str(movie.get(odb.PROCESSING_FAILURE_SUMMARY, 'Unknown processing error'))[:500])
    if odb.movie_analysis_lock_from_record(movie) or odb.movie_trace_lock_from_record(movie):
        raise ValueError('This movie is being edited or traced. Close Analyze and try again later.')
    status = movie.get(odb.MOVIE_STATUS) or odb.MOVIE_STATE_READY
    if status == odb.MOVIE_STATE_PROCESSING:
        status = movie.get(RECODE_STATUS) or odb.MOVIE_STATE_READY
    job = async_work.RecodeJob(movie_id=movie[odb.MOVIE_ID], attempt=uuid.uuid4().hex,
                              completed_status=status)
    condition = Attr(odb.MOVIE_ID).exists()
    for name in (odb.PROCESSING_EXPIRES_AT, odb.ANALYSIS_LOCK_EXPIRES_AT, odb.TRACE_LOCK_EXPIRES_AT):
        condition &= Attr(name).not_exists() | Attr(name).lte(now)
    condition &= Attr(odb.PROCESSING_FAILED_AT).not_exists()
    condition &= (Attr(odb.ANALYSIS_MP4).eq(movie[odb.ANALYSIS_MP4]) if movie.get(odb.ANALYSIS_MP4)
                  else Attr(odb.ANALYSIS_MP4).not_exists())
    height = movie.get(odb.FRAME_HEIGHT_PX)
    condition &= (Attr(odb.FRAME_HEIGHT_PX).eq(height) if height is not None
                  else Attr(odb.FRAME_HEIGHT_PX).not_exists())
    analysis = odb.movie_analysis_mp4(movie)
    if height is None and analysis:
        height = analysis.height
    ddbo = odb.DDBO()
    try:
        ddbo.update_table(ddbo.movies, job.movie_id, {
            odb.PROCESSING_ATTEMPT: job.attempt, odb.PROCESSING_EXPIRES_AT: now + 15 * 60,
            odb.MOVIE_STATUS: odb.MOVIE_STATE_PROCESSING, RECODE_STATE: QUEUED,
            RECODE_STATUS: status, odb.ANALYSIS_MP4: None,
            **({odb.FRAME_HEIGHT_PX: height} if height is not None else {}),
        }, condition_expression=condition)
    except ClientError as exc:
        if exc.response[ERROR][CODE] != 'ConditionalCheckFailedException':
            raise
        if ddbo.get_movie(job.movie_id).get(odb.PROCESSING_EXPIRES_AT, 0) > time.time():
            return None
        raise ValueError('Movie changed while preparing analysis. Reopen Analyze.') from exc
    return job


def prepare(*, api_key, request: RecodeRequest):
    """Authenticate, check the object, and enqueue at most one repair per lease."""
    _, _, movie = movie_glue.validate_movie_access(api_key=api_key, movie_id=request.movie_id)
    if not odb.movie_is_available(movie):
        raise ValueError('Movie upload is not complete.')
    if movie.get(odb.PROCESSING_EXPIRES_AT, 0) > time.time():
        return RecodeResponse()
    analysis = odb.movie_analysis_mp4(movie)
    if analysis and analysis.encoder_version >= ANALYSIS_ENCODER_VERSION:
        bucket, key = s3_presigned.parse_s3_urn(urn=analysis.urn)
        try:
            s3_presigned.s3_client().head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if exc.response[ERROR][CODE] not in ('404', 'NoSuchKey', 'NotFound'):
                raise
        else:
            return RecodeResponse(ready=True, message='')
    job = reserve(movie)
    if job:
        try:
            if movie_glue.async_queue_mode() == 'local':
                local_queue.enqueue_message(job.model_dump())
            else:
                async_work.publish_job(job)
        except Exception:
            # A publish failure permits a later explicit page opening to retry.
            odb.DDBO().update_movie(job.movie_id, {
                odb.PROCESSING_ATTEMPT: None, odb.PROCESSING_EXPIRES_AT: None,
                odb.MOVIE_STATUS: job.completed_status, RECODE_STATE: None,
            }, expected_processing_attempt=job.attempt)
            raise
    return RecodeResponse()


def process(job: async_work.RecodeJob):
    """Only one delivery runs; a crash can be retried on a later page opening."""
    ddbo = odb.DDBO()
    try:
        ddbo.update_table(ddbo.movies, job.movie_id, {RECODE_STATE: RUNNING},
                          condition_expression=(Attr(odb.PROCESSING_ATTEMPT).eq(job.attempt)
                                                & Attr(odb.PROCESSING_EXPIRES_AT).gt(int(time.time()))
                                                & Attr(RECODE_STATE).eq(QUEUED)))
    except ClientError as exc:
        if exc.response[ERROR][CODE] != 'ConditionalCheckFailedException':
            raise
        return
    movie_glue.process_uploaded_movie(movie_id=job.movie_id, processing_attempt=job.attempt,
                                     completed_status=job.completed_status)
