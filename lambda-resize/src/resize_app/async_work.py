"""Pydantic contract and EventBridge publisher for asynchronous movie work."""

import os
from typing import Annotated, Literal

import boto3
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from . import local_queue
from .src.app.constants import C, storage_deployment_id
from .src.app.schema import Trackpoint

EVENT_SOURCE = "planttracer.async-work"
EVENT_DETAIL_TYPE = "Plant Tracer Async Work"
EVENT_BUS_NAME = "default"


class TraceJob(BaseModel):
    """User-requested tracing work."""

    job_type: Literal["trace"] = "trace"
    movie_id: str
    frame_start: int = 0
    frame_end: int | None = None
    job_id: str | None = None


class RenderTracedJob(BaseModel):
    """Render saved annotations with no tracking or frame-data writes."""

    job_type: Literal["render_traced"] = "render_traced"
    movie_id: str
    job_id: str


class PostUploadJob(BaseModel):
    """Post-upload inspection and normalization work."""

    job_type: Literal["post_upload"] = "post_upload"
    movie_id: str


class RecodeJob(BaseModel):
    """On-demand analysis encoding with a preclaimed processing lease."""

    job_type: Literal["recode"] = "recode"
    movie_id: str
    attempt: str
    completed_status: str


class ResetRequest(BaseModel):
    """Inclusive frame range and replacement markers for its seed frame."""

    movie_id: str
    frame_start: int = Field(ge=0, lt=C.MAX_FRAMES)
    frame_end: int = Field(ge=0, lt=C.MAX_FRAMES)
    seed_frame: int = Field(ge=0, lt=C.MAX_FRAMES)
    trackpoints: list[Trackpoint] = Field(min_length=1, max_length=100)
    analysis_lease_id: str | None = None

    @model_validator(mode="after")
    def validate_range(self):
        """Reject inverted ranges and replacement markers outside the range."""
        if not self.frame_start <= self.seed_frame <= self.frame_end:
            raise ValueError("seed_frame must be inside the inclusive reset range")
        for point in self.trackpoints:
            point.frame_number = self.seed_frame
        return self


class ResetJob(ResetRequest):
    """Retryable range reset; progress is checkpointed in DynamoDB."""

    job_type: Literal["reset"] = "reset"
    job_id: str


AsyncJob = Annotated[TraceJob | PostUploadJob | ResetJob | RecodeJob | RenderTracedJob, Field(discriminator="job_type")]
JOB_ADAPTER = TypeAdapter(AsyncJob)


class AsyncWorkDetail(BaseModel):
    """Stack-scoped custom EventBridge event detail."""

    stack_name: str
    job: AsyncJob


class AsyncWorkEvent(BaseModel):
    """Validated custom EventBridge envelope delivered to lambda-resize."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    source: Literal[EVENT_SOURCE]
    detail_type: Literal[EVENT_DETAIL_TYPE] = Field(alias="detail-type")
    detail: AsyncWorkDetail


def eventbridge_client():
    """Return the deployed EventBridge client."""
    return boto3.client(
        "events",
        region_name=os.environ.get("AWS_REGION"),
        endpoint_url=os.environ.get("AWS_ENDPOINT_URL_EVENTS"),
    )


def publish_job(job: TraceJob | PostUploadJob | ResetJob | RecodeJob | RenderTracedJob) -> None:
    """Publish one stack-scoped work item and reject partial PutEvents failure."""
    detail = AsyncWorkDetail(stack_name=storage_deployment_id(), job=job)
    response = eventbridge_client().put_events(Entries=[{
        "EventBusName": EVENT_BUS_NAME,
        "Source": EVENT_SOURCE,
        "DetailType": EVENT_DETAIL_TYPE,
        "Detail": detail.model_dump_json(),
    }])
    if int(response.get("FailedEntryCount", 0)):
        entry = (response.get("Entries") or [{}])[0]
        code = entry.get("ErrorCode", "unknown")
        message = entry.get("ErrorMessage", "unknown error")
        raise RuntimeError(f"EventBridge rejected async work: {code}: {message}")


def enqueue_job(job):
    """Send one typed job to the configured local worker or EventBridge."""
    mode = (os.environ.get("TRACING_QUEUE_MODE") or os.environ.get("TRACKING_QUEUE_MODE", "")).strip().lower()
    if mode == "local":
        local_queue.enqueue_message(job.model_dump())
    else:
        publish_job(job)
