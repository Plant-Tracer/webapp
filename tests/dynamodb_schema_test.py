"""Live DynamoDB Local round trips for every persisted Pydantic contract."""

from collections import defaultdict
from decimal import Decimal
import uuid

from pydantic import BaseModel, TypeAdapter, ValidationError

from app import odb, schema
from app.schema import (
    AdminCourse,
    ApiKey,
    Course,
    CourseAdmin,
    CourseUser,
    DefaultCourseRequest,
    LogEntry,
    Movie,
    MovieAnalysisLock,
    MovieFrame,
    MovieTraceLock,
    RenameMarkerRequest,
    Trackpoint,
    TrackpointCoordinateMetadata,
    UniqueEmail,
    User,
)


PERSISTED_MODELS = {
    ApiKey,
    Course,
    CourseUser,
    LogEntry,
    Movie,
    MovieAnalysisLock,
    MovieFrame,
    MovieTraceLock,
    Trackpoint,
    UniqueEmail,
    User,
}
NON_PERSISTED_SCHEMA_MODELS = {
    AdminCourse,
    CourseAdmin,
    DefaultCourseRequest,
    RenameMarkerRequest,
    TrackpointCoordinateMetadata,
}


def nullable_fields(model_type):
    """Return every model field whose annotation accepts None."""
    nullable = set()
    for name, field in model_type.model_fields.items():
        try:
            TypeAdapter(field.annotation).validate_python(None)
        except ValidationError:
            continue
        nullable.add(name)
    return nullable


def schema_models():
    """Return every Pydantic model declared in the DynamoDB schema module."""
    return {
        value
        for value in vars(schema).values()
        if isinstance(value, type)
        and value is not BaseModel
        and issubclass(value, BaseModel)
        and value.__module__ == schema.__name__
    }


def test_persisted_pydantic_models_round_trip_through_dynamodb_local(local_ddb):
    """Store and load every model and both states of every nullable field."""
    assert schema_models() == PERSISTED_MODELS | NON_PERSISTED_SCHEMA_MODELS
    token = uuid.uuid4().hex
    course_ids = (f"nullable-{token}", f"populated-{token}")
    course_keys = (f"null-{token}", f"full-{token}")
    user_ids = (f"u-null-{token}", f"u-full-{token}")
    emails = (f"null-{token}@example.test", f"full-{token}@example.test")
    movie_ids = (f"m-null-{token}", f"m-full-{token}")
    log_ids = (f"log-null-{token}", f"log-full-{token}")
    api_key_value = f"a{token}"
    validated_models = set()
    nullable_states = defaultdict(set)

    def record(model):
        model_type = type(model)
        validated_models.add(model_type)
        for field_name in nullable_fields(model_type):
            nullable_states[(model_type, field_name)].add(
                getattr(model, field_name) is None
            )
        return model

    def load(table, key, model_type):
        item = table.get_item(Key=key, ConsistentRead=True)["Item"]
        return record(model_type.model_validate(item))

    courses = (
        Course(
            course_id=course_ids[0], course_name="Nullable course",
            course_key=course_keys[0], admins_for_course=[],
            max_enrollment=1, created_at=None,
        ),
        Course(
            course_id=course_ids[1], course_name="Populated course",
            course_key=course_keys[1], admins_for_course=[user_ids[1]],
            max_enrollment=2, created_at=1,
        ),
    )
    users = (
        User(
            user_id=user_ids[0], email=emails[0], user_name="Nullable user",
            created=1, enabled=1, admin_for_courses=[],
            default_course_id=None, default_course_name=None, courses=[],
        ),
        User(
            user_id=user_ids[1], email=emails[1], user_name="Populated user",
            created=2, enabled=1, admin_for_courses=[course_ids[1]],
            default_course_id=course_ids[1], default_course_name="Populated course",
            courses=[course_ids[1]], super_role="superauditor",
        ),
    )
    movies = (
        Movie(
            movie_id=movie_ids[0], title="Nullable movie", description="",
            created_at=1, user_id=user_ids[0], user_name="Nullable user",
            course_id=course_ids[0], published=1, deleted=0,
        ),
        Movie(
            movie_id=movie_ids[1], title="Populated movie", description="details",
            created_at=2, user_id=user_ids[1], user_name="Populated user",
            course_id=course_ids[1], published=1, deleted=0,
            status="ready", tracing_failed_at=3,
            tracing_failure_summary="previous failure", trace_job_id="old-job",
            tracing_state="queued", tracing_started_at=4,
            tracing_heartbeat_at=5, tracing_expires_at=6,
            tracing_started_by_user_id=user_ids[1],
            tracing_started_by_user_name="Populated user",
            analysis_lease_id="old-lease", analysis_started_at=7,
            analysis_heartbeat_at=8, analysis_expires_at=9,
            analysis_started_by_user_id=user_ids[1],
            analysis_started_by_user_name="Populated user",
            uploaded_at=10, last_activity_at=11, upload_bytes_expected=12,
            upload_staging_urn="s3://test/staging", upload_event_id="event-1",
            resize_queued_at=13, resize_started_at=14, resized_at=15,
            date_uploaded=16, orig_movie=movie_ids[0], fps="30", fpm="2.5",
            width=640, height=480, frame_height_px=480, trackpoint_origin="bottom-left",
            total_frames=120, trim_start_frame=1, trim_end_frame=119,
            total_bytes=1234, movie_data_urn="s3://test/movie.mp4",
            movie_zipfile_urn="s3://test/movie.zip", first_frame_urn="s3://test/frame.jpg",
            processing_state="complete", zip_frame_processing={"current": 1, "total": 1},
            last_frame_tracked=119, needs_retracing=1, version=2,
            research_use=1, credit_by_name=1,
            attribution_name="Alyssa P. Hacker", rotation=90,
        ),
    )
    trackpoints = (
        Trackpoint(x="10.1", y="20.2", label="Nullable marker"),
        Trackpoint(
            x="30.3", y="40.4", label="Populated marker", marker_id="marker-1",
            color="orange", undeletable=True, frame_number=1, status=1, err="0.5",
        ),
    )
    frames = (
        MovieFrame(movie_id=movie_ids[1], frame_number=0, trackpoints=[trackpoints[0]]),
        MovieFrame(movie_id=movie_ids[1], frame_number=1, trackpoints=[trackpoints[1]]),
    )
    logs = (
        LogEntry(
            log_id=log_ids[0], ipaddr="127.0.0.1", user_id=user_ids[0],
            course_id=course_ids[0], time_t=1, event_type="nullable",
            movie_id=movie_ids[0],
        ),
        LogEntry(
            log_id=log_ids[1], ipaddr="127.0.0.2", user_id=user_ids[1],
            course_id=course_ids[1], time_t=2, event_type="populated",
            movie_id=movie_ids[1], target_user_id=user_ids[0], event_id="event-2",
            object_key="movie.mp4", sequencer="001", total_bytes=1234,
            elapsed_seconds=Decimal("1.25"), trace_job_id="trace-job",
            error_type="RuntimeError", error_summary="test failure",
            old_super_role="none", new_super_role="superauditor",
        ),
    )

    try:
        for course in courses:
            local_ddb.put_course(course.model_dump())
            load(local_ddb.courses, {odb.COURSE_ID: course.course_id}, Course)

        for user in users:
            local_ddb.put_user(user.model_dump())
            load(local_ddb.users, {odb.USER_ID: user.user_id}, User)
            load(local_ddb.unique_emails, {odb.EMAIL: user.email}, UniqueEmail)

        api_key = ApiKey(api_key=api_key_value, user_id=user_ids[1])
        local_ddb.put_api_key_dict(api_key.model_dump())
        load(local_ddb.api_keys, {odb.API_KEY: api_key_value}, ApiKey)

        enrollment = CourseUser(user_id=user_ids[1], course_id=course_ids[1])
        local_ddb.course_users.put_item(Item=enrollment.model_dump())
        load(local_ddb.course_users, {
            odb.COURSE_ID: course_ids[1], odb.USER_ID: user_ids[1],
        }, CourseUser)

        for movie in movies:
            local_ddb.put_movie(movie.model_dump())
            load(local_ddb.movies, {odb.MOVIE_ID: movie.movie_id}, Movie)

        for frame in frames:
            local_ddb.put_movie_frame(frame.model_dump(exclude_none=True))
            stored_frame = load(local_ddb.movie_frames, {
                odb.MOVIE_ID: frame.movie_id,
                odb.FRAME_NUMBER: frame.frame_number,
            }, MovieFrame)
            for trackpoint in stored_frame.trackpoints:
                record(trackpoint)

        for entry in logs:
            local_ddb.logs.put_item(Item=entry.model_dump(exclude_none=True))
            load(local_ddb.logs, {odb.LOG_ID: entry.log_id}, LogEntry)

        movie_item = local_ddb.get_movie(movie_ids[1])
        analysis_lock = local_ddb.acquire_movie_analysis_lock(
            movie=movie_item, started_by_user_id=user_ids[1],
            started_by_user_name="Populated user",
        )
        assert record(local_ddb.get_active_movie_analysis_lock(movie_ids[1])) == analysis_lock
        assert local_ddb.release_movie_analysis_lock(
            movie_id=movie_ids[1], lease_id=analysis_lock.lease_id,
            user_id=user_ids[1],
        )

        trace_lock = local_ddb.acquire_movie_trace_lock(
            movie=local_ddb.get_movie(movie_ids[1]),
            started_by_user_id=user_ids[1], started_by_user_name="Populated user",
        )
        assert record(local_ddb.get_active_movie_trace_lock(movie_ids[1])) == trace_lock
        local_ddb.finish_movie_trace(
            movie_id=movie_ids[1], job_id=trace_lock.job_id,
            updates={odb.MOVIE_STATUS: odb.MOVIE_STATE_READY},
        )

        missing_states = {
            f"{model_type.__name__}.{field_name}":
                nullable_states[(model_type, field_name)]
            for model_type in PERSISTED_MODELS
            for field_name in nullable_fields(model_type)
            if nullable_states[(model_type, field_name)] != {False, True}
        }
        assert validated_models == PERSISTED_MODELS
        assert missing_states == {}
    finally:
        for log_id in log_ids:
            local_ddb.logs.delete_item(Key={odb.LOG_ID: log_id})
        for frame in frames:
            local_ddb.movie_frames.delete_item(Key={
                odb.MOVIE_ID: frame.movie_id, odb.FRAME_NUMBER: frame.frame_number,
            })
        for movie_id in movie_ids:
            local_ddb.movies.delete_item(Key={odb.MOVIE_ID: movie_id})
        local_ddb.course_users.delete_item(Key={
            odb.COURSE_ID: course_ids[1], odb.USER_ID: user_ids[1],
        })
        local_ddb.api_keys.delete_item(Key={odb.API_KEY: api_key_value})
        for user_id, email in zip(user_ids, emails):
            local_ddb.users.delete_item(Key={odb.USER_ID: user_id})
            local_ddb.unique_emails.delete_item(Key={odb.EMAIL: email})
        for course_id in course_ids:
            local_ddb.courses.delete_item(Key={odb.COURSE_ID: course_id})
