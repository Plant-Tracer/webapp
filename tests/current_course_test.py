import uuid

import pytest

import dbutil

from app import apikey, course_context, odb
from app.odb import API_KEY, COURSE_ID, COURSE_NAME, DEFAULT_COURSE_ID, MOVIE_ID, USER_ID

from .constants import USER_EMAIL


def additional_course_id():
    return f"switch-{uuid.uuid4()}"


def test_course_picker_lists_memberships_and_changes_default(client, new_course):
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

        response = client.patch("/api/default-course", json={COURSE_ID: new_course[COURSE_ID]})
        assert response.status_code == 200
        assert response.json["course"] == {
            COURSE_ID: new_course[COURSE_ID],
            COURSE_NAME: new_course[COURSE_NAME],
        }
        user = new_course["ddbo"].get_user(new_course[USER_ID])
        assert user[DEFAULT_COURSE_ID] == new_course[COURSE_ID]
        assert user[odb.DEFAULT_COURSE_NAME] == new_course[COURSE_NAME]
    finally:
        odb.unregister_from_course(course_id=course_id, user_id=new_course[USER_ID])
        odb.delete_course(course_id=course_id)


def test_default_course_rejects_nonmembership(client, new_course):
    course_id = additional_course_id()
    odb.create_course(
        course_id=course_id,
        course_name="Not My Course",
        course_key=f"key-{uuid.uuid4()}",
    )
    try:
        client.set_cookie(apikey.cookie_name(), new_course[API_KEY])
        response = client.patch("/api/default-course", json={COURSE_ID: course_id})

        assert response.status_code == 400
        assert response.json == {"error": True, "message": "Course membership required"}
        user = new_course["ddbo"].get_user(new_course[USER_ID])
        assert user[DEFAULT_COURSE_ID] == new_course[COURSE_ID]
    finally:
        odb.delete_course(course_id=course_id)


def test_default_course_requires_authentication(client, new_course):
    response = client.patch("/api/default-course", json={COURSE_ID: new_course[COURSE_ID]})

    assert response.status_code == 403


def test_current_course_is_a_compatibility_alias(client, new_course):
    client.set_cookie(apikey.cookie_name(), new_course[API_KEY])

    response = client.patch("/api/current-course", json={COURSE_ID: new_course[COURSE_ID]})

    assert response.status_code == 200
    assert response.json["course"][COURSE_ID] == new_course[COURSE_ID]


def test_movie_list_without_course_uses_default_profile_course(client, new_movie):
    course_id = additional_course_id()
    odb.create_course(
        course_id=course_id,
        course_name="Second Course",
        course_key=f"key-{uuid.uuid4()}",
    )
    second_movie_id = None
    try:
        odb.register_email(
            email=new_movie[USER_EMAIL],
            user_name="Course User",
            course_id=course_id,
        )
        second_movie_id = odb.create_new_movie(
            user_id=new_movie[USER_ID],
            course_id=course_id,
            title="Second-course movie",
            description="Regression fixture",
        )
        client.set_cookie(apikey.cookie_name(), new_movie[API_KEY])

        change = client.patch("/api/default-course", json={COURSE_ID: course_id})
        assert change.status_code == 200

        response = client.post("/api/list-movies")

        assert response.status_code == 200
        assert [movie[MOVIE_ID] for movie in response.json["movies"]] == [second_movie_id]
    finally:
        if second_movie_id is not None:
            new_movie["ddbo"].movies.delete_item(Key={MOVIE_ID: second_movie_id})
        odb.unregister_from_course(course_id=course_id, user_id=new_movie[USER_ID])
        odb.delete_course(course_id=course_id)


def test_explicit_course_overrides_default_without_changing_profile(client, new_movie):
    course_id = additional_course_id()
    odb.create_course(
        course_id=course_id,
        course_name="Second Course",
        course_key=f"key-{uuid.uuid4()}",
    )
    second_movie_id = None
    try:
        odb.register_email(
            email=new_movie[USER_EMAIL],
            user_name="Course User",
            course_id=course_id,
        )
        second_movie_id = odb.create_new_movie(
            user_id=new_movie[USER_ID],
            course_id=course_id,
            title="Second-course movie",
            description="Course-context fixture",
        )
        client.set_cookie(apikey.cookie_name(), new_movie[API_KEY])

        response = client.post(
            "/api/list-movies",
            data={COURSE_ID: new_movie[COURSE_ID]},
        )

        assert response.status_code == 200
        assert [movie[MOVIE_ID] for movie in response.json["movies"]] == [new_movie[MOVIE_ID]]
        user = new_movie["ddbo"].get_user(new_movie[USER_ID])
        assert user[DEFAULT_COURSE_ID] == course_id
    finally:
        if second_movie_id is not None:
            new_movie["ddbo"].movies.delete_item(Key={MOVIE_ID: second_movie_id})
        odb.unregister_from_course(course_id=course_id, user_id=new_movie[USER_ID])
        odb.delete_course(course_id=course_id)


def test_missing_read_course_falls_back_to_default(client, new_movie):
    client.set_cookie(apikey.cookie_name(), new_movie[API_KEY])

    response = client.post(
        "/api/list-movies",
        data={COURSE_ID: f"deleted-{uuid.uuid4()}"},
    )

    assert response.status_code == 200
    assert [movie[MOVIE_ID] for movie in response.json["movies"]] == [new_movie[MOVIE_ID]]
    assert response.json["course_context"]["source"] == "default"
    assert response.json["course_context"]["fallback_reason"] == "requested_course_missing"


def test_existing_course_without_membership_is_forbidden(client, new_movie):
    course_id = additional_course_id()
    odb.create_course(
        course_id=course_id,
        course_name="Not My Course",
        course_key=f"key-{uuid.uuid4()}",
    )
    try:
        client.set_cookie(apikey.cookie_name(), new_movie[API_KEY])

        response = client.post("/api/list-movies", data={COURSE_ID: course_id})

        assert response.status_code == 403
    finally:
        odb.delete_course(course_id=course_id)


def test_movie_api_rejects_mismatched_course_context(client, new_movie):
    course_id = additional_course_id()
    odb.create_course(
        course_id=course_id,
        course_name="Second Course",
        course_key=f"key-{uuid.uuid4()}",
    )
    try:
        odb.register_email(
            email=new_movie[USER_EMAIL],
            user_name="Course User",
            course_id=course_id,
        )
        client.set_cookie(apikey.cookie_name(), new_movie[API_KEY])

        response = client.post(
            "/api/get-movie-metadata",
            data={MOVIE_ID: new_movie[MOVIE_ID], COURSE_ID: course_id},
        )

        assert response.status_code == 409
        assert response.json["message"] == "Course context does not match the requested resource"
    finally:
        odb.unregister_from_course(course_id=course_id, user_id=new_movie[USER_ID])
        odb.delete_course(course_id=course_id)


def test_default_course_field_migration_is_dry_run_then_one_way(new_course):
    ddbo = new_course["ddbo"]
    user_id = new_course[USER_ID]
    ddbo.update_table(
        ddbo.users,
        user_id,
        {
            odb.DEFAULT_COURSE_ID: None,
            odb.DEFAULT_COURSE_NAME: None,
            odb.LEGACY_PRIMARY_COURSE_ID: new_course[COURSE_ID],
            odb.LEGACY_PRIMARY_COURSE_NAME: new_course[COURSE_NAME],
        },
    )

    dry_run = dbutil.migrate_default_course_fields(commit=False, ddbo=ddbo)
    raw_user = ddbo.users.get_item(Key={USER_ID: user_id}, ConsistentRead=True)["Item"]
    assert dry_run.changed == 1
    assert odb.LEGACY_PRIMARY_COURSE_ID in raw_user
    assert odb.DEFAULT_COURSE_ID not in raw_user

    committed = dbutil.migrate_default_course_fields(commit=True, ddbo=ddbo)
    raw_user = ddbo.users.get_item(Key={USER_ID: user_id}, ConsistentRead=True)["Item"]
    assert committed.changed == 1
    assert raw_user[odb.DEFAULT_COURSE_ID] == new_course[COURSE_ID]
    assert raw_user[odb.DEFAULT_COURSE_NAME] == new_course[COURSE_NAME]
    assert odb.LEGACY_PRIMARY_COURSE_ID not in raw_user
    assert odb.LEGACY_PRIMARY_COURSE_NAME not in raw_user


def test_stale_explicit_mutation_course_is_rejected(new_course):
    user = new_course["ddbo"].get_user(new_course[USER_ID])

    with pytest.raises(course_context.StaleCourseContext):
        course_context.resolve_course_context(
            user=user,
            requested_course_id=f"deleted-{uuid.uuid4()}",
            mode=course_context.CourseContextMode.MUTATION,
        )
