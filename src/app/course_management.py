"""Reusable course and course-administrator management service operations."""

from collections import defaultdict
import uuid

from pydantic import BaseModel

from . import mailer
from . import odb
from .constants import C, logger
from .odb import ADMINS_FOR_COURSE, COURSE_ID, COURSE_NAME, EMAIL, USER_ID, USER_NAME, DDBO
from .schema import AdminCourse, Course, CourseAdmin, User

EXCLUSIVE_START_KEY = 'ExclusiveStartKey'
ITEMS = 'Items'
LAST_EVALUATED_KEY = 'LastEvaluatedKey'


class AdminCreateResult(BaseModel):
    admin_user: User
    added_courses: list[Course]
    api_key: str | None = None


class CourseCreateResult(BaseModel):
    course: Course
    admin_user: User
    api_key: str | None = None
    created: bool


class DemoCourseResult(BaseModel):
    course: Course
    admin_user: User
    demo_user: User
    demo_api_key: str
    created: bool


def generate_course_key():
    """Return a short registration key for a newly created course."""
    return uuid.uuid4().hex[:8]


def scan_table_items(table):
    """Yield every item from a DynamoDB table resource scan."""
    response = table.scan()
    yield from response.get(ITEMS, [])
    while response.get(LAST_EVALUATED_KEY):
        response = table.scan(**{EXCLUSIVE_START_KEY: response[LAST_EVALUATED_KEY]})
        yield from response.get(ITEMS, [])


def list_admins():
    """Return all course administrators and the courses they administer."""
    ddbo = DDBO()
    courses_by_admin: dict[str, list[AdminCourse]] = defaultdict(list)

    for course in scan_table_items(ddbo.courses):
        admin_course = AdminCourse(
            course_id=course[COURSE_ID],
            course_name=course.get(COURSE_NAME) or "",
        )
        for user_id in course.get(ADMINS_FOR_COURSE, []):
            courses_by_admin[user_id].append(admin_course)

    admins = []
    for user_id, courses in courses_by_admin.items():
        try:
            user = ddbo.get_user(user_id)
        except odb.InvalidUser_Id:
            logger.warning("course admin user_id %s is missing from users table", user_id)
            continue
        admins.append(CourseAdmin(
            user_id=user_id,
            email=user.get(EMAIL, ""),
            user_name=user.get(USER_NAME, ""),
            courses=sorted(courses, key=lambda course: (course.course_name, course.course_id)),
        ))
    return sorted(admins, key=lambda admin: (admin.user_name.casefold(), admin.email.casefold(), admin.user_id))


def admin_create_for_courses(*, admin_email, admin_name, course_ids,
                             planttracer_endpoint=None, send_email=True):
    """Create/register a course administrator and add them to selected courses."""
    if not admin_email:
        raise ValueError("admin_email is required")
    if not admin_name:
        raise ValueError("admin_name is required")
    if not course_ids:
        raise ValueError("at least one course_id is required")
    if send_email and not planttracer_endpoint:
        raise ValueError("planttracer_endpoint is required when send_email=True")

    admin_user = None
    added_courses = []
    ddbo = DDBO()
    for course_id in course_ids:
        course_dict = odb.lookup_course_by_id(course_id=course_id)
        if admin_user is None:
            try:
                admin_user_dict = ddbo.get_user_email(admin_email)
            except odb.InvalidUser_Email:
                user_result = odb.register_email(
                    email=admin_email,
                    user_name=admin_name,
                    course_id=course_id,
                    admin=True,
                )
                admin_user_dict = ddbo.get_user(user_result[USER_ID])
            else:
                odb.add_course_admin(admin_id=admin_user_dict[USER_ID], course_id=course_id)
                admin_user_dict = ddbo.get_user(admin_user_dict[USER_ID])
        else:
            odb.add_course_admin(admin_id=admin_user.user_id, course_id=course_id)
            admin_user_dict = ddbo.get_user(admin_user.user_id)
        admin_user = User(**admin_user_dict)
        added_courses.append(Course(**course_dict))

    api_key = None
    if send_email:
        api_key = odb.get_first_api_key_for_user(admin_user.user_id)
        if api_key is None:
            api_key = odb.make_new_api_key(email=admin_email)
        for course in added_courses:
            mailer.send_course_created_email(
                to_addr=admin_email,
                course_name=course.course_name or course.course_id,
                course_id=course.course_id,
                planttracer_endpoint=planttracer_endpoint,
                api_key=api_key,
            )
    return AdminCreateResult(admin_user=admin_user, added_courses=added_courses, api_key=api_key)


def create_course_with_admin(*, course_id, course_name, admin_email, admin_name,
                             max_enrollment=C.DEFAULT_MAX_ENROLLMENT,
                             planttracer_endpoint=None, send_email=True):
    """Create or confirm a course and ensure a course administrator is attached."""
    if not course_id:
        raise ValueError("course_id is required")
    if not course_name:
        raise ValueError("course_name is required")
    created = False
    try:
        course_dict = odb.lookup_course_by_id(course_id=course_id)
        if course_dict.get(COURSE_NAME) != course_name:
            raise ValueError(
                f"course {course_id} already exists as {course_dict.get(COURSE_NAME)!r}, "
                f"not {course_name!r}"
            )
    except odb.InvalidCourse_Id:
        odb.create_course(
            course_id=course_id,
            course_key=generate_course_key(),
            course_name=course_name,
            max_enrollment=max_enrollment,
        )
        created = True

    admin_result = admin_create_for_courses(
        admin_email=admin_email,
        admin_name=admin_name,
        course_ids=[course_id],
        planttracer_endpoint=planttracer_endpoint,
        send_email=send_email,
    )
    course = Course(**odb.lookup_course_by_id(course_id=course_id))
    return CourseCreateResult(
        course=course,
        admin_user=admin_result.admin_user,
        api_key=admin_result.api_key,
        created=created,
    )


def ensure_demo_course(*, course_id, course_name, admin_email, admin_name,
                       demo_user_email, demo_user_name,
                       max_enrollment=2):
    """Ensure the demo course, its admin, and the demo-mode user/API key exist."""
    course_result = create_course_with_admin(
        course_id=course_id,
        course_name=course_name,
        admin_email=admin_email,
        admin_name=admin_name,
        max_enrollment=max_enrollment,
        send_email=False,
    )
    demo_user_result = odb.register_email(
        email=demo_user_email,
        user_name=demo_user_name,
        course_id=course_id,
    )
    demo_user = User(**DDBO().get_user(demo_user_result[USER_ID]))
    demo_api_key = odb.make_new_api_key_for_user_id(user_id=demo_user.user_id, demo_user=True)
    return DemoCourseResult(
        course=course_result.course,
        admin_user=course_result.admin_user,
        demo_user=demo_user,
        demo_api_key=demo_api_key,
        created=course_result.created,
    )
