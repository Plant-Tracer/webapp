"""Resolve an authenticated request's course without conflating it with a profile default."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel

from . import odb


class CourseContextMode(str, Enum):
    READ = "read"
    MUTATION = "mutation"


class CourseContext(BaseModel):
    requested_course_id: str | None
    effective_course_id: str
    default_course_id: str | None
    source: Literal["request", "default", "fallback"]
    fallback_reason: str | None = None


class CourseContextError(RuntimeError):
    """Base class for errors resolving a request course."""


class CourseAccessDenied(CourseContextError):
    """The requested course exists but is not authorized for this user."""


class StaleCourseContext(CourseContextError):
    """A mutation named a course that no longer exists."""


class CourseContextConflict(CourseContextError):
    """A request's course does not match the addressed resource."""


class CourseSetupRequired(CourseContextError):
    """The user has no existing course membership to use."""


def _existing_membership_ids(user) -> list[str]:
    return [course.course_id for course in odb.course_choices_for_user(user)]


def resolve_course_context(
        *, user, requested_course_id: str | None, mode: CourseContextMode) -> CourseContext:
    """Resolve URL/API course context using membership, default, then deterministic fallback."""
    requested_course_id = (requested_course_id or "").strip() or None
    default_course_id = user.get(odb.DEFAULT_COURSE_ID)
    membership_ids = _existing_membership_ids(user)

    if requested_course_id is not None:
        if requested_course_id in membership_ids:
            return CourseContext(
                requested_course_id=requested_course_id,
                effective_course_id=requested_course_id,
                default_course_id=default_course_id,
                source="request",
            )
        try:
            odb.lookup_course_by_id(course_id=requested_course_id)
        except odb.InvalidCourse_Id:
            if mode == CourseContextMode.MUTATION:
                raise StaleCourseContext(requested_course_id) from None
        else:
            if odb.normalize_super_role(user) in odb.SUPER_READ_ROLES and mode == CourseContextMode.READ:
                return CourseContext(
                    requested_course_id=requested_course_id,
                    effective_course_id=requested_course_id,
                    default_course_id=default_course_id,
                    source="request",
                )
            raise CourseAccessDenied(requested_course_id)

    if default_course_id in membership_ids:
        return CourseContext(
            requested_course_id=requested_course_id,
            effective_course_id=default_course_id,
            default_course_id=default_course_id,
            source="default",
            fallback_reason="requested_course_missing" if requested_course_id else None,
        )

    if membership_ids:
        return CourseContext(
            requested_course_id=requested_course_id,
            effective_course_id=membership_ids[0],
            default_course_id=default_course_id,
            source="fallback",
            fallback_reason="default_course_missing_or_invalid",
        )

    raise CourseSetupRequired(user.get(odb.USER_ID))
