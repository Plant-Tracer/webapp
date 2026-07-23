"""Read-only admin summary service."""

import base64
import binascii
import json
from enum import StrEnum

from boto3.dynamodb.conditions import Key
from pydantic import BaseModel, ValidationError

from . import odb
from .odb import (
    ADMIN_FOR_COURSES,
    COURSE_ID,
    COURSE_KEY,
    COURSE_NAME,
    DELETED,
    EMAIL,
    MAX_ENROLLMENT,
    MOVIE_ID,
    MOVIE_STATUS,
    PRIMARY_COURSE_ID,
    PUBLISHED,
    TITLE,
    USER_ID,
    USER_NAME,
    DDBO,
)

EXCLUSIVE_START_KEY = "ExclusiveStartKey"
ITEMS = "Items"
LAST_EVALUATED_KEY = "LastEvaluatedKey"
COUNT = "Count"
CONSISTENT_READ = "ConsistentRead"
KEY_CONDITION_EXPRESSION = "KeyConditionExpression"
SELECT = "Select"
DEFAULT_PAGE_LIMIT = 25
MAX_PAGE_LIMIT = 100


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


class AdminCounts(BaseModel):
    """Approximate table counts for the admin landing page."""

    courses: int
    users: int
    movies: int


class AdminCourseSummary(BaseModel):
    """Course row shown by the minimal admin interface."""

    course_id: str
    course_key: str
    course_name: str
    enrollment_count: int
    max_enrollment: int
    admin_count: int


class AdminUserCourseSummary(BaseModel):
    """Named course membership shown in an admin user row."""

    course_id: str
    course_name: str
    is_admin: bool


class AdminUserSummary(BaseModel):
    """User row shown by the minimal admin interface."""

    user_id: str
    user_name: str
    email: str
    primary_course_id: str
    super_role: str
    courses: list[AdminUserCourseSummary]


class AdminMovieSummary(BaseModel):
    """Privacy-aware movie row shown by the read-only admin interface."""

    movie_id: str
    title: str
    course_id: str
    course_name: str
    owner_name: str
    state: str
    status: str


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
    scan_kwargs = {"Limit": limit}
    exclusive_start_key = decode_restart_marker(restart_marker, key_name=key_name)
    if exclusive_start_key:
        scan_kwargs[EXCLUSIVE_START_KEY] = exclusive_start_key
    response = table.scan(**scan_kwargs)
    return response.get(ITEMS, []), encode_restart_marker(
        response.get(LAST_EVALUATED_KEY),
        key_name=key_name,
    )


def table_item_count(table) -> int:
    """Return DynamoDB's table item count without scanning the table."""
    table.load()
    return int(table.item_count or 0)


def course_name_map(table) -> dict[str, str]:
    """Return current names for all courses."""
    names = {}
    scan_kwargs = {CONSISTENT_READ: True}
    while True:
        response = table.scan(**scan_kwargs)
        for course in response.get(ITEMS, []):
            course_id = course[COURSE_ID]
            names[course_id] = course.get(COURSE_NAME) or course_id
        last_key = response.get(LAST_EVALUATED_KEY)
        if last_key is None:
            return names
        scan_kwargs[EXCLUSIVE_START_KEY] = last_key


def course_enrollment_count(table, course_id: str) -> int:
    """Count every current enrollment for a course using bounded query pages."""
    count = 0
    query_kwargs = {
        KEY_CONDITION_EXPRESSION: Key(COURSE_ID).eq(course_id),
        SELECT: "COUNT",
        CONSISTENT_READ: True,
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
        course_name=course.get(COURSE_NAME, ""),
        enrollment_count=enrollment_count,
        max_enrollment=course.get(MAX_ENROLLMENT, 0),
        admin_count=len(course.get(odb.ADMINS_FOR_COURSE, [])),
    )


def user_summary(user, *, course_names: dict[str, str]) -> AdminUserSummary:
    """Convert a DynamoDB user item into an admin summary row."""
    admin_courses = set(user.get(ADMIN_FOR_COURSES, []))
    courses = [
        AdminUserCourseSummary(
            course_id=course_id,
            course_name=course_names.get(course_id, course_id),
            is_admin=course_id in admin_courses,
        )
        for course_id in user.get(odb.COURSES, [])
    ]
    return AdminUserSummary(
        user_id=user[USER_ID],
        user_name=user.get(USER_NAME, ""),
        email=user.get(EMAIL, ""),
        primary_course_id=user.get(PRIMARY_COURSE_ID, ""),
        super_role=odb.normalize_super_role(user),
        courses=sorted(courses, key=lambda course: (course.course_name.casefold(), course.course_id)),
    )


def movie_summary(movie, *, course_names: dict[str, str]) -> AdminMovieSummary:
    """Convert a DynamoDB movie item into a privacy-aware admin row."""
    course_id = movie.get(COURSE_ID, "")
    if movie.get(DELETED, 0):
        state = "deleted"
    elif movie.get(PUBLISHED, 0):
        state = "published"
    else:
        state = "unpublished"
    return AdminMovieSummary(
        movie_id=movie[MOVIE_ID],
        title=movie.get(TITLE, ""),
        course_id=course_id,
        course_name=course_names.get(course_id, course_id),
        owner_name=movie.get(USER_NAME, ""),
        state=state,
        status=movie.get(MOVIE_STATUS) or "",
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
    course_items, next_course_marker = (scan_table_page(
        ddbo.courses,
        key_name=COURSE_ID,
        limit=page_limit,
        restart_marker=course_marker,
    ) if selected_section in (AdminSection.ALL, AdminSection.COURSES) else ([], None))
    user_items, next_user_marker = (scan_table_page(
        ddbo.users,
        key_name=USER_ID,
        limit=page_limit,
        restart_marker=user_marker,
    ) if selected_section in (AdminSection.ALL, AdminSection.USERS) else ([], None))
    movie_items, next_movie_marker = (scan_table_page(
        ddbo.movies,
        key_name=MOVIE_ID,
        limit=page_limit,
        restart_marker=movie_marker,
    ) if selected_section in (AdminSection.ALL, AdminSection.MOVIES) else ([], None))
    course_names = (course_name_map(ddbo.courses)
                    if selected_section in (AdminSection.ALL, AdminSection.USERS, AdminSection.MOVIES)
                    else {})
    return AdminSummaryResponse(
        viewer=AdminViewer(
            user_id=viewer_user[USER_ID],
            user_name=viewer_user.get(USER_NAME, ""),
            email=viewer_user.get(EMAIL, ""),
            super_role=access.super_role,
        ),
        counts=AdminCounts(
            courses=table_item_count(ddbo.courses),
            users=table_item_count(ddbo.users),
            movies=table_item_count(ddbo.movies),
        ),
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
            items=[user_summary(user, course_names=course_names) for user in user_items],
            restart_marker=next_user_marker,
        ),
        movies=AdminMoviePage(
            items=[movie_summary(movie, course_names=course_names) for movie in movie_items],
            restart_marker=next_movie_marker,
        ),
    )
