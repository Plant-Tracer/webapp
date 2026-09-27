"""Flask API tests for starting and uploading camera recordings."""

from app import apikey, odb
from app.constants import C, storage_deployment_id
from app.s3_presigned import frame_object_key


def test_camera_api_creates_movie_and_signs_frame_upload(client, new_course):
    """Each camera start creates a distinct uploading movie with bounded JPEG posts."""
    client.set_cookie(apikey.cookie_name(), new_course[odb.API_KEY])
    response = client.post("/api/camera/new-movie", data={
        "title": "Camera test",
        "description": "15-second capture",
        "course_id": new_course[odb.COURSE_ID],
    })
    assert response.status_code == 200
    movie_id = response.json[odb.MOVIE_ID]
    movie = new_course["ddbo"].get_movie(movie_id)
    assert movie[odb.MOVIE_STATUS] == odb.MOVIE_STATE_UPLOADING
    assert movie[odb.CAMERA_CAPTURE] is True
    assert movie[odb.FPM] == "4"

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

    second = client.post("/api/camera/new-movie", data={
        "title": "Camera test 2",
        "description": "Independent recording",
        "course_id": new_course[odb.COURSE_ID],
    })
    assert second.status_code == 200
    assert second.json[odb.MOVIE_ID] != movie_id
