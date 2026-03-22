"""
get-frame is implemented in lambda-resize (GET api/v1/frame).
Flask no longer has /api/get-frame; requests to it return 404.
"""


def test_get_frame_route_removed_from_flask(client):
    """Flask no longer serves get-frame; it was moved to lambda-resize."""
    resp = client.post(
        "/api/get-frame",
        data={"api_key": "any", "movie_id": "m0000000-0000-0000-0000-000000000000", "frame_number": "0"},
    )
    assert resp.status_code == 404
