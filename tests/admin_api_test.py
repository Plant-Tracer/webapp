from app import apikey, odb
from app.odb import API_KEY, USER_ID

from .constants import ADMIN_EMAIL


def test_admin_summary_denies_regular_user(client, new_course):
    client.set_cookie(apikey.cookie_name(), new_course[API_KEY])

    response = client.get("/api/admin/summary")

    assert response.status_code == 403
    assert response.json["error"] is True


def test_admin_summary_allows_bootstrap_course_admin(client, new_course):
    admin_api_key = odb.make_new_api_key(email=new_course[ADMIN_EMAIL])
    client.set_cookie(apikey.cookie_name(), admin_api_key)

    response = client.get("/api/admin/summary?limit=1")

    assert response.status_code == 200
    payload = response.json
    assert payload["error"] is False
    assert payload["viewer"]["bootstrap_course_admin"] is True
    assert payload["viewer"]["super_role"] == odb.SUPER_ROLE_NONE
    assert payload["counts"]["courses"] >= 1
    assert len(payload["courses"]["items"]) == 1
    assert len(payload["users"]["items"]) == 1


def test_admin_summary_allows_super_auditor(client, new_course):
    ddbo = new_course["ddbo"]
    ddbo.update_table(ddbo.users, new_course[USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_AUDITOR})
    client.set_cookie(apikey.cookie_name(), new_course[API_KEY])

    response = client.get("/api/admin/summary?limit=1")

    assert response.status_code == 200
    payload = response.json
    assert payload["viewer"]["bootstrap_course_admin"] is False
    assert payload["viewer"]["super_role"] == odb.SUPER_ROLE_AUDITOR


def test_admin_page_loads_for_super_auditor(client, new_course):
    ddbo = new_course["ddbo"]
    ddbo.update_table(ddbo.users, new_course[USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_AUDITOR})
    client.set_cookie(apikey.cookie_name(), new_course[API_KEY])

    response = client.get("/admin")

    assert response.status_code == 200
    assert "admin.js" in response.text
    assert "Admin" in response.text
