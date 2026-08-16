"""Lambda entry points for local and EventBridge asynchronous movie work."""

import time

from aws_lambda_powertools import Logger

from . import async_work
from . import movie_glue
from .src.app.constants import storage_deployment_id

LOGGER = Logger(service="planttracer")

def process_tracing_message(body: dict):
    """Validate and process one tracing job."""
    if not body.get("movie_id"):
        raise ValueError("movie_id is required in tracing work")
    job = async_work.TraceJob.model_validate(body)

    t0 = time.time()
    LOGGER.info("Start tracing work: movie_id=%s frame_start=%s frame_end=%s",
                job.movie_id, job.frame_start, job.frame_end)
    kwargs = {
        "movie_id": job.movie_id,
        "frame_start": job.frame_start,
        "frame_end": job.frame_end,
    }
    if job.job_id is not None:
        kwargs["job_id"] = job.job_id
    movie_glue.run_tracing(**kwargs)
    LOGGER.info(
        "Completed tracing work: movie_id=%s frame_start=%s frame_end=%s elapsed_time=%s",
        job.movie_id,
        job.frame_start,
        job.frame_end,
        time.time() - t0,
    )


def process_queue_message(body: dict):
    """Validate and dispatch one local asynchronous job."""
    payload = dict(body)
    payload.setdefault("job_type", "trace")
    job = async_work.JOB_ADAPTER.validate_python(payload)
    process_job(job)


def process_job(job: async_work.TraceJob | async_work.PostUploadJob) -> None:
    """Process one validated asynchronous job."""
    if isinstance(job, async_work.PostUploadJob):
        movie_glue.process_uploaded_movie(movie_id=job.movie_id)
        return
    process_tracing_message(job.model_dump())


def process_async_work_event(raw_event) -> dict:
    """Validate stack routing and process one custom EventBridge work event."""
    event = async_work.AsyncWorkEvent.model_validate(raw_event)
    deployment_id = storage_deployment_id()
    if event.detail.stack_name != deployment_id:
        raise ValueError("async work event does not belong to this deployment")
    LOGGER.info(
        "Start async work: job_type=%s movie_id=%s",
        event.detail.job.job_type,
        event.detail.job.movie_id,
    )
    process_job(event.detail.job)
    LOGGER.info(
        "Completed async work: job_type=%s movie_id=%s",
        event.detail.job.job_type,
        event.detail.job.movie_id,
    )
    return {
        "processed": True,
        "job_type": event.detail.job.job_type,
        "movie_id": event.detail.job.movie_id,
    }
