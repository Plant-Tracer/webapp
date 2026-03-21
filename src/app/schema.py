"""
schema.py - the types we store in DynamoDB
"""

from decimal import Decimal, ROUND_HALF_UP

from typing import Any, List, Annotated
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    TypeAdapter
)

from .constants import C


class User(BaseModel):
    """DynamoDB users table"""

    user_id: str
    email: str
    user_name: str
    created: int
    enabled: Annotated[int, Field(ge=0, le=1)]
    admin_for_courses: List[str]
    primary_course_id: str
    primary_course_name: str
    courses: List[str]


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


class CourseUser(BaseModel):
    """CourseUser tracks if a user is registered in the course"""

    user_id: str
    course_id: str


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
    date_uploaded: int | None = None
    orig_movie: str | None = None
    fps: str | None = None  # otherwise we get roundoff errors
    width: Annotated[int | None, Field(ge=0, le=10000)] = None
    height: Annotated[int | None, Field(ge=0, le=10000)] = None

    total_frames: Annotated[int | None, Field(ge=0, le=999999)] = None
    total_bytes: Annotated[int | None, Field(ge=0)] = None

    movie_data_urn: str | None = None
    movie_zipfile_urn: str | None = None
    first_frame_urn: str | None = None
    processing_state: str | None = None  # values in odb: PROCESSING_STATE_UPLOADING, _TRACKING, _TRACKED
    zip_frame_processing: dict | None = None  # {"total": int, "current": int}

    last_frame_tracked: Annotated[int | None, Field(ge=0)] = None

    version: Annotated[int | None, Field(ge=0)] = None

    # Research use and attribution (see docs/MOVIE_METADATA)
    research_use: Annotated[int, Field(ge=0, le=1)] = 0
    credit_by_name: Annotated[int, Field(ge=0, le=1)] = 0
    attribution_name: str | None = None

    # Preview rotation on upload page (0–3 × 90° CW). Applied when tracking.
    rotation_steps: Annotated[int, Field(ge=0, le=3)] = 0


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


class MovieFrame(BaseModel):
    """Each frame of each movie has a record"""

    movie_id: str
    frame_number: Annotated[int, Field(ge=0)]
    trackpoints: list[Trackpoint]


class LogEntry(BaseModel):
    """Logs"""

    log_id: str
    ipaddr: str
    user_id: str
    course_id: str
    time_t: Annotated[int, Field(ge=0)]


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
