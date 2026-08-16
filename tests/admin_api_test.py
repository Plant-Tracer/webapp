import time
import uuid
from urllib.parse import parse_qs, urlparse

import pytest

from app import admin_service, apikey, odb, s3_presigned
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


def test_admin_summary_includes_enrollment_memberships_and_movies(client, new_movie):
    ddbo = new_movie["ddbo"]
    ddbo.update_table(ddbo.users, new_movie[USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERAUDITOR})
    client.set_cookie(apikey.cookie_name(), new_movie[API_KEY])

    response = client.get("/api/admin/summary")

    assert response.status_code == 200
    payload = response.json
    course = next(item for item in payload["courses"]["items"]
                  if item["course_id"] == new_movie[odb.COURSE_ID])
    assert course["course_key"] == new_movie[odb.COURSE_KEY]
    assert course["enrollment_count"] == 2
    assert course["max_enrollment"] >= course["enrollment_count"]
    assert course["created_at"] is not None

    user = next(item for item in payload["users"]["items"]
                if item["user_id"] == new_movie[USER_ID])
    assert user["courses"] == [{
        "course_id": new_movie[odb.COURSE_ID],
        "is_admin": False,
    }]
    assert user["created_at"] is not None
    admin = next(item for item in payload["users"]["items"]
                 if item["email"] == new_movie[ADMIN_EMAIL])
    assert admin["courses"][0]["is_admin"] is True

    movie = next(item for item in payload["movies"]["items"]
                 if item["movie_id"] == new_movie[odb.MOVIE_ID])
    assert movie["title"] == new_movie[MOVIE_TITLE]
    assert movie["course_id"] == new_movie[odb.COURSE_ID]
    assert movie["owner_name"] == "Course User"
    assert movie["state"] == "published"
    assert movie["user_id"] == new_movie[USER_ID]
    assert movie["created_at"] is not None
    assert movie["uploaded_at"] is not None
    assert movie["last_activity_at"] >= movie["uploaded_at"]
    assert movie["total_bytes"] > 0
    assert movie["description"] == "Description"
    assert movie["needs_retracing"] is False
    assert "original_object_state" not in movie
    assert "research_use" in movie


def test_admin_summary_reports_hidden_movie(client, new_movie):
    ddbo = new_movie["ddbo"]
    ddbo.update_table(ddbo.users, new_movie[USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERAUDITOR})
    ddbo.update_movie(new_movie[odb.MOVIE_ID], {odb.PUBLISHED: 0})
    client.set_cookie(apikey.cookie_name(), new_movie[API_KEY])

    response = client.get("/api/admin/summary")

    assert response.status_code == 200
    movie = next(item for item in response.json["movies"]["items"]
                 if item["movie_id"] == new_movie[odb.MOVIE_ID])
    assert movie["state"] == "hidden"


def test_admin_movie_storage_health_reports_missing_derived_objects_and_pending_age(client, new_movie):
    ddbo = new_movie["ddbo"]
    ddbo.update_table(ddbo.users, new_movie[USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERAUDITOR})
    client.set_cookie(apikey.cookie_name(), new_movie[API_KEY])
    movie_id = new_movie[odb.MOVIE_ID]
    movie = ddbo.get_movie(movie_id)
    ddbo.update_movie(movie_id, {odb.MOVIE_DATA_URN: "not-an-s3-urn"})
    summary_response = client.get("/api/admin/summary?section=movies")
    assert summary_response.status_code == 200
    ddbo.update_movie(movie_id, {odb.MOVIE_DATA_URN: movie[odb.MOVIE_DATA_URN]})
    traced_urn = s3_presigned.traced_movie_urn(movie_data_urn=movie[odb.MOVIE_DATA_URN])
    zip_urn = s3_presigned.analysis_zip_urn(movie_data_urn=movie[odb.MOVIE_DATA_URN])
    ddbo.update_movie(movie_id, {
        odb.MOVIE_TRACED_URN: traced_urn,
        odb.MOVIE_ZIPFILE_URN: zip_urn,
    })

    response = client.get(f"/api/admin/movies/{movie_id}/storage-health")

    assert response.status_code == 200
    assert response.json["original_object_state"] == "present"
    assert response.json["traced_object_state"] == "missing"
    assert response.json["zip_object_state"] == "missing"
    assert "urn" not in str(response.json)

    pending_movie_id = odb.create_new_movie(
        user_id=new_movie[USER_ID],
        course_id=new_movie[odb.COURSE_ID],
        title="Pending storage health test",
        description="No S3 object has been uploaded",
    )
    ddbo.update_movie(pending_movie_id, {odb.CREATED_AT: int(time.time()) - 90})
    pending_response = client.get(f"/api/admin/movies/{pending_movie_id}/storage-health")
    assert pending_response.json["original_object_state"] == "not created"
    assert pending_response.json["pending_upload_age_seconds"] >= 90

    pending_movie = ddbo.get_movie(pending_movie_id)
    assert admin_service.admin_movie_storage_health(
        viewer_user=ddbo.get_user(new_movie[USER_ID]),
        movie_id=pending_movie_id,
        now=0,
    ).pending_upload_age_seconds == 0
    assert pending_movie[odb.CREATED_AT] > 0


def test_admin_movie_media_returns_fresh_urls(client, new_movie):
    ddbo = new_movie["ddbo"]
    ddbo.update_table(
        ddbo.users,
        new_movie[USER_ID],
        {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERAUDITOR},
    )
    client.set_cookie(apikey.cookie_name(), new_movie[API_KEY])

    response = client.get(f"/api/admin/movies/{new_movie[odb.MOVIE_ID]}/media")

    assert response.status_code == 200
    assert response.json["movie_id"] == new_movie[odb.MOVIE_ID]
    assert response.json["play_url"].startswith("http")
    assert response.json["traced_download_url"] is None

    movie = ddbo.get_movie(new_movie[odb.MOVIE_ID])
    ddbo.update_movie(
        new_movie[odb.MOVIE_ID],
        {odb.MOVIE_TRACED_URN: movie[odb.MOVIE_DATA_URN]},
    )
    traced_response = client.get(f"/api/admin/movies/{new_movie[odb.MOVIE_ID]}/media")
    disposition = parse_qs(
        urlparse(traced_response.json["traced_download_url"]).query
    )["response-content-disposition"][0]
    assert disposition == f'attachment; filename="{new_movie[odb.MOVIE_ID]}-traced.mp4"'


def test_admin_movie_media_requires_super_role(client, new_movie):
    response = client.get(f"/api/admin/movies/{new_movie[odb.MOVIE_ID]}/media")
    assert response.status_code == 403
    assert response.json == {"error": True, "message": "Invalid api_key"}

    client.set_cookie(apikey.cookie_name(), new_movie[API_KEY])
    response = client.get(f"/api/admin/movies/{new_movie[odb.MOVIE_ID]}/media")
    assert response.status_code == 403
    assert response.json == {"error": True, "message": "Admin read access required"}


def test_admin_movie_media_reports_missing_movie(client, new_course):
    ddbo = new_course["ddbo"]
    ddbo.update_table(
        ddbo.users,
        new_course[USER_ID],
        {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERAUDITOR},
    )
    client.set_cookie(apikey.cookie_name(), new_course[API_KEY])

    missing_movie_id = f"m{uuid.uuid4()}"
    response = client.get(f"/api/admin/movies/{missing_movie_id}/media")

    assert response.status_code == 404
    assert response.json == {"error": True, "message": "Movie not found"}


def test_admin_movie_media_distinguishes_pending_from_missing_data(client, new_course):
    ddbo = new_course["ddbo"]
    ddbo.update_table(
        ddbo.users,
        new_course[USER_ID],
        {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERAUDITOR},
    )
    client.set_cookie(apikey.cookie_name(), new_course[API_KEY])
    movie_id = odb.create_new_movie(
        user_id=new_course[USER_ID],
        course_id=new_course[odb.COURSE_ID],
        title="Pending admin media test",
        description="No S3 object has been uploaded",
    )

    pending_response = client.get(f"/api/admin/movies/{movie_id}/media")
    assert pending_response.status_code == 409
    assert pending_response.json == {"error": True, "message": "Movie has not been uploaded"}

    ddbo.update_movie(movie_id, {odb.UPLOADED_AT: int(time.time())})
    missing_data_response = client.get(f"/api/admin/movies/{movie_id}/media")
    assert missing_data_response.status_code == 409
    assert missing_data_response.json == {"error": True, "message": "Movie data is not available"}


def test_course_summary_uses_id_when_name_is_empty():
    summary = admin_service.course_summary(
        {
            odb.COURSE_ID: "course-without-name",
            odb.COURSE_NAME: "",
        },
        enrollment_count=0,
    )

    assert summary.course_name == "course-without-name"


def test_admin_summary_pages_only_requested_section(client, new_movie):
    ddbo = new_movie["ddbo"]
    ddbo.update_table(ddbo.users, new_movie[USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERAUDITOR})
    client.set_cookie(apikey.cookie_name(), new_movie[API_KEY])

    response = client.get("/api/admin/summary?section=movies&limit=100")

    assert response.status_code == 200
    payload = response.json
    assert payload["courses"] == {"items": [], "restart_marker": None}
    assert payload["users"] == {"items": [], "restart_marker": None}
    assert any(movie["movie_id"] == new_movie[odb.MOVIE_ID]
               for movie in payload["movies"]["items"])


def test_admin_summary_rejects_invalid_section(client, new_course):
    ddbo = new_course["ddbo"]
    ddbo.update_table(ddbo.users, new_course[USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERAUDITOR})
    client.set_cookie(apikey.cookie_name(), new_course[API_KEY])

    response = client.get("/api/admin/summary?section=secrets")

    assert response.status_code == 400
    assert response.json == {"error": True, "message": "Invalid admin section"}


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
