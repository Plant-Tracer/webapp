import uuid

from app import apikey, odb
from app.odb import API_KEY, COURSE_ID, COURSE_NAME, PRIMARY_COURSE_ID, USER_ID

from .constants import USER_EMAIL


def additional_course_id():
    return f"switch-{uuid.uuid4()}"


def test_current_course_picker_lists_memberships_and_switches(client, new_course):
    course_id = additional_course_id()
    course_name = "Second Course"
    odb.create_course(
        course_id=course_id,
        course_name=course_name,
        course_key=f"key-{uuid.uuid4()}",
    )
    try:
        odb.register_email(
            email=new_course[USER_EMAIL],
            user_name="Course User",
            course_id=course_id,
        )
        client.set_cookie(apikey.cookie_name(), new_course[API_KEY])

        page = client.get("/")
        assert page.status_code == 200
        assert 'id="current-course-select"' in page.text
        assert new_course[COURSE_NAME] in page.text
        assert course_name in page.text

        response = client.patch("/api/current-course", json={COURSE_ID: new_course[COURSE_ID]})
        assert response.status_code == 200
        assert response.json["course"] == {
            COURSE_ID: new_course[COURSE_ID],
            COURSE_NAME: new_course[COURSE_NAME],
        }
        user = new_course["ddbo"].get_user(new_course[USER_ID])
        assert user[PRIMARY_COURSE_ID] == new_course[COURSE_ID]
        assert user[odb.PRIMARY_COURSE_NAME] == new_course[COURSE_NAME]
    finally:
        odb.unregister_from_course(course_id=course_id, user_id=new_course[USER_ID])
        odb.delete_course(course_id=course_id)


def test_current_course_rejects_nonmembership(client, new_course):
    course_id = additional_course_id()
    odb.create_course(
        course_id=course_id,
        course_name="Not My Course",
        course_key=f"key-{uuid.uuid4()}",
    )
    try:
        client.set_cookie(apikey.cookie_name(), new_course[API_KEY])
        response = client.patch("/api/current-course", json={COURSE_ID: course_id})

        assert response.status_code == 400
        assert response.json == {"error": True, "message": "Course membership required"}
        user = new_course["ddbo"].get_user(new_course[USER_ID])
        assert user[PRIMARY_COURSE_ID] == new_course[COURSE_ID]
    finally:
        odb.delete_course(course_id=course_id)


def test_current_course_requires_authentication(client, new_course):
    response = client.patch("/api/current-course", json={COURSE_ID: new_course[COURSE_ID]})

    assert response.status_code == 403
