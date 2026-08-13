"""
Test the various functions in the database involving user creation.
"""

import uuid
import copy

from app import course_management
from app import odb
from app import odbmaint
from app.constants import C,logger
from app.odb import (
    ExistingCourse_Id, UserExists, COURSE_ID, COURSE_NAME, API_KEY, COURSE_KEY,
    USER_ID, USERS, COURSES, ADMINS_FOR_COURSE, MAX_ENROLLMENT, DDBO,
)
from dbutil import DEMO_COURSE_ID,DEMO_COURSE_NAME,DEFAULT_ADMIN_EMAIL,DEFAULT_ADMIN_NAME,DEMO_USER_EMAIL,DEMO_USER_NAME

# Fixtures are imported in conftest.py
from .constants import ADMIN_EMAIL



################################################################
## fixture tests
################################################################

def test_ddb(local_ddb):
    logger.info("test_ddb local_ddb=%s",local_ddb)

def test_ddb2(local_ddb):
    logger.info("test_ddb local_ddb=%s",local_ddb)

def test_new_course(new_course):
    cfg = copy.copy(new_course)
    course_key = cfg[COURSE_KEY]
    admin_email = cfg[ADMIN_EMAIL]
    logger.info("Created course %s admin_email %s", course_key, admin_email )

    # Check course lookup functions
    c1 = odb.lookup_course_by_key(course_key = cfg[COURSE_KEY])
    c2 = odb.lookup_course_by_id(course_id = cfg[COURSE_ID])
    assert c1 == c2
    assert c1[ COURSE_KEY  ] == cfg[COURSE_KEY]


# Make sure that there is a demo user
def test_demo_user(new_course):
    #cfg = copy.copy(new_course)
    try:
        odbmaint.create_course(course_id  = DEMO_COURSE_ID,
                               course_name = DEMO_COURSE_NAME,
                               course_key = str(uuid.uuid4())[0:8],
                               admin_email = DEFAULT_ADMIN_EMAIL,
                               admin_name  = DEFAULT_ADMIN_NAME,
                               max_enrollment = 2)
    except ExistingCourse_Id:
        pass

    try:
        odb.register_email(DEMO_USER_EMAIL, DEMO_USER_NAME, course_id=DEMO_COURSE_ID)
    except UserExists:
        pass

    # Create the demo user to own the demo movies
    odb.make_new_api_key(email=DEMO_USER_EMAIL, demo_user=True)        # Give the demo user an API key
    userdict = odb.validate_api_key( C.DEMO_MODE_API_KEY )
    assert 'created' in userdict


def test_ensure_demo_course_is_idempotent(local_ddb):
    del local_ddb

    result = course_management.ensure_demo_course(
        course_id=DEMO_COURSE_ID,
        course_name=DEMO_COURSE_NAME,
        admin_email=DEFAULT_ADMIN_EMAIL,
        admin_name=DEFAULT_ADMIN_NAME,
        demo_user_email=DEMO_USER_EMAIL,
        demo_user_name=DEMO_USER_NAME,
        max_enrollment=2,
    )
    retry = course_management.ensure_demo_course(
        course_id=DEMO_COURSE_ID,
        course_name=DEMO_COURSE_NAME,
        admin_email=DEFAULT_ADMIN_EMAIL,
        admin_name=DEFAULT_ADMIN_NAME,
        demo_user_email=DEMO_USER_EMAIL,
        demo_user_name=DEMO_USER_NAME,
        max_enrollment=2,
    )

    assert retry.created is False
    assert retry.course.course_id == result.course.course_id
    assert retry.admin_user.email == DEFAULT_ADMIN_EMAIL
    assert retry.demo_user.email == DEMO_USER_EMAIL
    assert retry.demo_api_key == C.DEMO_MODE_API_KEY
    userdict = odb.validate_api_key(C.DEMO_MODE_API_KEY)
    assert userdict[USER_ID] == retry.demo_user.user_id


def test_add_remove_user_and_admin(new_course):
    """Tests creating a new user and adding them to the course as an admin"""
    cfg = copy.copy(new_course)
    #course_key = cfg[COURSE_KEY]

    for admin in range(0,2):
        new_email = f"some-user{str(uuid.uuid4())[0:8]}@company.com"
        user_id = odb.register_email(email=new_email,
                                  course_key=cfg[COURSE_KEY],
                                  user_name='User Name',
                                  admin = admin)['user_id']

        logger.info("generated admin_email=%s user_id=%s",new_email, user_id)
        course_id = odb.lookup_course_by_key(course_key = cfg[COURSE_KEY])['course_id']

        if not admin:
            assert not odb.check_course_admin(user_id=user_id, course_id=course_id)
            odb.add_course_admin(admin_id = user_id, course_id = course_id)
            assert odb.check_course_admin(user_id=user_id, course_id=course_id)
            odb.remove_course_admin(admin_id = user_id, course_id = course_id)
            assert not odb.check_course_admin(user_id=user_id, course_id=course_id)

        if admin:
            assert odb.check_course_admin(user_id=user_id, course_id=course_id)
            odb.add_course_admin(admin_id = user_id, course_id = course_id)
            assert odb.check_course_admin(user_id=user_id, course_id=course_id)
            odb.remove_course_admin(admin_id = user_id, course_id = course_id)
            assert not odb.check_course_admin(user_id=user_id, course_id=course_id)
        odb.delete_user(user_id=user_id)


def test_course_list(client, new_course):
    cfg        = copy.copy(new_course)
    #user_email = cfg[USER_EMAIL]
    api_key    = cfg[API_KEY]

    user_dict = odb.validate_api_key(api_key)
    user_id   = user_dict['user_id']

    recs1 = odb.list_users_courses(user_id=user_id)
    users1 = recs1['users']

    matches = [user for user in users1 if user['user_id']==user_id]
    assert len(matches)>0

    # Make sure that there is an admin in the course (it's the user)
    recs2 = course_management.list_admins()
    assert len(recs2)>=1        # we could do a better test
    matching_admins = [admin for admin in recs2 if admin.email == cfg[ADMIN_EMAIL]]
    assert len(matching_admins) == 1
    assert matching_admins[0].user_name == "Course Admin"
    assert any(course.course_id == cfg[COURSE_ID] for course in matching_admins[0].courses)

    # Make sure that the endpoint works
    response = client.post('/api/list-users',
                           data = {'api_key': api_key})

    res = response.get_json()
    assert res['error'] is False
    users2 = res['users']

    # Regular user is not an admin: they see only themselves
    assert len(users2) == 1
    assert users1[0]['user_name'] == users2[0]['user_name']


def test_admin_create_for_courses(new_course):
    cfg = copy.copy(new_course)
    admin_email = f"new-admin-{str(uuid.uuid4())[0:8]}@company.com"

    result = course_management.admin_create_for_courses(
        admin_email=admin_email,
        admin_name="New Course Admin",
        course_ids=[cfg[COURSE_ID]],
        send_email=False,
    )

    assert result.api_key is None
    assert result.admin_user.email == admin_email
    assert result.admin_user.user_name == "New Course Admin"
    assert [course.course_id for course in result.added_courses] == [cfg[COURSE_ID]]
    assert odb.check_course_admin(user_id=result.admin_user.user_id, course_id=cfg[COURSE_ID])
    listed_admins = course_management.list_admins()
    matching_admins = [admin for admin in listed_admins if admin.email == admin_email]
    assert len(matching_admins) == 1
    assert any(course.course_id == cfg[COURSE_ID] for course in matching_admins[0].courses)

    odb.remove_course_admin(course_id=cfg[COURSE_ID], admin_id=result.admin_user.user_id)
    odb.delete_user(user_id=result.admin_user.user_id)


def test_create_course_with_existing_admin_is_idempotent(new_course):
    cfg = copy.copy(new_course)
    course_id = "CourseCreate-" + str(uuid.uuid4())[0:8]
    course_name = "Course Create Test"

    result = course_management.create_course_with_admin(
        course_id=course_id,
        course_name=course_name,
        admin_email=cfg[ADMIN_EMAIL],
        admin_name="Course Admin",
        send_email=False,
    )

    assert result.created is True
    assert result.api_key is None
    assert result.course.course_id == course_id
    assert result.course.course_name == course_name
    assert result.admin_user.email == cfg[ADMIN_EMAIL]
    assert odb.check_course_admin(user_id=result.admin_user.user_id, course_id=course_id)

    retry = course_management.create_course_with_admin(
        course_id=course_id,
        course_name=course_name,
        admin_email=cfg[ADMIN_EMAIL],
        admin_name="Course Admin",
        send_email=False,
    )

    assert retry.created is False
    assert retry.api_key is None
    assert retry.course.course_id == course_id
    assert retry.admin_user.user_id == result.admin_user.user_id
    assert odb.check_course_admin(user_id=result.admin_user.user_id, course_id=course_id)

    odb.remove_course_admin(course_id=course_id, admin_id=result.admin_user.user_id)
    odb.delete_course(course_id=course_id)


def test_list_admins_tolerates_null_course_name(new_course):
    cfg = copy.copy(new_course)
    ddbo = DDBO()
    course_id = "NullName-" + str(uuid.uuid4())[0:8]
    ddbo.courses.put_item(Item={
        COURSE_ID: course_id,
        COURSE_NAME: None,
        COURSE_KEY: "key-" + str(uuid.uuid4())[0:8],
        ADMINS_FOR_COURSE: [cfg["admin_id"]],
        MAX_ENROLLMENT: 50,
    })

    try:
        admins = course_management.list_admins()
        matching_admins = [admin for admin in admins if admin.user_id == cfg["admin_id"]]
        assert len(matching_admins) == 1
        matching_courses = [
            course
            for course in matching_admins[0].courses
            if course.course_id == course_id
        ]
        assert len(matching_courses) == 1
        assert matching_courses[0].course_name == ""
    finally:
        ddbo.courses.delete_item(Key={COURSE_ID: course_id})


def test_first_last_login_times(client, new_course):
    """first/last fields in list-users response should be populated after a user has authenticated."""
    admin_email = new_course[ADMIN_EMAIL]
    admin_id    = new_course['admin_id']

    # Give the admin an api_key and use it (triggers first_used_at / last_used_at recording)
    admin_api_key = odb.make_new_api_key(email=admin_email)
    odb.validate_api_key(admin_api_key)   # simulates a login

    recs = odb.list_users_courses(user_id=admin_id)
    admin_user = next(u for u in recs['users'] if u[USER_ID] == admin_id)
    assert admin_user.get('first') is not None, "first should be set after login"
    assert admin_user.get('last') is not None, "last should be set after login"


def test_admin_sees_all_enrolled_users(client, new_course):
    """An admin calling list-users should see every user enrolled in their course,
    not just themselves (regression test for issue #955)."""
    admin_id    = new_course['admin_id']
    admin_email = new_course[ADMIN_EMAIL]
    user_id     = new_course[USER_ID]

    # Give the admin an API key so they can call the endpoint
    admin_api_key = odb.make_new_api_key(email=admin_email)

    # list_users_courses via the ODB layer
    recs = odb.list_users_courses(user_id=admin_id)
    returned_ids = {u[USER_ID] for u in recs['users']}
    assert admin_id in returned_ids, "admin should see themselves"
    assert user_id in returned_ids, "admin should see the enrolled regular user"

    # Verify the same through the HTTP endpoint
    response = client.post('/api/list-users', data={'api_key': admin_api_key})
    res = response.get_json()
    assert res['error'] is False
    http_ids = {u['user_id'] for u in res['users']}
    assert admin_id in http_ids
    assert user_id in http_ids


def test_admin_two_courses(client, new_course):
    """An admin for two courses sees only the explicitly selected course."""
    admin_id    = new_course['admin_id']
    admin_email = new_course[ADMIN_EMAIL]
    user1_id    = new_course[USER_ID]        # enrolled in course 1 via fixture

    # Create a second course and enroll a distinct user in it
    course2_id  = 'TestCourse2-' + str(uuid.uuid4())[0:8]
    course2_key = 'key2-' + str(uuid.uuid4())[0:8]
    odb.create_course(course_id=course2_id, course_name='Second Course', course_key=course2_key)

    user2_dict  = odb.register_email(email=f'user2-{uuid.uuid4()!s:.8}@example.com',
                                     user_name='Course2 User',
                                     course_id=course2_id)
    user2_id    = user2_dict[USER_ID]

    # Make the fixture admin an admin of the second course too
    odb.add_course_admin(admin_id=admin_id, course_id=course2_id)

    try:
        recs         = odb.list_users_courses(user_id=admin_id)
        returned_ids = {u[USER_ID] for u in recs['users']}
        course_ids   = {c['course_id'] for c in recs['courses']}

        # All three users (admin + one per course) should be present
        assert admin_id in returned_ids, "admin should see themselves"
        assert user1_id in returned_ids, "admin should see user from course 1"
        assert user2_id in returned_ids, "admin should see user from course 2"

        # Both courses should be in the courses list
        assert new_course[COURSE_ID] in course_ids, "course 1 should be in courses list"
        assert course2_id in course_ids,             "course 2 should be in courses list"

        # The browser API is course-scoped even though the underlying ODB helper
        # retains its aggregate form for maintenance callers.
        admin_api_key = odb.make_new_api_key(email=admin_email)
        response1 = client.post('/api/list-users', data={
            'api_key': admin_api_key,
            COURSE_ID: new_course[COURSE_ID],
        })
        res1 = response1.get_json()
        assert res1['error'] is False
        assert user1_id in {u[USER_ID] for u in res1[USERS]}
        assert user2_id not in {u[USER_ID] for u in res1[USERS]}
        assert [course[COURSE_ID] for course in res1[COURSES]] == [new_course[COURSE_ID]]

        response2 = client.post('/api/list-users', data={
            'api_key': admin_api_key,
            COURSE_ID: course2_id,
        })
        res2 = response2.get_json()
        assert res2['error'] is False
        assert user2_id in {u[USER_ID] for u in res2[USERS]}
        assert user1_id not in {u[USER_ID] for u in res2[USERS]}
        assert [course[COURSE_ID] for course in res2[COURSES]] == [course2_id]

    finally:
        odb.remove_course_admin(admin_id=admin_id, course_id=course2_id)
        odb.delete_user(user_id=user2_id, purge_movies=True)
        odb.delete_course(course_id=course2_id)
