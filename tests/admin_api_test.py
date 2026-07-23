import pytest

from app import admin_service, apikey, odb
from app.odb import API_KEY, USER_ID

from .constants import ADMIN_EMAIL, MOVIE_TITLE


def test_admin_summary_denies_regular_user(client, new_course):
    client.set_cookie(apikey.cookie_name(), new_course[API_KEY])

    response = client.get("/api/admin/summary")

    assert response.status_code == 403
    assert response.json["error"] is True


def test_admin_summary_denies_course_admin_without_super_role(client, new_course):
    admin_api_key = odb.make_new_api_key(email=new_course[ADMIN_EMAIL])
    client.set_cookie(apikey.cookie_name(), admin_api_key)

    response = client.get("/api/admin/summary?limit=1")

    assert response.status_code == 403
    assert response.json["error"] is True


def test_admin_summary_allows_superauditor(client, new_course):
    ddbo = new_course["ddbo"]
    ddbo.update_table(ddbo.users, new_course[USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERAUDITOR})
    client.set_cookie(apikey.cookie_name(), new_course[API_KEY])

    response = client.get("/api/admin/summary?limit=1")

    assert response.status_code == 200
    payload = response.json
    assert payload["viewer"]["super_role"] == odb.SUPER_ROLE_SUPERAUDITOR


def test_admin_summary_allows_superadmin(client, new_course):
    ddbo = new_course["ddbo"]
    ddbo.update_table(ddbo.users, new_course[USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERADMIN})
    client.set_cookie(apikey.cookie_name(), new_course[API_KEY])

    response = client.get("/api/admin/summary?limit=1")

    assert response.status_code == 200
    assert response.json["viewer"]["super_role"] == odb.SUPER_ROLE_SUPERADMIN


def test_admin_summary_includes_enrollment_named_memberships_and_movies(client, new_movie):
    ddbo = new_movie["ddbo"]
    ddbo.update_table(ddbo.users, new_movie[USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERAUDITOR})
    client.set_cookie(apikey.cookie_name(), new_movie[API_KEY])

    response = client.get("/api/admin/summary")

    assert response.status_code == 200
    payload = response.json
    course = next(item for item in payload["courses"]["items"]
                  if item["course_id"] == new_movie[odb.COURSE_ID])
    assert course["enrollment_count"] == 2
    assert course["max_enrollment"] >= course["enrollment_count"]

    user = next(item for item in payload["users"]["items"]
                if item["user_id"] == new_movie[USER_ID])
    assert user["courses"] == [{
        "course_id": new_movie[odb.COURSE_ID],
        "course_name": new_movie[odb.COURSE_NAME],
        "is_admin": False,
    }]
    admin = next(item for item in payload["users"]["items"]
                 if item["email"] == new_movie[ADMIN_EMAIL])
    assert admin["courses"][0]["is_admin"] is True

    movie = next(item for item in payload["movies"]["items"]
                 if item["movie_id"] == new_movie[odb.MOVIE_ID])
    assert movie["title"] == new_movie[MOVIE_TITLE]
    assert movie["course_name"] == new_movie[odb.COURSE_NAME]
    assert movie["owner_name"] == "Course User"
    assert movie["state"] == "published"


def test_admin_summary_rejects_invalid_restart_marker(client, new_course):
    ddbo = new_course["ddbo"]
    ddbo.update_table(ddbo.users, new_course[USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERAUDITOR})
    client.set_cookie(apikey.cookie_name(), new_course[API_KEY])

    response = client.get("/api/admin/summary?course_marker=not-valid")

    assert response.status_code == 400
    assert response.json == {"error": True, "message": "Invalid restart marker"}


def test_decode_restart_marker_rejects_non_key_json():
    marker = admin_service.encode_restart_marker(
        {USER_ID: "u-test"},
        key_name=USER_ID,
    )

    with pytest.raises(admin_service.InvalidRestartMarker, match="Invalid restart marker"):
        admin_service.decode_restart_marker(marker, key_name=odb.COURSE_ID)


def test_admin_summary_rejects_marker_for_other_table(client, new_course):
    ddbo = new_course["ddbo"]
    ddbo.update_table(ddbo.users, new_course[USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERAUDITOR})
    client.set_cookie(apikey.cookie_name(), new_course[API_KEY])

    first_page = client.get("/api/admin/summary?limit=1")
    user_marker = first_page.json["users"]["restart_marker"]
    response = client.get(f"/api/admin/summary?course_marker={user_marker}")

    assert user_marker is not None
    assert response.status_code == 400
    assert response.json == {"error": True, "message": "Invalid restart marker"}


def test_admin_page_loads_for_superauditor(client, new_course):
    ddbo = new_course["ddbo"]
    ddbo.update_table(ddbo.users, new_course[USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERAUDITOR})
    client.set_cookie(apikey.cookie_name(), new_course[API_KEY])

    response = client.get("/admin")

    assert response.status_code == 200
    assert "admin.js" in response.text
    assert "Admin" in response.text


def test_admin_page_denies_course_admin_without_super_role(client, new_course):
    admin_api_key = odb.make_new_api_key(email=new_course[ADMIN_EMAIL])
    client.set_cookie(apikey.cookie_name(), admin_api_key)

    response = client.get("/admin")

    assert response.status_code == 403
