import csv
import io
import zipfile
from decimal import Decimal

import pytest
from PIL import Image
from pydantic import ValidationError

from app import odb, schema
from app import odb_movie_data
from app.odb import API_KEY, FRAME_NUMBER, HEIGHT, MOVIE_ID
from app.s3_presigned import make_urn
from app.schema import Trackpoint


TRACKPOINT_ORIGIN = "trackpoint_origin"
BOTTOM_LEFT = "bottom-left"
TOP_LEFT = "top-left"


def _movie_payload(**overrides):
    payload = {
        MOVIE_ID: "mtest",
        "title": "ttest",
        "description": "dtest",
        "created_at": 1,
        "user_id": "utest",
        "user_name": "utest2",
        "course_id": "ctest",
        "published": 0,
        "deleted": 0,
    }
    payload.update(overrides)
    return payload


def _make_legacy_top_left_movie(*, movie_id: str, frame_height: int, legacy_y: int) -> None:
    ddbo = odb.DDBO()
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={HEIGHT: frame_height})
    ddbo.movies.update_item(
        Key={MOVIE_ID: movie_id},
        UpdateExpression=f"REMOVE {TRACKPOINT_ORIGIN}",
    )
    ddbo.put_movie_frame(
        {
            MOVIE_ID: movie_id,
            FRAME_NUMBER: 0,
            "trackpoints": [Trackpoint(x=Decimal(10), y=Decimal(legacy_y), label="plant").model_dump()],
        }
    )


def _jpeg_bytes(*, width: int, height: int) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), color="white").save(output, format="JPEG")
    return output.getvalue()


def _zip_with_frame(*, width: int, height: int) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("frame_0000.jpeg", _jpeg_bytes(width=width, height=height))
    return output.getvalue()


def test_movie_schema_declares_trackpoint_origin_contract():
    assert getattr(odb, "TRACKPOINT_ORIGIN", None) == TRACKPOINT_ORIGIN
    assert TRACKPOINT_ORIGIN in schema.Movie.model_fields.keys()

    legacy_movie = schema.Movie(**_movie_payload())
    assert getattr(legacy_movie, TRACKPOINT_ORIGIN) is None

    bottom_left_movie = schema.Movie(**_movie_payload(trackpoint_origin=BOTTOM_LEFT))
    assert getattr(bottom_left_movie, TRACKPOINT_ORIGIN) == BOTTOM_LEFT

    with pytest.raises(ValidationError):
        schema.Movie(**_movie_payload(trackpoint_origin=TOP_LEFT))


def test_create_new_movie_stores_bottom_left_trackpoint_origin(new_movie):
    movie = odb.get_movie(movie_id=new_movie[MOVIE_ID])
    assert movie.get(TRACKPOINT_ORIGIN) == BOTTOM_LEFT


def test_get_movie_metadata_exposes_trackpoint_origin(client, new_movie):
    resp = client.post(
        "/api/get-movie-metadata",
        data={API_KEY: new_movie[API_KEY], MOVIE_ID: new_movie[MOVIE_ID]},
    )
    assert resp.status_code == 200
    res = resp.get_json()
    assert res["error"] is False
    assert res["metadata"].get(TRACKPOINT_ORIGIN) == BOTTOM_LEFT


def test_new_movie_api_stores_bottom_left_trackpoint_origin(client, new_course):
    resp = client.post(
        "/api/new-movie",
        data={
            API_KEY: new_course[API_KEY],
            "title": "Trackpoint origin API test",
            "description": "Verify /api/new-movie writes the coordinate contract.",
            "movie_data_sha256": "0" * 64,
        },
    )

    assert resp.status_code == 200
    res = resp.get_json()
    assert res["error"] is False
    movie = odb.get_movie(movie_id=res[MOVIE_ID])
    assert movie.get(TRACKPOINT_ORIGIN) == BOTTOM_LEFT


def test_get_movie_metadata_lazily_migrates_legacy_markers_to_bottom_left(client, new_movie):
    movie_id = new_movie[MOVIE_ID]
    _make_legacy_top_left_movie(movie_id=movie_id, frame_height=150, legacy_y=20)

    resp = client.post(
        "/api/get-movie-metadata",
        data={
            API_KEY: new_movie[API_KEY],
            MOVIE_ID: movie_id,
            "frame_start": 0,
            "frame_count": 1,
        },
    )

    assert resp.status_code == 200
    res = resp.get_json()
    assert res["error"] is False
    assert res["metadata"].get(TRACKPOINT_ORIGIN) == BOTTOM_LEFT
    assert res["frames"]["0"]["markers"] == [
        {"frame_number": 0, "x": 10, "y": 130, "label": "plant"},
    ]
    assert odb.get_movie_trackpoints(movie_id=movie_id) == [
        {"frame_number": 0, "x": 10, "y": 130, "label": "plant"},
    ]


def test_get_movie_metadata_reports_lazy_migration_failure_as_json(client, new_movie):
    movie_id = new_movie[MOVIE_ID]
    ddbo = odb.DDBO()
    ddbo.movies.update_item(
        Key={MOVIE_ID: movie_id},
        UpdateExpression=f"REMOVE {TRACKPOINT_ORIGIN}, #height",
        ExpressionAttributeNames={"#height": HEIGHT},
    )
    ddbo.put_movie_frame(
        {
            MOVIE_ID: movie_id,
            FRAME_NUMBER: 0,
            "trackpoints": [Trackpoint(x=Decimal(10), y=Decimal(20), label="plant").model_dump()],
        }
    )

    resp = client.post(
        "/api/get-movie-metadata",
        data={
            API_KEY: new_movie[API_KEY],
            MOVIE_ID: movie_id,
            "frame_start": 0,
            "frame_count": 1,
        },
    )

    assert resp.status_code == 500
    res = resp.get_json()
    assert res["error"] is True
    assert "Trackpoint migration failed" in res["message"]
    assert "does not have analysis frame height" in res["message"]


def test_get_movie_metadata_lazily_migrates_using_zipfile_height_when_movie_height_missing(client, new_movie):
    movie_id = new_movie[MOVIE_ID]
    zip_urn = make_urn(object_name=f"tests/{movie_id}_zipfile.mov")
    odb_movie_data.write_object(zip_urn, _zip_with_frame(width=200, height=150))
    ddbo = odb.DDBO()
    ddbo.movies.update_item(
        Key={MOVIE_ID: movie_id},
        UpdateExpression=f"SET movie_zipfile_urn=:zip_urn REMOVE {TRACKPOINT_ORIGIN}, #height",
        ExpressionAttributeNames={"#height": HEIGHT},
        ExpressionAttributeValues={":zip_urn": zip_urn},
    )
    ddbo.put_movie_frame(
        {
            MOVIE_ID: movie_id,
            FRAME_NUMBER: 0,
            "trackpoints": [Trackpoint(x=Decimal(10), y=Decimal(20), label="plant").model_dump()],
        }
    )

    resp = client.post(
        "/api/get-movie-metadata",
        data={
            API_KEY: new_movie[API_KEY],
            MOVIE_ID: movie_id,
            "frame_start": 0,
            "frame_count": 1,
        },
    )

    assert resp.status_code == 200
    res = resp.get_json()
    assert res["error"] is False
    assert res["metadata"].get(TRACKPOINT_ORIGIN) == BOTTOM_LEFT
    assert res["frames"]["0"]["markers"] == [
        {"frame_number": 0, "x": 10, "y": 130, "label": "plant"},
    ]


def test_lazy_migration_retry_does_not_double_flip_converted_frames(new_movie):
    movie_id = new_movie[MOVIE_ID]
    ddbo = odb.DDBO()
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={HEIGHT: 150})
    ddbo.movies.update_item(
        Key={MOVIE_ID: movie_id},
        UpdateExpression=f"REMOVE {TRACKPOINT_ORIGIN}",
    )
    ddbo.put_movie_frame(
        {
            MOVIE_ID: movie_id,
            FRAME_NUMBER: 0,
            odb.TRACKPOINT_MIGRATION_ORIGIN: BOTTOM_LEFT,
            "trackpoints": [Trackpoint(x=Decimal(10), y=Decimal(130), label="already").model_dump()],
        }
    )
    ddbo.put_movie_frame(
        {
            MOVIE_ID: movie_id,
            FRAME_NUMBER: 1,
            "trackpoints": [Trackpoint(x=Decimal(11), y=Decimal(20), label="legacy").model_dump()],
        }
    )

    odb.ensure_bottom_left_trackpoints(movie_id=movie_id)

    assert odb.get_movie_trackpoints(movie_id=movie_id) == [
        {"frame_number": 0, "x": 10, "y": 130, "label": "already"},
        {"frame_number": 1, "x": 11, "y": 130, "label": "legacy"},
    ]


def test_lazy_migration_can_use_supplied_frame_height_when_movie_height_missing(new_movie):
    movie_id = new_movie[MOVIE_ID]
    ddbo = odb.DDBO()
    ddbo.movies.update_item(
        Key={MOVIE_ID: movie_id},
        UpdateExpression=f"REMOVE {TRACKPOINT_ORIGIN}, {HEIGHT}",
    )
    ddbo.put_movie_frame(
        {
            MOVIE_ID: movie_id,
            FRAME_NUMBER: 0,
            "trackpoints": [Trackpoint(x=Decimal(10), y=Decimal(20), label="plant").model_dump()],
        }
    )

    odb.ensure_bottom_left_trackpoints(movie_id=movie_id, frame_height=150)

    assert odb.get_movie(movie_id=movie_id).get(TRACKPOINT_ORIGIN) == BOTTOM_LEFT
    assert odb.get_movie_trackpoints(movie_id=movie_id) == [
        {"frame_number": 0, "x": 10, "y": 130, "label": "plant"},
    ]


def test_get_movie_trackpoints_lazily_migrates_legacy_csv_export(client, new_movie):
    movie_id = new_movie[MOVIE_ID]
    _make_legacy_top_left_movie(movie_id=movie_id, frame_height=150, legacy_y=20)

    resp = client.post(
        "/api/get-movie-trackpoints",
        data={API_KEY: new_movie[API_KEY], MOVIE_ID: movie_id},
    )

    assert resp.status_code == 200
    rows = list(csv.DictReader(io.StringIO(resp.data.decode("utf-8"))))
    assert rows == [
        {"frame_number": "0", "plant x": "10", "plant y": "130"},
    ]
    assert odb.get_movie(movie_id=movie_id).get(TRACKPOINT_ORIGIN) == BOTTOM_LEFT
    stored_frame = odb.DDBO().movie_frames.get_item(Key={MOVIE_ID: movie_id, FRAME_NUMBER: 0})["Item"]
    assert stored_frame["trackpoints"][0]["y"] == Decimal(130)
