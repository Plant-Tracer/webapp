"""Admin summary models and service operations."""

import base64
import binascii
import json
import time
from enum import StrEnum
from typing import Annotated

from boto3.dynamodb.conditions import Key
from pydantic import BaseModel, Field, ValidationError, field_validator

from . import odb, s3_presigned
from .constants import C
from .odb import (
    ADMIN_FOR_COURSES,
    COURSE_ID,
    COURSE_KEY,
    COURSE_NAME,
    CREATED,
    CREATED_AT,
    DATE_UPLOADED,
    DELETED,
    EMAIL,
    MAX_ENROLLMENT,
    MOVIE_ID,
    MOVIE_DATA_URN,
    MOVIE_STATUS,
    MOVIE_TRACED_URN,
    MOVIE_ZIPFILE_URN,
    DEFAULT_COURSE_ID,
    PUBLISHED,
    TITLE,
    TOTAL_BYTES,
    TOTAL_FRAMES,
    FPM,
    FPS,
    WIDTH,
    HEIGHT,
    DESCRIPTION,
    MOVIE_ROTATION,
    TRIM_START_FRAME,
    TRIM_END_FRAME,
    NEEDS_RETRACING,
    RESEARCH_USE,
    CREDIT_BY_NAME,
    ATTRIBUTION_NAME,
    LAST_ACTIVITY_AT,
    UPLOADED_AT,
    USER_ID,
    USER_NAME,
    DDBO,
)
from .schema import Course

EXCLUSIVE_START_KEY = "ExclusiveStartKey"
ITEMS = "Items"
LAST_EVALUATED_KEY = "LastEvaluatedKey"
COUNT = "Count"
CONSISTENT_READ = "ConsistentRead"
KEY_CONDITION_EXPRESSION = "KeyConditionExpression"
SELECT = "Select"
LIMIT = "Limit"
DEFAULT_PAGE_LIMIT = 25
MAX_PAGE_LIMIT = 100

# Product sizing assumes at most roughly 10 courses with 80 students each.
# At that scale the admin page intentionally loads complete datasets so it can
# sort them globally in the browser. MAX_PAGE_LIMIT bounds one DynamoDB/API
# request; it must not truncate the paginated result. If the installation grows
# beyond practical browser/DOM sizes, replace this design with server-side
# sorting and pagination instead of silently imposing a maximum page count.


class AdminReadDenied(RuntimeError):
    """Raised when the current user cannot read the admin interface."""


class InvalidRestartMarker(ValueError):
    """Raised when a client supplies an invalid opaque restart marker."""


class InvalidAdminSection(ValueError):
    """Raised when a client requests an unknown admin table section."""


class AdminSection(StrEnum):
    """Admin table sections that can be paged independently."""

    ALL = "all"
    COURSES = "courses"
    USERS = "users"
    MOVIES = "movies"


class StorageObjectState(StrEnum):
    """Read-only storage state shown without an object identifier."""

    PRESENT = "present"
    MISSING = "missing"
    NOT_CREATED = "not created"


class RestartMarker(BaseModel):
    """Table-bound DynamoDB restart key."""

    key_name: str
    key: dict[str, str]


class AdminViewer(BaseModel):
    """Current admin reader."""

    user_id: str
    user_name: str
    email: str
    super_role: str
    all_courses: bool
    course_ids: list[str]


class AdminCounts(BaseModel):
    """Approximate table counts for the admin landing page."""

    courses: int
    users: int
    movies: int


class AdminCourseCreateRequest(BaseModel):
    """Validated fields submitted by the superadmin course dialog."""

    course_id: Annotated[str, Field(min_length=1, max_length=200)]
    course_name: Annotated[str, Field(min_length=1, max_length=200)]
    admin_email: Annotated[str, Field(min_length=3, max_length=320)]
    admin_name: Annotated[str, Field(min_length=1, max_length=200)]

    @field_validator("course_id", "course_name", "admin_email", "admin_name", mode="before")
    @classmethod
    def strip_text(cls, value):
        """Reject fields that contain only whitespace."""
        return value.strip() if isinstance(value, str) else value


class AdminCourseAdministrator(BaseModel):
    """Administrator identity returned without credentials or memberships."""

    user_id: str
    email: str
    user_name: str


class AdminCourseCreateResponse(BaseModel):
    """Safe result returned after an admin course-creation request."""

    error: bool = False
    course: Course
    administrator: AdminCourseAdministrator
    created: bool
    email_sent: bool
    message: str


class AdminCourseSummary(BaseModel):
    """Course row shown by the minimal admin interface."""

    course_id: str
    course_key: str
    course_name: str
    enrollment_count: int
    max_enrollment: int
    admin_count: int
    created_at: int | None = None
    last_movie_activity_at: int | None = None


class AdminUserCourseSummary(BaseModel):
    """Course membership shown in an admin user row."""

    course_id: str
    is_admin: bool


class AdminUserSummary(BaseModel):
    """User row shown by the minimal admin interface."""

    user_id: str
    user_name: str
    email: str
    enabled: bool
    default_course_id: str | None
    super_role: str
    courses: list[AdminUserCourseSummary]
    created_at: int | None = None
    last_movie_activity_at: int | None = None


class AdminMovieSummary(BaseModel):
    """Privacy-aware movie row shown by the read-only admin interface."""

    movie_id: str
    title: str
    course_id: str
    user_id: str
    owner_name: str
    state: str
    status: str
    created_at: int | None = None
    uploaded_at: int | None = None
    last_activity_at: int | None = None
    total_frames: int | None = None
    total_bytes: int | None = None
    fpm: str | None = None
    has_traced_movie: bool = False
    description: str = ""
    fps: str | None = None
    width: int | None = None
    height: int | None = None
    rotation: int | None = None
    trim_start_frame: int | None = None
    trim_end_frame: int | None = None
    needs_retracing: bool = False
    research_use: int | None = None
    credit_by_name: str | None = None
    attribution_name: str | None = None


class AdminMovieMediaResponse(BaseModel):
    """Fresh signed URLs for one movie selected from the admin interface."""

    error: bool = False
    movie_id: str
    play_url: str
    traced_download_url: str | None = None


class AdminMovieStorageHealth(BaseModel):
    """Read-only storage health for one admin-visible movie."""

    error: bool = False
    movie_id: str
    original_object_state: StorageObjectState
    traced_object_state: StorageObjectState
    zip_object_state: StorageObjectState
    pending_upload_age_seconds: int | None = None


class AdminCoursePage(BaseModel):
    """Page of course rows."""

    items: list[AdminCourseSummary]
    restart_marker: str | None = None


class AdminUserPage(BaseModel):
    """Page of user rows."""

    items: list[AdminUserSummary]
    restart_marker: str | None = None


class AdminMoviePage(BaseModel):
    """Page of movie rows."""

    items: list[AdminMovieSummary]
    restart_marker: str | None = None


class AdminSummaryResponse(BaseModel):
    """Read-only admin landing-page payload."""

    error: bool = False
    viewer: AdminViewer
    counts: AdminCounts
    courses: AdminCoursePage
    users: AdminUserPage
    movies: AdminMoviePage


def bounded_limit(value) -> int:
    """Return a conservative page size for admin preview tables."""
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PAGE_LIMIT
    return max(1, min(limit, MAX_PAGE_LIMIT))


def admin_section(value) -> AdminSection:
    """Return a validated admin table section."""
    try:
        return AdminSection(value or AdminSection.ALL)
    except ValueError as exc:
        raise InvalidAdminSection("Invalid admin section") from exc


def encode_restart_marker(marker, *, key_name: str):
    """Encode a DynamoDB LastEvaluatedKey as an opaque URL-safe marker."""
    if not marker:
        return None
    marker_payload = RestartMarker(key_name=key_name, key=marker)
    marker_json = marker_payload.model_dump_json()
    return base64.urlsafe_b64encode(marker_json.encode("utf-8")).decode("ascii")


def decode_restart_marker(marker, *, key_name: str):
    """Decode an opaque restart marker from the client."""
    if not marker:
        return None
    try:
        marker_json = base64.urlsafe_b64decode(marker.encode("ascii")).decode("utf-8")
        decoded = RestartMarker.model_validate(json.loads(marker_json))
    except (
        UnicodeEncodeError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
        ValidationError,
    ) as exc:
        raise InvalidRestartMarker("Invalid restart marker") from exc
    if decoded.key_name != key_name or set(decoded.key) != {key_name}:
        raise InvalidRestartMarker("Invalid restart marker")
    return decoded.key


def scan_table_page(table, *, key_name: str, limit: int, restart_marker: str | None):
    """Return one DynamoDB scan page and the next restart marker."""
    scan_kwargs = {LIMIT: limit}
    exclusive_start_key = decode_restart_marker(restart_marker, key_name=key_name)
    if exclusive_start_key:
        scan_kwargs[EXCLUSIVE_START_KEY] = exclusive_start_key
    response = table.scan(**scan_kwargs)
    return response.get(ITEMS, []), encode_restart_marker(
        response.get(LAST_EVALUATED_KEY),
        key_name=key_name,
    )


def page_items(items, *, key_name: str, limit: int, restart_marker: str | None):
    """Page an in-memory, access-scoped result using a stable item key."""
    exclusive_start_key = decode_restart_marker(restart_marker, key_name=key_name)
    start_value = exclusive_start_key[key_name] if exclusive_start_key else None
    sorted_items = sorted(items, key=lambda item: item[key_name])
    if start_value is not None:
        sorted_items = [item for item in sorted_items if item[key_name] > start_value]
    page = sorted_items[:limit]
    next_marker = None
    if len(sorted_items) > limit:
        next_marker = encode_restart_marker(
            {key_name: page[-1][key_name]},
            key_name=key_name,
        )
    return page, next_marker


def table_item_count(table) -> int:
    """Return DynamoDB's table item count without scanning the table."""
    table.load()
    return int(table.item_count or 0)


def course_enrollment_count(table, course_id: str) -> int:
    """Count every current enrollment for a course using bounded query pages."""
    count = 0
    query_kwargs = {
        KEY_CONDITION_EXPRESSION: Key(COURSE_ID).eq(course_id),
        SELECT: "COUNT",
        CONSISTENT_READ: True,
        LIMIT: MAX_PAGE_LIMIT,
    }
    while True:
        response = table.query(**query_kwargs)
        count += int(response.get(COUNT, 0))
        last_key = response.get(LAST_EVALUATED_KEY)
        if last_key is None:
            return count
        query_kwargs[EXCLUSIVE_START_KEY] = last_key


def course_summary(course, *, enrollment_count: int) -> AdminCourseSummary:
    """Convert a DynamoDB course item into an admin summary row."""
    return AdminCourseSummary(
        course_id=course[COURSE_ID],
        course_key=course.get(COURSE_KEY, ""),
        course_name=course.get(COURSE_NAME) or course[COURSE_ID],
        enrollment_count=enrollment_count,
        max_enrollment=course.get(MAX_ENROLLMENT, 0),
        admin_count=len(course.get(odb.ADMINS_FOR_COURSE, [])),
        created_at=course.get(CREATED_AT) or course.get(CREATED),
    )


def user_summary(user, *, visible_course_ids=None) -> AdminUserSummary:
    """Convert a DynamoDB user item into an admin summary row."""
    visible_courses = set(user.get(odb.COURSES, []))
    if visible_course_ids is not None:
        visible_courses.intersection_update(visible_course_ids)
    admin_courses = set(user.get(ADMIN_FOR_COURSES, [])).intersection(visible_courses)
    courses = [
        AdminUserCourseSummary(
            course_id=course_id,
            is_admin=course_id in admin_courses,
        )
        for course_id in visible_courses
    ]
    default_course_id = odb.normalize_user_default_course(user).get(DEFAULT_COURSE_ID, "")
    if visible_course_ids is not None and default_course_id not in visible_courses:
        default_course_id = ""
    return AdminUserSummary(
        user_id=user[USER_ID],
        user_name=user.get(USER_NAME, ""),
        email=user.get(EMAIL, ""),
        enabled=bool(user.get(odb.ENABLED, 0)),
        default_course_id=default_course_id,
        super_role=odb.normalize_super_role(user),
        courses=sorted(courses, key=lambda course: course.course_id),
        created_at=user.get(CREATED),
    )


def scoped_admin_items(ddbo, course_ids):
    """Return courses, enrolled users, and movies for administered courses."""
    courses = []
    user_ids = set()
    movies_by_id = {}
    for course_id in course_ids:
        try:
            courses.append(ddbo.get_course(course_id))
        except odb.InvalidCourse_Id:
            continue
        user_ids.update(odb.course_enrollments(course_id, ddbo=ddbo))
        for movie in ddbo.get_movies_for_course_id(course_id):
            movies_by_id[movie[MOVIE_ID]] = movie
    users = []
    for user_id in user_ids:
        try:
            users.append(ddbo.get_user(user_id))
        except odb.InvalidUser_Id:
            continue
    return courses, users, list(movies_by_id.values())


def admin_visible_movie(*, viewer_user, movie_id: str):
    """Return a movie only when it is inside the viewer's admin scope."""
    access = odb.admin_read_access(viewer_user)
    if not access.allowed:
        raise AdminReadDenied(viewer_user.get(USER_ID, "unknown"))
    movie = DDBO().get_movie(movie_id)
    if access.all_courses or movie.get(COURSE_ID) in access.course_ids:
        return movie
    raise odb.UnauthorizedUser(
        f"user {viewer_user.get(USER_ID, 'unknown')} attempted to administer movie {movie_id}"
    )


def object_state(urn) -> StorageObjectState:
    """Report the state of a movie object without disclosing its URN."""
    if not urn:
        return StorageObjectState.NOT_CREATED
    try:
        exists = s3_presigned.object_exists(urn)
    except (AssertionError, RuntimeError, ValueError):
        return StorageObjectState.MISSING
    return StorageObjectState.PRESENT if exists else StorageObjectState.MISSING


def movie_summary(movie) -> AdminMovieSummary:
    """Convert a DynamoDB movie item into a privacy-aware admin row."""
    course_id = movie.get(COURSE_ID, "")
    if movie.get(DELETED, 0):
        state = "deleted"
    elif movie.get(PUBLISHED, 0):
        state = "published"
    else:
        state = "hidden"
    uploaded_at = movie.get(UPLOADED_AT) or movie.get(DATE_UPLOADED)
    created_at = movie.get(CREATED_AT)
    return AdminMovieSummary(
        movie_id=movie[MOVIE_ID],
        title=movie.get(TITLE, ""),
        course_id=course_id,
        user_id=movie.get(USER_ID, ""),
        owner_name=movie.get(USER_NAME, ""),
        state=state,
        status=movie.get(MOVIE_STATUS) or "",
        created_at=created_at,
        uploaded_at=uploaded_at,
        last_activity_at=movie.get(LAST_ACTIVITY_AT) or uploaded_at or created_at,
        total_frames=movie.get(TOTAL_FRAMES),
        total_bytes=movie.get(TOTAL_BYTES),
        fpm=movie.get(FPM),
        has_traced_movie=bool(movie.get(MOVIE_TRACED_URN)),
        description=movie.get(DESCRIPTION) or "",
        fps=movie.get(FPS),
        width=movie.get(WIDTH),
        height=movie.get(HEIGHT),
        rotation=movie.get(MOVIE_ROTATION),
        trim_start_frame=movie.get(TRIM_START_FRAME),
        trim_end_frame=movie.get(TRIM_END_FRAME),
        needs_retracing=bool(movie.get(NEEDS_RETRACING)),
        research_use=movie.get(RESEARCH_USE),
        credit_by_name=movie.get(CREDIT_BY_NAME),
        attribution_name=movie.get(ATTRIBUTION_NAME),
    )


def admin_movie_storage_health(*, viewer_user, movie_id: str,
                               now=None) -> AdminMovieStorageHealth:
    """Return storage health for one movie only after an explicit admin request."""
    movie = admin_visible_movie(viewer_user=viewer_user, movie_id=movie_id)
    created_at = movie.get(CREATED_AT)
    uploaded_at = movie.get(UPLOADED_AT) or movie.get(DATE_UPLOADED)
    pending_upload_age_seconds = None
    if not uploaded_at and created_at:
        current_time = time.time() if now is None else now
        pending_upload_age_seconds = max(0, int(current_time - int(created_at)))
    return AdminMovieStorageHealth(
        movie_id=movie_id,
        original_object_state=object_state(movie.get(MOVIE_DATA_URN)),
        traced_object_state=object_state(movie.get(MOVIE_TRACED_URN)),
        zip_object_state=object_state(movie.get(MOVIE_ZIPFILE_URN)),
        pending_upload_age_seconds=pending_upload_age_seconds,
    )


def admin_movie_media(*, viewer_user, movie_id: str) -> AdminMovieMediaResponse:
    """Return short-lived media URLs without exposing stored S3 URNs."""
    movie = admin_visible_movie(viewer_user=viewer_user, movie_id=movie_id)
    if not (movie.get(UPLOADED_AT) or movie.get(DATE_UPLOADED)):
        raise ValueError("Movie has not been uploaded")
    movie_urn = (movie.get(MOVIE_DATA_URN) or "").strip()
    if not movie_urn:
        raise ValueError("Movie data is not available")
    traced_urn = (movie.get(MOVIE_TRACED_URN) or "").strip() or None
    return AdminMovieMediaResponse(
        movie_id=movie_id,
        play_url=s3_presigned.make_signed_url(
            urn=movie_urn,
            expires=C.ADMIN_MEDIA_URL_EXPIRES_SECONDS,
        ),
        traced_download_url=(
            s3_presigned.make_signed_url(
                urn=traced_urn,
                expires=C.ADMIN_MEDIA_URL_EXPIRES_SECONDS,
                download_name=f"{movie_id}-traced.mp4",
            )
            if traced_urn else None
        ),
    )


def admin_summary(*, viewer_user, course_marker=None, user_marker=None,
                  movie_marker=None, limit=None, section=None) -> AdminSummaryResponse:
    """Return the minimal read-only admin summary payload."""
    access = odb.admin_read_access(viewer_user)
    if not access.allowed:
        raise AdminReadDenied(viewer_user.get(USER_ID, "unknown"))

    ddbo = DDBO()
    page_limit = bounded_limit(limit)
    selected_section = admin_section(section)
    visible_course_ids = None
    if access.all_courses:
        counts = AdminCounts(
            courses=table_item_count(ddbo.courses),
            users=table_item_count(ddbo.users),
            movies=table_item_count(ddbo.movies),
        )
        course_items, next_course_marker = (scan_table_page(
            ddbo.courses, key_name=COURSE_ID, limit=page_limit,
            restart_marker=course_marker,
        ) if selected_section in (AdminSection.ALL, AdminSection.COURSES) else ([], None))
        user_items, next_user_marker = (scan_table_page(
            ddbo.users, key_name=USER_ID, limit=page_limit,
            restart_marker=user_marker,
        ) if selected_section in (AdminSection.ALL, AdminSection.USERS) else ([], None))
        movie_items, next_movie_marker = (scan_table_page(
            ddbo.movies, key_name=MOVIE_ID, limit=page_limit,
            restart_marker=movie_marker,
        ) if selected_section in (AdminSection.ALL, AdminSection.MOVIES) else ([], None))
    else:
        visible_course_ids = set(access.course_ids)
        scoped_courses, scoped_users, scoped_movies = scoped_admin_items(
            ddbo, access.course_ids,
        )
        counts = AdminCounts(
            courses=len(scoped_courses),
            users=len(scoped_users),
            movies=len(scoped_movies),
        )
        course_items, next_course_marker = (page_items(
            scoped_courses, key_name=COURSE_ID, limit=page_limit,
            restart_marker=course_marker,
        ) if selected_section in (AdminSection.ALL, AdminSection.COURSES) else ([], None))
        user_items, next_user_marker = (page_items(
            scoped_users, key_name=USER_ID, limit=page_limit,
            restart_marker=user_marker,
        ) if selected_section in (AdminSection.ALL, AdminSection.USERS) else ([], None))
        movie_items, next_movie_marker = (page_items(
            scoped_movies, key_name=MOVIE_ID, limit=page_limit,
            restart_marker=movie_marker,
        ) if selected_section in (AdminSection.ALL, AdminSection.MOVIES) else ([], None))
    return AdminSummaryResponse(
        viewer=AdminViewer(
            user_id=viewer_user[USER_ID],
            user_name=viewer_user.get(USER_NAME, ""),
            email=viewer_user.get(EMAIL, ""),
            super_role=access.super_role,
            all_courses=access.all_courses,
            course_ids=list(access.course_ids),
        ),
        counts=counts,
        courses=AdminCoursePage(
            items=[
                course_summary(
                    course,
                    enrollment_count=course_enrollment_count(ddbo.course_users, course[COURSE_ID]),
                )
                for course in course_items
            ],
            restart_marker=next_course_marker,
        ),
        users=AdminUserPage(
            items=[
                user_summary(user, visible_course_ids=visible_course_ids)
                for user in user_items
            ],
            restart_marker=next_user_marker,
        ),
        movies=AdminMoviePage(
            items=[movie_summary(movie) for movie in movie_items],
            restart_marker=next_movie_marker,
        ),
    )
