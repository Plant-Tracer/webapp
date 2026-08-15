"""
schema.py - the types we store in DynamoDB
"""

from decimal import Decimal, ROUND_HALF_UP

from typing import Any, List, Annotated, Literal
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    TypeAdapter
)

from .constants import C


def normalize_super_role_value(value):
    """Return the canonical value for current and legacy super roles."""
    if value in (None, "", 0, False):
        return "none"
    if value == "super_auditor":
        return "superauditor"
    if value == "super_admin":
        return "superadmin"
    return value


class User(BaseModel):
    """DynamoDB users table"""

    user_id: str
    email: str
    user_name: str
    created: int
    enabled: Annotated[int, Field(ge=0, le=1)]
    admin_for_courses: List[str]
    default_course_id: str | None
    default_course_name: str | None
    courses: List[str]
    super_role: Literal["none", "superauditor", "superadmin"] = "none"

    @field_validator("super_role", mode="before")
    @classmethod
    def normalize_super_role(cls, value):
        """Treat missing legacy role data as an ordinary non-super user."""
        return normalize_super_role_value(value)


# Function to validate a single prop and value using the User schema

# Assuming 'User' is imported from somewhere, e.g.:
# from .models import User


USER_ADAPTERS = {
    prop: TypeAdapter(field.annotation)
    for prop, field in User.model_fields.items()
}
def validate_user_field(prop: str, value: Any) -> Any:
    """
    Validates a single value against a specific field type from the User model.
    """
    if prop not in USER_ADAPTERS:
        raise AttributeError(f"{prop} is not a valid field of User")
    if prop == "super_role":
        value = normalize_super_role_value(value)
    return USER_ADAPTERS[prop].validate_python(value)


class UniqueEmail(BaseModel):
    """unique_emails table"""

    email: str


class ApiKey(BaseModel):
    """api_key model"""

    api_key: str
    user_id: str


class Course(BaseModel):
    """DynamoDB courses table"""

    course_id: str
    course_name: str
    course_key: str
    admins_for_course: List[str]
    max_enrollment: int
    created_at: int | None = None


class CourseUser(BaseModel):
    """CourseUser tracks if a user is registered in the course"""

    user_id: str
    course_id: str


class AdminCourse(BaseModel):
    """Course administered by a user."""

    course_id: str
    course_name: str


class DefaultCourseRequest(BaseModel):
    """Request to change the signed-in user's default course."""

    course_id: str


class CourseAdmin(BaseModel):
    """Operator-facing course administrator summary."""

    user_id: str
    email: str
    user_name: str
    courses: List[AdminCourse]


class Movie(BaseModel):
    """DynamoDB movies table"""

    movie_id: str
    title: str
    description: str
    created_at: int
    user_id: str
    user_name: str
    course_id: str
    status: str | None = None

    published: Annotated[int, Field(ge=0, le=1)]
    deleted: Annotated[int, Field(ge=0, le=1)]
    uploaded_at: int | None = None
    last_activity_at: int | None = None
    upload_bytes_expected: Annotated[int | None, Field(ge=1)] = None
    upload_staging_urn: str | None = None
    upload_event_id: str | None = None
    resize_queued_at: int | None = None
    resize_started_at: int | None = None
    resized_at: int | None = None
    # Read compatibility for DynamoDB rows created before uploaded_at replaced
    # date_uploaded. New writes must use uploaded_at.
    date_uploaded: int | None = None
    orig_movie: str | None = None
    fps: str | None = None  # encoded playback frame rate; string to avoid roundoff errors
    fpm: str | None = None  # capture interval in frames/minute (time-lapse); string to avoid roundoff
    width: Annotated[int | None, Field(ge=0, le=10000)] = None
    height: Annotated[int | None, Field(ge=0, le=10000)] = None
    trackpoint_origin: Literal["bottom-left"] | None = None

    total_frames: Annotated[int | None, Field(ge=0, le=999999)] = None
    trim_start_frame: Annotated[int | None, Field(ge=0, le=999999)] = None
    trim_end_frame: Annotated[int | None, Field(ge=0, le=999999)] = None
    total_bytes: Annotated[int | None, Field(ge=0)] = None

    movie_data_urn: str | None = None
    movie_zipfile_urn: str | None = None
    first_frame_urn: str | None = None
    processing_state: str | None = None  # unused legacy field; superseded by the status field in odb.py
    zip_frame_processing: dict | None = None  # {"total": int, "current": int}

    last_frame_tracked: Annotated[int | None, Field(ge=0)] = None
    needs_retracing: Annotated[int, Field(ge=0, le=1)] | None = None

    version: Annotated[int | None, Field(ge=0)] = None

    # Research use and attribution (see docs/Development/MOVIE_METADATA)
    # None means the user was never asked (legacy or upload without the radio buttons answered).
    research_use: Annotated[int, Field(ge=0, le=1)] | None = None
    credit_by_name: Annotated[int, Field(ge=0, le=1)] | None = None
    attribution_name: str | None = None

    # Preview rotation on upload page (0–3 × 90° CW). Applied when tracking.
    rotation: Annotated[int, Field(ge=0, lt=360)] = 0


def fix_movie_prop_value(prop, value):
    if value is None:
        return None
    if prop in C.MOVIE_PROPS_INT:
        return int(value)
    if prop in C.MOVIE_PROPS_STR:
        return str(value)
    return value


def fix_movie(movie):
    return {prop: fix_movie_prop_value(prop, value) for (prop, value) in movie.items()}


def fix_movies(movies):
    return [fix_movie(movie) for movie in movies]


class Trackpoint(BaseModel):
    """DynamoDB trackpoints table"""

    x: Decimal
    y: Decimal
    label: str
    marker_id: str | None = None
    color: str | None = None
    undeletable: bool | None = None
    frame_number: int | None = None
    status: int | None = None
    err: Decimal | None = None

    @field_validator("x", "y", "err", mode="before")
    @classmethod
    def round_to_one_decimal(cls, v):
        if v is None:
            return v
        d = Decimal(str(v))  # string conversion avoids float issues
        return d.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


class RenameMarkerRequest(BaseModel):
    """Request to rename a marker label across a movie's stored trackpoints."""

    old_label: Annotated[str, Field(min_length=1, max_length=100)]
    new_label: Annotated[str, Field(min_length=1, max_length=100)]

    @field_validator("old_label", "new_label", mode="before")
    @classmethod
    def strip_label(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class MovieFrame(BaseModel):
    """Each frame of each movie has a record"""

    movie_id: str
    frame_number: Annotated[int, Field(ge=0)]
    trackpoints: list[Trackpoint]


class LogEntry(BaseModel):
    """DynamoDB audit event."""

    log_id: str
    ipaddr: str
    user_id: str
    course_id: str
    time_t: Annotated[int, Field(ge=0)]
    event_type: str
    movie_id: str
    event_id: str | None = None
    object_key: str | None = None
    sequencer: str | None = None
    total_bytes: Annotated[int | None, Field(ge=0)] = None
    elapsed_seconds: Annotated[Decimal | None, Field(ge=0)] = None


# Function to validate a single prop and value using the Movie schema
MOVIE_ADAPTERS = {
    prop: TypeAdapter(field.annotation)
    for prop, field in Movie.model_fields.items()
}
def validate_movie_field(prop: str, value: Any) -> Any:
    """
    Validates a single value against a specific field type from the Movie model.
    """
    if prop not in MOVIE_ADAPTERS:
        raise AttributeError(f"{prop} is not a valid field of Movie")
    return MOVIE_ADAPTERS[prop].validate_python(value)
