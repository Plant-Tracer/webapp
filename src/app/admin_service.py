"""Read-only admin summary service."""

import base64
import json

from pydantic import BaseModel

from . import odb
from .odb import (
    ADMIN_FOR_COURSES,
    COURSE_ID,
    COURSE_NAME,
    EMAIL,
    MAX_ENROLLMENT,
    PRIMARY_COURSE_ID,
    USER_ID,
    USER_NAME,
    DDBO,
)

EXCLUSIVE_START_KEY = "ExclusiveStartKey"
ITEMS = "Items"
LAST_EVALUATED_KEY = "LastEvaluatedKey"
DEFAULT_PAGE_LIMIT = 25
MAX_PAGE_LIMIT = 100


class AdminReadDenied(RuntimeError):
    """Raised when the current user cannot read the admin interface."""


class AdminViewer(BaseModel):
    """Current admin reader."""

    user_id: str
    user_name: str
    email: str
    super_role: str
    bootstrap_course_admin: bool


class AdminCounts(BaseModel):
    """Approximate table counts for the admin landing page."""

    courses: int
    users: int
    movies: int


class AdminCourseSummary(BaseModel):
    """Course row shown by the minimal admin interface."""

    course_id: str
    course_name: str
    max_enrollment: int
    admin_count: int


class AdminUserSummary(BaseModel):
    """User row shown by the minimal admin interface."""

    user_id: str
    user_name: str
    email: str
    primary_course_id: str
    super_role: str
    course_count: int
    admin_course_count: int


class AdminCoursePage(BaseModel):
    """Page of course rows."""

    items: list[AdminCourseSummary]
    restart_marker: str | None = None


class AdminUserPage(BaseModel):
    """Page of user rows."""

    items: list[AdminUserSummary]
    restart_marker: str | None = None


class AdminSummaryResponse(BaseModel):
    """Read-only admin landing-page payload."""

    error: bool = False
    viewer: AdminViewer
    counts: AdminCounts
    courses: AdminCoursePage
    users: AdminUserPage


def bounded_limit(value) -> int:
    """Return a conservative page size for admin preview tables."""
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PAGE_LIMIT
    return max(1, min(limit, MAX_PAGE_LIMIT))


def encode_restart_marker(marker):
    """Encode a DynamoDB LastEvaluatedKey as an opaque URL-safe marker."""
    if not marker:
        return None
    marker_json = json.dumps(marker, separators=(",", ":"), default=str)
    return base64.urlsafe_b64encode(marker_json.encode("utf-8")).decode("ascii")


def decode_restart_marker(marker):
    """Decode an opaque restart marker from the client."""
    if not marker:
        return None
    marker_json = base64.urlsafe_b64decode(marker.encode("ascii")).decode("utf-8")
    return json.loads(marker_json)


def scan_table_page(table, *, limit: int, restart_marker: str | None):
    """Return one DynamoDB scan page and the next restart marker."""
    scan_kwargs = {"Limit": limit}
    exclusive_start_key = decode_restart_marker(restart_marker)
    if exclusive_start_key:
        scan_kwargs[EXCLUSIVE_START_KEY] = exclusive_start_key
    response = table.scan(**scan_kwargs)
    return response.get(ITEMS, []), encode_restart_marker(response.get(LAST_EVALUATED_KEY))


def table_item_count(table) -> int:
    """Return DynamoDB's table item count without scanning the table."""
    table.load()
    return int(table.item_count or 0)


def course_summary(course) -> AdminCourseSummary:
    """Convert a DynamoDB course item into an admin summary row."""
    return AdminCourseSummary(
        course_id=course[COURSE_ID],
        course_name=course.get(COURSE_NAME, ""),
        max_enrollment=course.get(MAX_ENROLLMENT, 0),
        admin_count=len(course.get(odb.ADMINS_FOR_COURSE, [])),
    )


def user_summary(user) -> AdminUserSummary:
    """Convert a DynamoDB user item into an admin summary row."""
    return AdminUserSummary(
        user_id=user[USER_ID],
        user_name=user.get(USER_NAME, ""),
        email=user.get(EMAIL, ""),
        primary_course_id=user.get(PRIMARY_COURSE_ID, ""),
        super_role=odb.normalize_super_role(user),
        course_count=len(user.get(odb.COURSES, [])),
        admin_course_count=len(user.get(ADMIN_FOR_COURSES, [])),
    )


def admin_summary(*, viewer_user, course_marker=None, user_marker=None, limit=None) -> AdminSummaryResponse:
    """Return the minimal read-only admin summary payload."""
    access = odb.admin_read_access(viewer_user)
    if not access.allowed:
        raise AdminReadDenied(viewer_user.get(USER_ID, "unknown"))

    ddbo = DDBO()
    page_limit = bounded_limit(limit)
    course_items, next_course_marker = scan_table_page(
        ddbo.courses,
        limit=page_limit,
        restart_marker=course_marker,
    )
    user_items, next_user_marker = scan_table_page(
        ddbo.users,
        limit=page_limit,
        restart_marker=user_marker,
    )
    return AdminSummaryResponse(
        viewer=AdminViewer(
            user_id=viewer_user[USER_ID],
            user_name=viewer_user.get(USER_NAME, ""),
            email=viewer_user.get(EMAIL, ""),
            super_role=access.super_role,
            bootstrap_course_admin=access.bootstrap_course_admin,
        ),
        counts=AdminCounts(
            courses=table_item_count(ddbo.courses),
            users=table_item_count(ddbo.users),
            movies=table_item_count(ddbo.movies),
        ),
        courses=AdminCoursePage(
            items=[course_summary(course) for course in course_items],
            restart_marker=next_course_marker,
        ),
        users=AdminUserPage(
            items=[user_summary(user) for user in user_items],
            restart_marker=next_user_marker,
        ),
    )
