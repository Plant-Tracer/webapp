"""Integration coverage for S3/EventBridge upload completion."""

import time
from pathlib import Path

from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
import pytest
from pydantic import BaseModel

from resize_app import lambda_tracing_handler, local_queue, main, movie_glue, upload_event
from resize_app.src.app import odb, odb_movie_data, s3_presigned
from resize_app.src.app.constants import C
from tests.constants import TEST_PLANTMOVIE_PATH


class PendingUpload(BaseModel):
    """Real MinIO/DynamoDB state for one pending movie upload."""

    movie_id: str
    bucket: str
    durable_key: str
    durable_urn: str
    staging_key: str
    staging_urn: str
    movie_data: bytes


def object_created_event(*, bucket, key, size, event_id="event-1"):
    """Return a representative native S3 Object Created EventBridge envelope."""
    return {
        "version": "0",
        "id": event_id,
        "detail-type": "Object Created",
        "source": "aws.s3",
        "account": "111122223333",
        "time": "2026-07-24T20:00:00Z",
        "region": "us-east-1",
        "resources": [f"arn:aws:s3:::{bucket}"],
        "detail": {
            "version": "0",
            "event-version": "1.0",
            "bucket": {"name": bucket},
            "object": {
                "key": key,
                "size": size,
                "etag": "test-etag",
                "sequencer": "0000000000000001",
            },
            "reason": "PutObject",
        },
    }


def create_pending_upload(new_course, *, deployment_id="event-test",
                          expected_size=None) -> PendingUpload:
    """Create a pending movie row and its exact staging object."""
    movie_data = Path(TEST_PLANTMOVIE_PATH).read_bytes()
    movie_id = odb.create_new_movie(
        user_id=new_course[odb.USER_ID],
        course_id=new_course[odb.COURSE_ID],
        title="EventBridge upload",
        description="integration test",
        upload_bytes_expected=expected_size or len(movie_data),
    )
    durable_key = s3_presigned.movie_object_key(
        deployment_id=deployment_id,
        course_id=new_course[odb.COURSE_ID],
        movie_id=movie_id,
    )
    staging_key = s3_presigned.upload_staging_object_key(
        deployment_id=deployment_id,
        course_id=new_course[odb.COURSE_ID],
        movie_id=movie_id,
    )
    bucket = C.DEFAULT_LOCAL_BUCKET
    durable_urn = s3_presigned.make_urn(object_name=durable_key, bucket=bucket)
    staging_urn = s3_presigned.make_urn(object_name=staging_key, bucket=bucket)
    new_course["ddbo"].update_movie(
        movie_id,
        {
            odb.MOVIE_DATA_URN: durable_urn,
            odb.UPLOAD_STAGING_URN: staging_urn,
        },
        touch_activity=False,
    )
    s3_presigned.s3_client().put_object(
        Bucket=bucket,
        Key=staging_key,
        Body=movie_data,
        Metadata={"fpm": "30"},
    )
    return PendingUpload(
        movie_id=movie_id,
        bucket=bucket,
        durable_key=durable_key,
        durable_urn=durable_urn,
        staging_key=staging_key,
        staging_urn=staging_urn,
        movie_data=movie_data,
    )


def test_eventbridge_upload_moves_object_processes_metadata_and_logs(
        new_course, monkeypatch):
    ddbo = new_course["ddbo"]
    deployment_id = "event-test"
    monkeypatch.setenv(C.PLANTTRACER_STACK_NAME, deployment_id)
    monkeypatch.setenv("TRACING_QUEUE_MODE", "local")
    pending = create_pending_upload(new_course, deployment_id=deployment_id)
    event = object_created_event(
        bucket=pending.bucket,
        key=pending.staging_key,
        size=len(pending.movie_data),
    )
    local_queue.start_worker(processor=lambda_tracing_handler.process_local_queue_message)
    try:
        completed = main.process_eventbridge_event(event)
        assert completed["total_bytes"] == len(pending.movie_data)
        deadline = time.time() + 10
        while time.time() < deadline:
            movie = ddbo.get_movie(pending.movie_id)
            if movie.get(odb.RESIZED_AT):
                break
            time.sleep(0.05)
        assert movie[odb.MOVIE_STATUS] == odb.MOVIE_STATE_READY
        assert movie[odb.TOTAL_FRAMES] > 0
        assert movie[odb.WIDTH] > 0
        assert movie[odb.HEIGHT] > 0
        assert movie[odb.MOVIE_DATA_URN] == pending.durable_urn
        assert movie[odb.UPLOAD_EVENT_ID] == "event-1"
        assert int(s3_presigned.s3_client().head_object(
            Bucket=pending.bucket,
            Key=pending.durable_key,
        )["ContentLength"]) == len(pending.movie_data)
        with pytest.raises(ClientError):
            s3_presigned.s3_client().head_object(
                Bucket=pending.bucket,
                Key=pending.staging_key,
            )

        duplicate_event = object_created_event(
            bucket=pending.bucket,
            key=pending.staging_key,
            size=len(pending.movie_data),
            event_id="event-2",
        )
        duplicate = upload_event.process_upload_event(duplicate_event)
        assert duplicate.uploaded_at == completed["uploaded_at"]
        completed_log_id = (
            f"{pending.movie_id}:{C.LOG_EVENT_MOVIE_RESIZE_COMPLETED}"
        )
        ddbo.logs.delete_item(Key={odb.LOG_ID: completed_log_id})
        movie_glue.process_uploaded_movie(movie_id=pending.movie_id)
        logs = ddbo.logs.scan(
            FilterExpression=Attr(odb.MOVIE_ID).eq(pending.movie_id),
        )["Items"]
        assert len(logs) == 3
        assert {entry["event_type"] for entry in logs} == {
            C.LOG_EVENT_MOVIE_UPLOAD_COMPLETED,
            C.LOG_EVENT_MOVIE_RESIZE_STARTED,
            C.LOG_EVENT_MOVIE_RESIZE_COMPLETED,
        }
        upload_log = next(
            entry
            for entry in logs
            if entry["event_type"] == C.LOG_EVENT_MOVIE_UPLOAD_COMPLETED
        )
        assert upload_log["event_id"] == "event-1"
    finally:
        local_queue.stop_worker()
        odb_movie_data.purge_movie(movie_id=pending.movie_id)


def test_eventbridge_upload_rejects_another_stack(monkeypatch):
    monkeypatch.setenv(C.PLANTTRACER_STACK_NAME, "prod")
    event = object_created_event(
        bucket=C.DEFAULT_LOCAL_BUCKET,
        key="uploads/dev/course/movie.mov",
        size=10,
    )
    with pytest.raises(ValueError, match="does not belong"):
        upload_event.process_upload_event(event)


def test_eventbridge_upload_rejects_another_bucket(monkeypatch):
    monkeypatch.setenv(C.PLANTTRACER_STACK_NAME, "prod")
    event = object_created_event(
        bucket="another-bucket",
        key="uploads/prod/course/movie.mov",
        size=10,
    )
    with pytest.raises(ValueError, match="bucket does not match"):
        upload_event.process_upload_event(event)


@pytest.mark.parametrize(
    ("key", "message"),
    (
        ("uploads/prod/course/movie/extra.mov", "valid movie ID"),
        ("uploads/prod/movie.mov", "too few path components"),
        ("uploads/prod/course/movie.mp4", "end in .mov"),
    ),
)
def test_eventbridge_upload_rejects_noncanonical_keys(monkeypatch, key, message):
    monkeypatch.setenv(C.PLANTTRACER_STACK_NAME, "prod")
    event = object_created_event(
        bucket=C.DEFAULT_LOCAL_BUCKET,
        key=key,
        size=10,
    )
    with pytest.raises(ValueError, match=message):
        upload_event.process_upload_event(event)


def test_eventbridge_upload_rejects_event_and_expected_size_mismatches(
        new_course, monkeypatch):
    monkeypatch.setenv(C.PLANTTRACER_STACK_NAME, "event-test")
    pending = create_pending_upload(new_course, expected_size=1)
    try:
        wrong_event = object_created_event(
            bucket=pending.bucket,
            key=pending.staging_key,
            size=len(pending.movie_data) + 1,
        )
        with pytest.raises(ValueError, match="EventBridge object size"):
            upload_event.process_upload_event(wrong_event)

        exact_event = object_created_event(
            bucket=pending.bucket,
            key=pending.staging_key,
            size=len(pending.movie_data),
        )
        with pytest.raises(ValueError, match="does not match expected size"):
            upload_event.process_upload_event(exact_event)
    finally:
        odb_movie_data.purge_movie(movie_id=pending.movie_id)
        s3_presigned.s3_client().delete_object(
            Bucket=pending.bucket,
            Key=pending.staging_key,
        )


def test_eventbridge_upload_rejects_a_missing_movie(monkeypatch):
    monkeypatch.setenv(C.PLANTTRACER_STACK_NAME, "event-test")
    event = object_created_event(
        bucket=C.DEFAULT_LOCAL_BUCKET,
        key="uploads/event-test/course/m00000000-0000-0000-0000-000000000000.mov",
        size=10,
    )
    with pytest.raises(odb.InvalidMovie_Id):
        upload_event.process_upload_event(event)


def test_eventbridge_upload_rejects_a_staging_urn_mismatch(new_course, monkeypatch):
    monkeypatch.setenv(C.PLANTTRACER_STACK_NAME, "event-test")
    pending = create_pending_upload(new_course)
    new_course["ddbo"].update_movie(
        pending.movie_id,
        {odb.UPLOAD_STAGING_URN: pending.staging_urn + ".wrong"},
        touch_activity=False,
    )
    event = object_created_event(
        bucket=pending.bucket,
        key=pending.staging_key,
        size=len(pending.movie_data),
    )
    try:
        with pytest.raises(ValueError, match="does not match the pending movie"):
            upload_event.process_upload_event(event)
    finally:
        odb_movie_data.purge_movie(movie_id=pending.movie_id)
        s3_presigned.s3_client().delete_object(
            Bucket=pending.bucket,
            Key=pending.staging_key,
        )


def test_eventbridge_retry_recovers_when_copy_preceded_database_update(
        new_course, monkeypatch):
    monkeypatch.setenv(C.PLANTTRACER_STACK_NAME, "event-test")
    pending = create_pending_upload(new_course)
    client = s3_presigned.s3_client()
    client.copy_object(
        Bucket=pending.bucket,
        Key=pending.durable_key,
        CopySource={"Bucket": pending.bucket, "Key": pending.staging_key},
        MetadataDirective="COPY",
    )
    event = object_created_event(
        bucket=pending.bucket,
        key=pending.staging_key,
        size=len(pending.movie_data),
    )
    try:
        completed = upload_event.process_upload_event(event)
        assert completed.total_bytes == len(pending.movie_data)
        assert new_course["ddbo"].get_movie(pending.movie_id)[odb.UPLOADED_AT]
        with pytest.raises(ClientError):
            client.head_object(Bucket=pending.bucket, Key=pending.staging_key)
    finally:
        odb_movie_data.purge_movie(movie_id=pending.movie_id)
