"""Flask API tests for starting and uploading camera recordings."""

from urllib.parse import urlencode
from uuid import uuid4

from app import apikey, odb
from app.constants import C, storage_deployment_id
from app.s3_presigned import frame_object_key


def test_camera_magic_link_authenticates_and_clears_key_from_url(client, new_course):
    """A registration recipient can open Camera in a fresh phone browser."""
    camera = client.get('/camera', query_string={
        odb.API_KEY: new_course[odb.API_KEY],
        odb.COURSE_ID: new_course[odb.COURSE_ID],
    }, follow_redirects=True)
    assert camera.status_code == 200
    assert len(camera.history) == 1
    redirect = camera.history[0]
    assert redirect.location == f"/camera?{urlencode({odb.COURSE_ID: new_course[odb.COURSE_ID]})}"
    assert redirect.headers['Referrer-Policy'] == 'no-referrer'
    assert client.get_cookie(apikey.cookie_name()).value == new_course[odb.API_KEY]
    assert b'id="camera-root"' in camera.data
    assert b'camera.js?v=1' in camera.data


def test_camera_api_creates_movie_and_signs_frame_upload(client, new_course):
    """Each camera start creates a distinct uploading movie with bounded JPEG posts."""
    client.set_cookie(apikey.cookie_name(), new_course[odb.API_KEY])
    page = client.get("/camera")
    assert page.status_code == 200
    assert b'id="camera-root"' in page.data

    invalid_interval = client.post("/api/camera/new-movie", data={
        "title": "Camera test",
        "description": "Invalid interval",
        "course_id": new_course[odb.COURSE_ID],
        "capture_interval_seconds": "20",
    })
    assert invalid_interval.status_code == 400

    fields = {
        "title": "Camera test",
        "description": "Two-minute capture",
        "course_id": new_course[odb.COURSE_ID],
        "capture_interval_seconds": "120",
        "recording_id": str(uuid4()),
    }
    invalid_recording = client.post("/api/camera/new-movie", data={**fields, "recording_id": "invalid"})
    assert invalid_recording.status_code == 400

    response = client.post("/api/camera/new-movie", data=fields)
    assert response.status_code == 200
    movie_id = response.json[odb.MOVIE_ID]
    movie = new_course["ddbo"].get_movie(movie_id)
    assert movie[odb.MOVIE_STATUS] == odb.MOVIE_STATE_UPLOADING
    assert movie[odb.CAMERA_CAPTURE] is True
    assert movie[odb.CAMERA_FRAMES_STAMPED] is True
    assert movie[odb.FPM] == "0.5"
    assert movie[odb.MOVIE_DATA_URN]

    upload = client.post("/api/camera/frame-upload", data={
        "movie_id": movie_id,
        "frame_number": "0",
    })
    assert upload.status_code == 200
    signed = upload.json["presigned_post"]
    expected_key = frame_object_key(
        deployment_id=storage_deployment_id(),
        course_id=new_course[odb.COURSE_ID],
        movie_id=movie_id,
        frame_number=0,
    )
    assert signed["fields"]["key"] == expected_key
    assert signed["fields"]["Content-Type"] == "image/jpeg"
    assert signed["fields"]["policy"]
    assert C.CAMERA_FRAME_MAX_BYTES == 2 * 1024 * 1024

    invalid_number = client.post("/api/camera/frame-upload", data={
        "movie_id": movie_id,
        "frame_number": "-1",
    })
    assert invalid_number.status_code == 400

    new_course["ddbo"].update_movie(movie_id, {odb.MOVIE_STATUS: odb.MOVIE_STATE_READY})
    retry = client.post("/api/camera/new-movie", data=fields)
    assert retry.status_code == 200
    assert retry.json[odb.MOVIE_ID] == movie_id
    assert new_course["ddbo"].get_movie(movie_id)[odb.MOVIE_STATUS] == odb.MOVIE_STATE_READY
    stopped_upload = client.post("/api/camera/frame-upload", data={
        "movie_id": movie_id,
        "frame_number": "1",
    })
    assert stopped_upload.status_code == 409

    second = client.post("/api/camera/new-movie", data={
        "title": "Camera test 2",
        "description": "Independent recording",
        "course_id": new_course[odb.COURSE_ID],
    })
    assert second.status_code == 200
    assert second.json[odb.MOVIE_ID] != movie_id
    legacy = new_course["ddbo"].get_movie(second.json[odb.MOVIE_ID])
    assert legacy[odb.FPM] == "4"
    assert not legacy[odb.CAMERA_FRAMES_STAMPED]
