import json

from app import local_lambda_debug


def test_local_lambda_bridge_ping():
    local_lambda_debug.configure_local_environment()
    client = local_lambda_debug.bridge_app.test_client()

    response = client.get("/resize-api/v1/ping")

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "ok"
