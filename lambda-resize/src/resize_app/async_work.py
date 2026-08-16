"""Pydantic contract and EventBridge publisher for asynchronous movie work."""

import os
from typing import Annotated, Literal

import boto3
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .src.app.constants import storage_deployment_id

EVENT_SOURCE = "planttracer.async-work"
EVENT_DETAIL_TYPE = "Plant Tracer Async Work"
EVENT_BUS_NAME = "default"


class TraceJob(BaseModel):
    """User-requested tracing work."""

    job_type: Literal["trace"] = "trace"
    movie_id: str
    frame_start: int = 0
    frame_end: int | None = None


class PostUploadJob(BaseModel):
    """Post-upload inspection and normalization work."""

    job_type: Literal["post_upload"] = "post_upload"
    movie_id: str


AsyncJob = Annotated[TraceJob | PostUploadJob, Field(discriminator="job_type")]
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


def publish_job(job: TraceJob | PostUploadJob) -> None:
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
