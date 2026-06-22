import csv
import io
import zipfile
from decimal import Decimal

import pytest
from PIL import Image
from pydantic import ValidationError

from app import odb, schema
from app import odb_movie_data
from app.odb import API_KEY, FRAME_NUMBER, HEIGHT, MOVIE_ID, MOVIE_TRACED_URN, NEEDS_RETRACING
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


def test_put_frame_trackpoints_marks_movie_as_needing_retrace(client, new_movie):
    resp = client.post(
        "/api/put-frame-trackpoints",
        data={
            API_KEY: new_movie[API_KEY],
            MOVIE_ID: new_movie[MOVIE_ID],
            FRAME_NUMBER: 0,
            "trackpoints": '[{"x":10,"y":20,"label":"Apex"}]',
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["error"] is False
    movie = odb.get_movie(movie_id=new_movie[MOVIE_ID])
    assert movie[NEEDS_RETRACING] == 1


def test_rename_marker_api_renames_stored_trackpoints(client, new_movie):
    movie_id = new_movie[MOVIE_ID]
    odb.put_frame_trackpoints(
        movie_id=movie_id,
        frame_number=0,
        trackpoints=[Trackpoint(x=Decimal(10), y=Decimal(20), label="Ruler 0mm", color="red", undeletable=True)],
    )

    resp = client.post(
        "/api/rename-marker",
        data={
            API_KEY: new_movie[API_KEY],
            MOVIE_ID: movie_id,
            "old_label": "Ruler 0mm",
            "new_label": "Ruler 30mm",
        },
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"error": False, "frames_updated": 1, "trackpoints_updated": 1}
    assert odb.get_movie_trackpoints(movie_id=movie_id) == [
        {"frame_number": 0, "x": 10, "y": 20, "label": "Ruler 30mm", "color": "red", "undeletable": True},
    ]
    assert odb.get_movie(movie_id=movie_id)[NEEDS_RETRACING] == 1


def test_list_movies_returns_signed_traced_movie_url(client, new_movie):
    traced_urn = make_urn(object_name=f"{new_movie[MOVIE_ID]}_traced.mp4")
    ddbo = odb.DDBO()
    ddbo.update_table(ddbo.movies, new_movie[MOVIE_ID], {MOVIE_TRACED_URN: traced_urn})

    resp = client.post("/api/list-movies", data={API_KEY: new_movie[API_KEY]})

    assert resp.status_code == 200
    res = resp.get_json()
    listed_movie = next(movie for movie in res["movies"] if movie[MOVIE_ID] == new_movie[MOVIE_ID])
    assert listed_movie["movie_traced_url"].startswith("http")


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


def test_lazy_migration_conditional_write_prevents_concurrent_double_flip(new_movie, mocker):
    # Simulate two concurrent first-accesses: the real DynamoDB frame has already been
    # flipped and marked bottom-left by one runner, while this runner is working from a
    # stale snapshot that still shows the frame unmarked with its original y. The in-memory
    # skip cannot catch this, so the per-frame ConditionExpression must prevent a second
    # flip (refs #1058).
    movie_id = new_movie[MOVIE_ID]
    ddbo = odb.DDBO()
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={HEIGHT: 150})
    ddbo.movies.update_item(
        Key={MOVIE_ID: movie_id},
        UpdateExpression=f"REMOVE {TRACKPOINT_ORIGIN}",
    )
    # Real DB state: frame already flipped (y 20 -> 130) and marked bottom-left.
    ddbo.put_movie_frame(
        {
            MOVIE_ID: movie_id,
            FRAME_NUMBER: 0,
            odb.TRACKPOINT_MIGRATION_ORIGIN: BOTTOM_LEFT,
            "trackpoints": [Trackpoint(x=Decimal(10), y=Decimal(130), label="plant").model_dump()],
        }
    )
    # Stale snapshot this runner reads: the already-flipped value (y=130) but WITHOUT the
    # marker, so the in-memory skip does not fire. A second flip would compute 150-130=20
    # and corrupt the frame; the ConditionExpression must prevent that write.
    stale_frame = {
        MOVIE_ID: movie_id,
        FRAME_NUMBER: 0,
        "trackpoints": [{"x": Decimal(10), "y": Decimal(130), "label": "plant"}],
    }
    mocker.patch.object(odb.DDBO, "get_frames", return_value=[stale_frame])

    odb.ensure_bottom_left_trackpoints(movie_id=movie_id, frame_height=150)

    # Read the raw frame directly (get_frames is patched); the conditional write must have
    # failed, so y stays single-flipped at 130 rather than being flipped back to 20.
    item = ddbo.movie_frames.get_item(Key={MOVIE_ID: movie_id, FRAME_NUMBER: 0})["Item"]
    assert item["trackpoints"][0]["y"] == Decimal(130)
    assert odb.get_movie(movie_id=movie_id).get(TRACKPOINT_ORIGIN) == BOTTOM_LEFT


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
    # No ruler markers => uncalibrated => pixels, with units annotated in the headers.
    assert rows == [
        {"frame_number": "0", "plant x (px)": "10", "plant y (px)": "130"},
    ]
    assert odb.get_movie(movie_id=movie_id).get(TRACKPOINT_ORIGIN) == BOTTOM_LEFT
    stored_frame = odb.DDBO().movie_frames.get_item(Key={MOVIE_ID: movie_id, FRAME_NUMBER: 0})["Item"]
    assert stored_frame["trackpoints"][0]["y"] == Decimal(130)


def _seed_frame0(movie_id, trackpoints, *, height):
    """Set the analysis-frame height and write a single frame 0 of trackpoints."""
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={HEIGHT: height, "total_frames": 1})
    odb.put_frame_trackpoints(movie_id=movie_id, frame_number=0, trackpoints=trackpoints)


def test_csv_uses_mm_for_non_ruler_markers_when_rulers_calibrated(client, new_movie):
    movie_id = new_movie[MOVIE_ID]
    # Rulers 100 px apart spanning 10 mm (scale 0.1 mm/px), placed off their default positions.
    _seed_frame0(movie_id, [
        Trackpoint(x=Decimal(100), y=Decimal(200), label="Apex"),
        Trackpoint(x=Decimal(10), y=Decimal(10), label="Ruler 0mm"),
        Trackpoint(x=Decimal(10), y=Decimal(110), label="Ruler 10mm"),
    ], height=480)

    resp = client.post("/api/get-movie-trackpoints", data={API_KEY: new_movie[API_KEY], MOVIE_ID: movie_id})
    assert resp.status_code == 200
    rows = list(csv.DictReader(io.StringIO(resp.data.decode("utf-8"))))
    row = rows[0]
    # Non-ruler marker in mm: 100*0.1=10.0, 200*0.1=20.0
    assert row["Apex x (mm)"] == "10.0"
    assert row["Apex y (mm)"] == "20.0"
    # Ruler markers stay in pixels
    assert row["Ruler 0mm x (px)"] == "10"
    assert row["Ruler 10mm y (px)"] == "110"


def test_csv_uses_pixels_when_rulers_at_default_position(client, new_movie):
    movie_id = new_movie[MOVIE_ID]
    height = 480
    # Rulers at their default canvas positions (bottom-left y = height - canvas_y) => uncalibrated.
    _seed_frame0(movie_id, [
        Trackpoint(x=Decimal(100), y=Decimal(200), label="Apex"),
        Trackpoint(x=Decimal(50), y=Decimal(height - 100), label="Ruler 0mm"),
        Trackpoint(x=Decimal(50), y=Decimal(height - 150), label="Ruler 10mm"),
    ], height=height)

    resp = client.post("/api/get-movie-trackpoints", data={API_KEY: new_movie[API_KEY], MOVIE_ID: movie_id})
    assert resp.status_code == 200
    rows = list(csv.DictReader(io.StringIO(resp.data.decode("utf-8"))))
    row = rows[0]
    assert row["Apex x (px)"] == "100"
    assert row["Apex y (px)"] == "200"
    assert "Apex x (mm)" not in row


def test_csv_uses_pixels_when_frame_height_unknown(client, new_movie, mocker):
    # Rulers off default, but the analysis-frame height cannot be determined at all
    # (not in metadata, not inferable), so the export conservatively stays in pixels.
    movie_id = new_movie[MOVIE_ID]
    ddbo = odb.DDBO()
    ddbo.movies.update_item(Key={MOVIE_ID: movie_id}, UpdateExpression=f"REMOVE {HEIGHT}")
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={"total_frames": 1})
    odb.put_frame_trackpoints(movie_id=movie_id, frame_number=0, trackpoints=[
        Trackpoint(x=Decimal(100), y=Decimal(200), label="Apex"),
        Trackpoint(x=Decimal(10), y=Decimal(10), label="Ruler 0mm"),
        Trackpoint(x=Decimal(10), y=Decimal(110), label="Ruler 10mm"),
    ])
    mocker.patch("app.flask_api.infer_trackpoint_frame_height", return_value=None)

    resp = client.post("/api/get-movie-trackpoints", data={API_KEY: new_movie[API_KEY], MOVIE_ID: movie_id})
    assert resp.status_code == 200
    row = list(csv.DictReader(io.StringIO(resp.data.decode("utf-8"))))[0]
    assert row["Apex x (px)"] == "100"
    assert "Apex x (mm)" not in row


def test_csv_uses_inferred_height_when_metadata_height_missing(client, new_movie, mocker):
    # The movie has no stored height, but the height is recoverable (e.g. from the movie zip).
    # The CSV must still calibrate and report non-ruler markers in mm. Regression for the
    # ctrack case where height was absent from metadata.
    movie_id = new_movie[MOVIE_ID]
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={"total_frames": 1})
    odb.put_frame_trackpoints(movie_id=movie_id, frame_number=0, trackpoints=[
        Trackpoint(x=Decimal(100), y=Decimal(200), label="Apex"),
        Trackpoint(x=Decimal(10), y=Decimal(10), label="Ruler 0mm"),
        Trackpoint(x=Decimal(10), y=Decimal(110), label="Ruler 10mm"),
    ])
    odb.DDBO().movies.update_item(Key={MOVIE_ID: movie_id}, UpdateExpression=f"REMOVE {HEIGHT}")
    mocker.patch("app.flask_api.infer_trackpoint_frame_height", return_value=480)

    resp = client.post("/api/get-movie-trackpoints", data={API_KEY: new_movie[API_KEY], MOVIE_ID: movie_id})
    assert resp.status_code == 200
    row = list(csv.DictReader(io.StringIO(resp.data.decode("utf-8"))))[0]
    assert row["Apex x (mm)"] == "10.0"
    assert row["Ruler 0mm x (px)"] == "10"
