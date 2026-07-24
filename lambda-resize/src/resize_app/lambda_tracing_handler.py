"""
Lambda entry points for tracing: direct invoke (no Flask) and SQS.
"""

import json
import time
from typing import Annotated, Literal

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord
from pydantic import BaseModel, Field, TypeAdapter

from . import movie_glue

LOGGER = Logger(service="planttracer")
MAX_BATCH_SIZE = 500
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}

class TraceJob(BaseModel):
    """User-requested tracing queue job."""

    job_type: Literal["trace"] = "trace"
    movie_id: str
    frame_start: int = 0
    frame_end: int | None = None
    api_key: str | None = None


class PostUploadJob(BaseModel):
    """S3-triggered post-upload inspection/resizing job."""

    job_type: Literal["post_upload"]
    movie_id: str


QUEUE_JOB_ADAPTER = TypeAdapter(
    Annotated[TraceJob | PostUploadJob, Field(discriminator="job_type")]
)

def process_tracing_message(body: dict):
    """Process legacy or explicit tracing messages."""
    if not body.get("movie_id"):
        raise ValueError("movie_id is required in SQS message")
    job = TraceJob.model_validate(body)

    t0 = time.time()
    LOGGER.info("SQS Start tracing batch: movie_id=%s frame_start=%s frame_end=%s",
                job.movie_id, job.frame_start, job.frame_end)
    movie_glue.run_tracing(
        movie_id=job.movie_id,
        frame_start=job.frame_start,
        frame_end=job.frame_end,
    )
    LOGGER.info(
        "SQS Completed tracing batch: movie_id=%s frame_start=%s frame_end=%s elapsed_time=%s",
        job.movie_id,
        job.frame_start,
        job.frame_end,
        time.time() - t0,
    )


def process_queue_message(body: dict):
    """Validate and dispatch one queue job."""
    payload = dict(body)
    payload.setdefault(movie_glue.QUEUE_JOB_TYPE, movie_glue.TRACE_JOB)
    job = QUEUE_JOB_ADAPTER.validate_python(payload)
    if isinstance(job, PostUploadJob):
        movie_glue.process_uploaded_movie(movie_id=job.movie_id)
        return
    process_tracing_message(job.model_dump())


def process_tracing_record(record: SQSRecord):
    """
    Process a single SQS message.
    If this raises an exception, BatchProcessor marks only this record for retry.
    """
    try:
        body = json.loads(record.body or "{}")
    except json.JSONDecodeError as exc:
        LOGGER.error("Invalid JSON in SQS body: %s", exc)
        raise
    process_queue_message(body)
