"""S3 Object Created EventBridge adapter for movie uploads."""

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from . import movie_glue
from .src.app.constants import C, storage_deployment_id
from .src.app import odb
from .src.app.s3_presigned import make_urn, upload_staging_object_key


class S3EventBucket(BaseModel):
    """Bucket portion of an S3 EventBridge detail object."""

    name: str


class S3EventObject(BaseModel):
    """Object portion of an S3 EventBridge detail object."""

    model_config = ConfigDict(populate_by_name=True)

    key: str
    size: int = Field(ge=0)
    etag: str | None = None
    version_id: str | None = Field(default=None, alias="version-id")
    sequencer: str | None = None


class S3EventDetail(BaseModel):
    """S3-specific EventBridge detail."""

    bucket: S3EventBucket
    object: S3EventObject
    reason: str | None = None


class S3ObjectCreatedEvent(BaseModel):
    """Validated native S3 Object Created EventBridge envelope."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    source: Literal["aws.s3"]
    detail_type: Literal["Object Created"] = Field(alias="detail-type")
    detail: S3EventDetail


def process_upload_event(raw_event) -> movie_glue.UploadCompletion:
    """Validate stack routing and run the shared upload completion service."""
    event = S3ObjectCreatedEvent.model_validate(raw_event)
    deployment_id = storage_deployment_id()
    key_parts = event.detail.object.key.split("/")
    if len(key_parts) < 4:
        raise ValueError("uploaded movie key has too few path components")
    prefix, event_deployment_id = key_parts[:2]
    course_id = "/".join(key_parts[2:-1])
    movie_filename = key_parts[-1]
    if prefix != "uploads" or event_deployment_id != deployment_id:
        raise ValueError("uploaded movie key does not belong to this deployment")
    if not movie_filename.endswith(".mov"):
        raise ValueError("uploaded movie key must end in .mov")
    movie_id = movie_filename[:-4]
    if not odb.is_movie_id(movie_id):
        raise ValueError("uploaded movie key does not contain a valid movie ID")
    expected_key = upload_staging_object_key(
        deployment_id=deployment_id,
        course_id=course_id,
        movie_id=movie_id,
    )
    if event.detail.object.key != expected_key:
        raise ValueError("uploaded movie key is not canonical")
    configured_bucket = C.PLANTTRACER_S3_BUCKET
    if event.detail.bucket.name != os.environ.get(configured_bucket):
        raise ValueError("uploaded movie bucket does not match this deployment")
    return movie_glue.complete_uploaded_object(
        movie_id=movie_id,
        staging_urn=make_urn(
            object_name=event.detail.object.key,
            bucket=event.detail.bucket.name,
        ),
        event_id=event.id,
        event_size=event.detail.object.size,
        sequencer=event.detail.object.sequencer,
        source="aws-eventbridge",
    )
