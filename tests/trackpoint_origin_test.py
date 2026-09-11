import csv
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal

import pytest
from PIL import Image
from pydantic import ValidationError

from resize_app import movie_glue, mpeg_jpeg_zip
from tests.fixtures.analysis_mp4_fixture import write_four_color_movie

from app import odb, schema
from app import odb_movie_data
from app.odb import (
    API_KEY,
    FRAME_NUMBER,
    HEIGHT,
    MOVIE_ID,
    MOVIE_TRACED_URN,
    NEEDS_RETRACING,
    TRIM_END_FRAME,
    TRIM_START_FRAME,
)
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


def _xlsx_shared_strings(zf):
    try:
        xml = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(xml)
    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = []
    for si in root.findall("s:si", namespace):
        strings.append("".join(node.text or "" for node in si.findall(".//s:t", namespace)))
    return strings


def _xlsx_cell_value(cell, shared_strings):
    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    value = cell.find("s:v", namespace)
    if value is None or value.text is None:
        return ""
    if cell.get("t") == "s":
        return shared_strings[int(value.text)]
    if "." in value.text:
        return float(value.text)
    return int(value.text)


def _xlsx_cell_column(cell):
    match = re.match(r"([A-Z]+)", cell.get("r", ""))
    if not match:
        return 0
    column = 0
    for character in match.group(1):
        column = column * 26 + ord(character) - ord("A") + 1
    return column - 1


def _xlsx_rows(data, sheet_path):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        shared_strings = _xlsx_shared_strings(zf)
        root = ET.fromstring(zf.read(sheet_path))
    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows = []
    for row in root.findall(".//s:sheetData/s:row", namespace):
        values = []
        for cell in row.findall("s:c", namespace):
            column = _xlsx_cell_column(cell)
            while len(values) <= column:
                values.append("")
            values[column] = _xlsx_cell_value(cell, shared_strings)
        rows.append(values)
    return rows


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
    ddbo.update_movie(new_movie[MOVIE_ID], {MOVIE_TRACED_URN: traced_urn})

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
            "movie_data_length": 1,
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
        {"frame_number": "0", "plant x (px)": "10", "plant y (px)": "130",
         odb.FRAME_HEIGHT_PX: "150", TRACKPOINT_ORIGIN: BOTTOM_LEFT},
    ]
    assert odb.get_movie(movie_id=movie_id).get(TRACKPOINT_ORIGIN) == BOTTOM_LEFT
    stored_frame = odb.DDBO().movie_frames.get_item(Key={MOVIE_ID: movie_id, FRAME_NUMBER: 0})["Item"]
    assert stored_frame["trackpoints"][0]["y"] == Decimal(130)


def _seed_frame0(movie_id, trackpoints, *, height):
    """Set the analysis-frame height and write a single frame 0 of trackpoints."""
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={
        HEIGHT: height, odb.FRAME_HEIGHT_PX: height, odb.TOTAL_FRAMES: 1})
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


def test_xlsx_exports_trackpoints_and_metadata(client, new_movie):
    movie_id = new_movie[MOVIE_ID]
    _seed_frame0(movie_id, [
        Trackpoint(x=Decimal(100), y=Decimal(200), label="Apex", color="orange"),
        Trackpoint(x=Decimal(20), y=Decimal(20), label="Inflection Point", color="#336699"),
        Trackpoint(x=Decimal(10), y=Decimal(10), label="Ruler 0mm"),
        Trackpoint(x=Decimal(10), y=Decimal(110), label="Ruler 10mm"),
    ], height=480)
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={"total_frames": 2})
    odb.put_frame_trackpoints(movie_id=movie_id, frame_number=1, trackpoints=[
        Trackpoint(x=Decimal(105), y=Decimal(190), label="Apex", color="orange", status=0),
        Trackpoint(x=Decimal(25), y=Decimal(20), label="Inflection Point", color="#336699"),
        Trackpoint(x=Decimal(10), y=Decimal(10), label="Ruler 0mm"),
        Trackpoint(x=Decimal(10), y=Decimal(110), label="Ruler 10mm"),
    ])

    resp = client.post("/api/get-movie-trackpoints", data={
        API_KEY: new_movie[API_KEY],
        MOVIE_ID: movie_id,
        "format": "xlsx",
    })

    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert resp.headers["Content-Disposition"] == 'attachment; filename="trackpoints.xlsx"'
    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        assert "xl/worksheets/sheet1.xml" in zf.namelist()
        assert "xl/worksheets/sheet2.xml" in zf.namelist()
        assert "xl/worksheets/sheet3.xml" in zf.namelist()
        assert "xl/worksheets/sheet4.xml" in zf.namelist()
        assert "xl/worksheets/sheet5.xml" in zf.namelist()
        assert "xl/charts/chart1.xml" in zf.namelist()
        assert "xl/charts/chart2.xml" in zf.namelist()
        chart1_xml = zf.read("xl/charts/chart1.xml").decode("utf-8")
        chart2_xml = zf.read("xl/charts/chart2.xml").decode("utf-8")
        assert '<c:tickLblPos val="low"/>' in chart1_xml
        assert '<c:tickLblPos val="low"/>' in chart2_xml

    trackpoint_rows = _xlsx_rows(resp.data, "xl/worksheets/sheet1.xml")
    assert trackpoint_rows[0] == [
        "frame_number",
        "Apex x (mm)",
        "Apex y (mm)",
        "Inflection Point x (mm)",
        "Inflection Point y (mm)",
        "Ruler 0mm x (px)",
        "Ruler 0mm y (px)",
        "Ruler 10mm x (px)",
        "Ruler 10mm y (px)",
    ]
    assert trackpoint_rows[1] == [0, 10, 20, 2, 2, 10, 10, 10, 110]
    assert trackpoint_rows[2] == [1, 10.5, 19, 2.5, 2, 10, 10, 10, 110]

    metadata_rows = _xlsx_rows(resp.data, "xl/worksheets/sheet2.xml")
    metadata = {row[0]: row[1] if len(row) > 1 else "" for row in metadata_rows[1:]}
    assert metadata["movie_id"] == movie_id
    assert metadata["trim_start_frame"] == 0
    assert metadata["trim_end_frame"] == 1
    assert metadata["exported_frame_count"] == 2
    assert metadata["marker_count"] == 4
    assert metadata[odb.FRAME_HEIGHT_PX] == 480
    assert metadata[TRACKPOINT_ORIGIN] == BOTTOM_LEFT
    assert metadata["ruler_calibrated"] == "yes"
    assert metadata["ruler_marker_units"] == "px"
    assert metadata["non_ruler_marker_units"] == "mm"
    assert metadata["scale_mm_per_px"] == 0.1

    marker_rows = _xlsx_rows(resp.data, "xl/worksheets/sheet3.xml")
    assert marker_rows[0][:5] == ["label", "type", "graphable", "color", "colors_seen"]
    assert marker_rows[1][:5] == ["Apex", "apex", "yes", "orange", "orange"]
    assert marker_rows[2][:5] == [
        "Inflection Point", "inflection point", "yes", "#336699", "#336699",
    ]
    assert marker_rows[3][:4] == ["Ruler 0mm", "ruler", "no", ""]

    chart_rows = _xlsx_rows(resp.data, "xl/worksheets/sheet4.xml")
    assert chart_rows == [
        [
            "frame_number",
            "Apex X Position (mm)",
            "Apex Y Position (mm)",
            "Inflection Point X Position (mm)",
            "Inflection Point Y Position (mm)",
        ],
        [0, 0, 0, 0, 0],
        [1, 0.5, -1, 0.5, 0],
    ]


def test_xlsx_trackpoint_download_respects_trim_bounds(client, new_movie):
    movie_id = new_movie[MOVIE_ID]
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={
        "total_frames": 3,
        TRIM_START_FRAME: 1,
        TRIM_END_FRAME: 1,
    })
    for frame_number in range(3):
        odb.put_frame_trackpoints(
            movie_id=movie_id,
            frame_number=frame_number,
            trackpoints=[Trackpoint(x=10 + frame_number, y=20 + frame_number, label="apex")],
        )

    resp = client.post("/api/get-movie-trackpoints", data={
        API_KEY: new_movie[API_KEY],
        MOVIE_ID: movie_id,
        "format": "xlsx",
    })

    assert resp.status_code == 200
    rows = _xlsx_rows(resp.data, "xl/worksheets/sheet1.xml")
    assert rows == [
        ["frame_number", "apex x (px)", "apex y (px)"],
        [1, 11, 21],
    ]


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


@pytest.mark.parametrize('width,height,rotation,analysis_height', [
    (640, 480, 0, 480), (480, 640, 0, 640),
    (640, 480, 90, 640), (480, 640, 90, 480),
    (1280, 960, 0, 480), (960, 1280, 90, 480),
])
def test_movie_height_in_all_trackpoint_downloads(client, new_movie_record, tmp_path,
                                                 width, height, rotation, analysis_height):
    """Real MP4 pixels, persisted metadata and every export agree after rotation/scaling."""
    movie_id = new_movie_record[MOVIE_ID]
    path = tmp_path / 'source.mp4'
    write_four_color_movie(path, width=width, height=height)
    source_metadata = mpeg_jpeg_zip.extract_movie_metadata(movie_path=str(path))
    assert (source_metadata[odb.WIDTH], source_metadata[odb.HEIGHT]) == (width, height)
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={odb.MOVIE_ROTATION: rotation})
    odb_movie_data.set_movie_data(movie_id=movie_id, movie_data=path.read_bytes())
    movie_glue.process_uploaded_movie(movie_id=movie_id)
    stored = odb.get_movie(movie_id=movie_id)
    assert stored[odb.FRAME_HEIGHT_PX] == analysis_height
    assert schema.Movie(**stored).frame_height_px == analysis_height
    shared_metadata = odb.get_movie_metadata(movie_id=movie_id)
    assert isinstance(shared_metadata[odb.FRAME_HEIGHT_PX], int)
    assert shared_metadata[odb.FRAME_HEIGHT_PX] == analysis_height
    actual_frame = mpeg_jpeg_zip.get_first_frame_from_url(str(path), rotation)
    assert actual_frame.shape[0] == analysis_height
    # Write through the same API used by JavaScript, then download the saved point.
    params = {API_KEY: new_movie_record[API_KEY], MOVIE_ID: movie_id}
    result = client.post('/api/put-frame-trackpoints', data={
        **params, FRAME_NUMBER: 0,
        'trackpoints': json.dumps([{'x': 10, 'y': analysis_height - 20, 'label': 'Apex'}]),
    })
    assert result.status_code == 200
    expected = {odb.FRAME_HEIGHT_PX: analysis_height, TRACKPOINT_ORIGIN: BOTTOM_LEFT}
    browser = client.post('/api/get-movie-metadata', data={**params, 'frame_start': 0, 'frame_count': 1}).get_json()
    assert {key: browser['metadata'][key] for key in expected} == expected
    assert browser['frames']['0']['markers'][0]['y'] == analysis_height - 20
    for frame_range in ({}, {'frame_start': 0, 'frame_count': 1}):
        metadata = client.post('/api/get-movie-metadata', data={**params, **frame_range}).get_json()['metadata']
        assert metadata[odb.FRAME_HEIGHT_PX] == analysis_height
    downloaded = client.post('/api/get-movie-trackpoints', data={**params, 'format': 'json'}).get_json()
    assert downloaded['metadata'] == expected
    assert downloaded['trackpoint_dicts'][0]['y'] == analysis_height - 20
    response = client.post('/api/get-movie-trackpoints', data=params)
    row = next(csv.DictReader(io.StringIO(response.data.decode())))
    assert int(row[odb.FRAME_HEIGHT_PX]) == analysis_height
    assert row[TRACKPOINT_ORIGIN] == BOTTOM_LEFT
    assert int(row['Apex y (px)']) == analysis_height - 20
    response = client.post('/api/get-movie-trackpoints', data={**params, 'format': 'xlsx'})
    rows = _xlsx_rows(response.data, 'xl/worksheets/sheet2.xml')
    metadata = {row[0]: row[1] if len(row) > 1 else '' for row in rows[1:]}
    assert {key: metadata[key] for key in expected} == expected


@pytest.mark.parametrize('height', [480, 640])
def test_legacy_zip_height_persists_for_downloads(client, new_movie, height):
    """Once established from ZIP pixels, height survives removal of that ZIP."""
    movie_id = new_movie[MOVIE_ID]
    zip_urn = make_urn(object_name=f'tests/{movie_id}_zipfile.mov')
    odb_movie_data.write_object(zip_urn, _zip_with_frame(width=640 if height == 480 else 480, height=height))
    ddbo = odb.DDBO()
    ddbo.update_movie(movie_id, {odb.MOVIE_ZIPFILE_URN: zip_urn})
    ddbo.movies.update_item(Key={MOVIE_ID: movie_id}, UpdateExpression=f'REMOVE {TRACKPOINT_ORIGIN}')
    ddbo.put_movie_frame({MOVIE_ID: movie_id, FRAME_NUMBER: 0,
                         'trackpoints': [Trackpoint(x=10, y=20, label='plant').model_dump()]})
    params = {API_KEY: new_movie[API_KEY], MOVIE_ID: movie_id, 'format': 'json'}
    first = client.post('/api/get-movie-trackpoints', data=params).get_json()
    assert first['metadata'][odb.FRAME_HEIGHT_PX] == height
    assert first['trackpoint_dicts'][0]['y'] == height - 20
    assert ddbo.get_movie(movie_id)[odb.FRAME_HEIGHT_PX] == height
    odb_movie_data.purge_movie_zipfile(movie_id=movie_id)
    assert client.post('/api/get-movie-trackpoints', data=params).get_json() == first


def test_unknown_frame_height_is_explicit(client, new_movie):
    params = {API_KEY: new_movie[API_KEY], MOVIE_ID: new_movie[MOVIE_ID]}
    odb.put_frame_trackpoints(movie_id=new_movie[MOVIE_ID], frame_number=0,
                             trackpoints=[Trackpoint(x=10, y=20, label='plant')])
    for endpoint in ('get-movie-metadata', 'get-movie-trackpoints'):
        result = client.post(f'/api/{endpoint}', data={**params, 'format': 'json'}).get_json()
        assert result['metadata'][odb.FRAME_HEIGHT_PX] is None
        assert result['metadata'][TRACKPOINT_ORIGIN] == BOTTOM_LEFT
    row = next(csv.DictReader(io.StringIO(client.post('/api/get-movie-trackpoints', data=params).data.decode())))
    assert row[odb.FRAME_HEIGHT_PX] == ''
    assert row[TRACKPOINT_ORIGIN] == BOTTOM_LEFT


@pytest.mark.parametrize('width,height,rotation,expected', [
    (640, 480, 90, 640), (480, 640, 90, 480),
    (1280, 960, 0, 480), (480, 360, 0, 480),
])
def test_legacy_source_dimensions_supply_analysis_height(client, new_movie_record, width, height, rotation, expected):
    """Rotated API dimensions must not cause a second rotation or omit scaling."""
    movie_id = new_movie_record[MOVIE_ID]
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={
        odb.WIDTH: width, odb.HEIGHT: height, odb.MOVIE_ROTATION: rotation})
    result = client.post('/api/get-movie-metadata', data={
        API_KEY: new_movie_record[API_KEY], MOVIE_ID: movie_id}).get_json()
    assert result['metadata'][odb.FRAME_HEIGHT_PX] == expected


@pytest.mark.parametrize('frame_start,frame_count', [(0, None), (0, 0), (-1, 1)])
def test_invalid_frame_range_does_not_cache_legacy_height(client, new_movie, frame_start, frame_count):
    """Invalid range requests must not trigger the otherwise available ZIP backfill."""
    movie_id = new_movie[MOVIE_ID]
    zip_urn = make_urn(object_name=f'tests/{movie_id}_zipfile.mov')
    odb_movie_data.write_object(zip_urn, _zip_with_frame(width=480, height=640))
    ddbo = odb.DDBO()
    ddbo.update_movie(movie_id, {odb.MOVIE_ZIPFILE_URN: zip_urn})
    params = {API_KEY: new_movie[API_KEY], MOVIE_ID: movie_id, 'frame_start': frame_start}
    if frame_count is not None:
        params['frame_count'] = frame_count
    assert client.post('/api/get-movie-metadata', data=params).status_code == 400
    assert ddbo.get_movie(movie_id).get(odb.FRAME_HEIGHT_PX) is None
    params.update(frame_start=0, frame_count=1)
    assert client.post('/api/get-movie-metadata', data=params).status_code == 200
    assert ddbo.get_movie(movie_id)[odb.FRAME_HEIGHT_PX] == 640


def test_metadata_only_leaves_legacy_height_recovery_to_trackpoint_requests(client, new_movie):
    """A metadata-only read does not inspect or cache a legacy ZIP's available height."""
    movie_id = new_movie[MOVIE_ID]
    urn = make_urn(object_name=f'tests/{movie_id}-legacy.zip')
    odb_movie_data.write_object(urn, _zip_with_frame(width=480, height=640))
    ddbo = odb.DDBO()
    ddbo.update_movie(movie_id, {odb.MOVIE_ZIPFILE_URN: urn})
    params = {API_KEY: new_movie[API_KEY], MOVIE_ID: movie_id}
    response = client.post('/api/get-movie-metadata', data=params)
    assert response.get_json()['metadata'][odb.FRAME_HEIGHT_PX] is None
    assert ddbo.get_movie(movie_id).get(odb.FRAME_HEIGHT_PX) is None
    response = client.post('/api/get-movie-metadata', data={**params, 'frame_start': 0, 'frame_count': 1})
    assert response.get_json()['metadata'][odb.FRAME_HEIGHT_PX] == 640
    assert ddbo.get_movie(movie_id)[odb.FRAME_HEIGHT_PX] == 640
    response = client.post('/api/get-movie-metadata', data=params)
    assert response.get_json()['metadata'][odb.FRAME_HEIGHT_PX] == 640


@pytest.mark.parametrize('width,height', [(640, 480), (480, 640)])
@pytest.mark.parametrize('rotation', [90, 270])
def test_tracing_caches_rotated_height_from_raw_movie(new_movie_record, tmp_path, width, height, rotation):
    """Exercise the tracing entry point with real decoded MP4 pixels and raw DB dimensions."""
    movie_id = new_movie_record[MOVIE_ID]
    path = tmp_path / 'source.mp4'
    write_four_color_movie(path, width=width, height=height)
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={odb.MOVIE_ROTATION: rotation})
    odb_movie_data.set_movie_data(movie_id=movie_id, movie_data=path.read_bytes())
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={
        odb.WIDTH: width, odb.HEIGHT: height, odb.TOTAL_FRAMES: 4, odb.FPS: '4'})
    odb.put_frame_trackpoints(movie_id=movie_id, frame_number=0,
                             trackpoints=[Trackpoint(x=10, y=width - 20, label='Apex')])
    movie_glue.run_tracing(movie_id=movie_id, frame_start=0, frame_end=3)
    stored = odb.get_movie(movie_id=movie_id)
    assert stored[odb.FRAME_HEIGHT_PX] == width
    assert (stored[odb.WIDTH], stored[odb.HEIGHT]) == (width, height)
    assert stored[odb.MOVIE_STATUS] == odb.MOVIE_STATE_TRACING_COMPLETED


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_untouched_height_only_legacy_movie_retains_coordinate_height(client, new_movie_record, rotation):
    movie_id = new_movie_record[MOVIE_ID]
    ddbo = odb.DDBO()
    ddbo.update_movie(movie_id, {odb.HEIGHT: 150, odb.MOVIE_ROTATION: rotation})
    params = {API_KEY: new_movie_record[API_KEY], MOVIE_ID: movie_id}
    for endpoint in ('get-movie-metadata', 'get-movie-trackpoints'):
        response = client.post(f'/api/{endpoint}', data={**params, 'format': 'json'})
        assert response.status_code == 200
        assert response.get_json()['metadata'][odb.FRAME_HEIGHT_PX] == 150


@pytest.mark.parametrize('width,height', [(640, 480), (480, 640)])
def test_processed_movie_geometry_is_fixed(client, new_movie_record, tmp_path, width, height):
    """Reject late edits without altering the processed pixels or saved trackpoints."""
    movie_id = new_movie_record[MOVIE_ID]
    path = tmp_path / 'source.mp4'
    write_four_color_movie(path, width=width, height=height)
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={odb.MOVIE_ROTATION: 90})
    odb_movie_data.set_movie_data(movie_id=movie_id, movie_data=path.read_bytes())
    params = {API_KEY: new_movie_record[API_KEY], MOVIE_ID: movie_id}
    movie_glue.process_uploaded_movie(movie_id=movie_id)
    odb.put_frame_trackpoints(movie_id=movie_id, frame_number=0,
                             trackpoints=[Trackpoint(x=10, y=width - 20, label='Apex')])
    ddbo = odb.DDBO()
    before = ddbo.get_movie(movie_id)
    points = ddbo.get_frames(movie_id)
    for rotation in (90, 180):
        response = client.post('/api/rotate-movie', data={**params, 'rotation': rotation})
        assert response.status_code == 409
        assert response.get_json()['error'] is True
    for prop, value in ((odb.WIDTH, height), (odb.HEIGHT, width), (odb.MOVIE_ROTATION, 180),
                        (odb.FRAME_HEIGHT_PX, height), (odb.FRAME_HEIGHT_PX, None),
                        (odb.WIDTH, None), (odb.HEIGHT, None), (odb.MOVIE_ROTATION, None)):
        with pytest.raises(odb.MovieGeometryFinalized):
            ddbo.update_movie(movie_id, {prop: value})
    with pytest.raises(odb.MovieGeometryFinalized):
        odb_movie_data.set_movie_data(movie_id=movie_id, movie_data=b'replacement')
    assert odb_movie_data.read_object(before[odb.MOVIE_DATA_URN]) == path.read_bytes()
    assert ddbo.get_movie(movie_id) == before
    assert ddbo.get_frames(movie_id) == points
    # A repeated measurement/completion is idempotent, and exports retain the fixed height.
    movie_glue.process_uploaded_movie(movie_id=movie_id)
    assert ddbo.get_movie(movie_id)[odb.FRAME_HEIGHT_PX] == width
    download = client.post('/api/get-movie-trackpoints', data={**params, 'format': 'json'}).get_json()
    assert download['metadata'][odb.FRAME_HEIGHT_PX] == width
    assert download['trackpoint_dicts'][0]['y'] == width - 20


@pytest.mark.parametrize('state', [odb.MOVIE_STATE_PROCESSING, odb.MOVIE_STATE_READY,
                                   odb.MOVIE_STATE_TRACING, odb.MOVIE_STATE_TRACING_FAILED, None])
def test_rotation_rejects_processing_and_legacy_states(client, new_movie, state):
    movie_id = new_movie[MOVIE_ID]
    ddbo = odb.DDBO()
    ddbo.update_movie(movie_id, {odb.MOVIE_STATUS: state})
    before = ddbo.get_movie(movie_id)
    response = client.post('/api/rotate-movie', data={
        API_KEY: new_movie[API_KEY], MOVIE_ID: movie_id, 'rotation': 90})
    assert response.status_code == 409
    assert ddbo.get_movie(movie_id) == before


def test_upload_repairs_missing_height_atomically(new_movie_record, tmp_path):
    movie_id = new_movie_record[MOVIE_ID]
    path = tmp_path / 'source.mp4'
    write_four_color_movie(path, width=480, height=640)
    odb_movie_data.set_movie_data(movie_id=movie_id, movie_data=path.read_bytes())
    movie_glue.process_uploaded_movie(movie_id=movie_id)
    ddbo = odb.DDBO()
    # Represent a legacy completed upload lacking the newly introduced field.
    ddbo.movies.update_item(Key={MOVIE_ID: movie_id}, UpdateExpression='REMOVE frame_height_px')
    movie_glue.process_uploaded_movie(movie_id=movie_id)
    movie = ddbo.get_movie(movie_id)
    assert movie[odb.FRAME_HEIGHT_PX] == 640
    assert movie[odb.MOVIE_STATUS] == odb.MOVIE_STATE_READY


@pytest.mark.parametrize('artifact', ['width', 'height', 'jpeg', 'trackpoints', 'uploaded'])
def test_legacy_upload_with_coordinate_data_cannot_rotate(client, new_movie_record, artifact):
    """Even a legacy uploading status cannot make an existing coordinate space editable."""
    movie_id = new_movie_record[MOVIE_ID]
    ddbo = odb.DDBO()
    ddbo.update_movie(movie_id, {odb.MOVIE_ROTATION: 0})
    if artifact == 'uploaded':
        ddbo.update_movie(movie_id, {odb.UPLOADED_AT: 1})
    if artifact in ('width', 'height'):
        ddbo.update_movie(movie_id, {odb.WIDTH if artifact == 'width' else odb.HEIGHT: 480})
    elif artifact == 'jpeg':
        odb_movie_data.create_new_movie_frame(movie_id=movie_id, frame_number=0,
                                             frame_data=_jpeg_bytes(width=640, height=480))
    elif artifact == 'trackpoints':
        ddbo.put_movie_frame({MOVIE_ID: movie_id, FRAME_NUMBER: 0,
                              'trackpoints': [Trackpoint(x=10, y=20, label='Apex').model_dump()]})
    movie = ddbo.get_movie(movie_id)
    frames = ddbo.get_frames(movie_id)
    response = client.post('/api/rotate-movie', data={
        API_KEY: new_movie_record[API_KEY], MOVIE_ID: movie_id, 'rotation': 90})
    assert response.status_code == 409
    for rotation in (90, None):
        with pytest.raises(odb.MovieGeometryFinalized):
            ddbo.update_movie(movie_id, {odb.MOVIE_ROTATION: rotation})
    # Repeating the saved value is harmless, including when frames already exist.
    ddbo.update_movie(movie_id, {odb.MOVIE_ROTATION: movie[odb.MOVIE_ROTATION]}, touch_activity=False)
    assert ddbo.get_movie(movie_id) == movie
    assert ddbo.get_frames(movie_id) == frames


@pytest.mark.parametrize('prop', [odb.WIDTH, odb.HEIGHT])
def test_client_cannot_fill_missing_legacy_dimensions(client, new_movie, prop):
    movie_id = new_movie[MOVIE_ID]
    ddbo = odb.DDBO()
    ddbo.update_movie(movie_id, {odb.FRAME_HEIGHT_PX: 480, odb.MOVIE_STATUS: odb.MOVIE_STATE_READY})
    before = ddbo.get_movie(movie_id)
    response = client.post('/api/set-metadata', data={
        API_KEY: new_movie[API_KEY], 'set_movie_id': movie_id, 'property': prop, 'value': 640})
    assert response.status_code == 403
    assert response.get_json()['error'] is True
    assert ddbo.get_movie(movie_id) == before


def test_fixed_height_conflict_is_distinct_from_late_rotation(new_movie):
    movie_id = new_movie[MOVIE_ID]
    snapshot = odb.DDBO().get_movie(movie_id)
    odb.remember_trackpoint_frame_height(movie=snapshot, frame_height=480)
    # Identical measurements from concurrent readers remain idempotent.
    odb.remember_trackpoint_frame_height(movie=snapshot, frame_height=480)
    with pytest.raises(odb.TrackpointFrameHeightMismatch):
        odb.remember_trackpoint_frame_height(movie=snapshot, frame_height=640)
    assert odb.DDBO().get_movie(movie_id)[odb.FRAME_HEIGHT_PX] == 480


@pytest.mark.parametrize('upload_field', [odb.UPLOADED_AT, odb.DATE_UPLOADED])
def test_uploaded_movie_rejects_shared_rotation_and_source_replacement(new_movie, upload_field):
    movie_id = new_movie[MOVIE_ID]
    ddbo = odb.DDBO()
    if upload_field == odb.DATE_UPLOADED:
        ddbo.update_movie(movie_id, {odb.UPLOADED_AT: None, odb.DATE_UPLOADED: 1})
    movie = ddbo.get_movie(movie_id)
    original = odb_movie_data.read_object(movie[odb.MOVIE_DATA_URN])
    with pytest.raises(odb.MovieGeometryFinalized):
        ddbo.update_movie(movie_id, {odb.MOVIE_ROTATION: 90})
    with pytest.raises(odb.MovieGeometryFinalized):
        odb_movie_data.set_movie_data(movie_id=movie_id, movie_data=b'replacement')
    assert ddbo.get_movie(movie_id) == movie
    assert odb_movie_data.read_object(movie[odb.MOVIE_DATA_URN]) == original


def test_upload_setup_cannot_accept_trackpoints(client, new_movie_record):
    movie_id = new_movie_record[MOVIE_ID]
    params = {API_KEY: new_movie_record[API_KEY], MOVIE_ID: movie_id}
    response = client.post('/api/put-frame-trackpoints', data={
        **params, FRAME_NUMBER: 0, 'trackpoints': json.dumps([{'x': 10, 'y': 20, 'label': 'Apex'}])})
    assert response.status_code == 409
    assert 'upload' in response.get_json()['message']
    ddbo = odb.DDBO()
    assert not ddbo.get_frames(movie_id)
    assert ddbo.get_movie(movie_id).get(odb.LAST_FRAME_TRACKED) is None
    # Rejected points cannot race rotation or leave coordinate state behind.
    assert client.post('/api/rotate-movie', data={**params, 'rotation': 90}).status_code == 200


@pytest.mark.parametrize('artifact', [odb.WIDTH, odb.HEIGHT, 'jpeg', 'trackpoints'])
def test_source_initialization_preserves_legacy_coordinate_data(new_movie_record, artifact):
    """Legacy uploading rows without completion markers must not lose coordinate data."""
    movie_id = new_movie_record[MOVIE_ID]
    ddbo = odb.DDBO()
    frame_urn = None
    jpeg = _jpeg_bytes(width=640, height=480)
    if artifact in (odb.WIDTH, odb.HEIGHT):
        ddbo.update_movie(movie_id, {artifact: 480})
    elif artifact == 'jpeg':
        frame_urn = odb_movie_data.create_new_movie_frame(movie_id=movie_id, frame_number=0, frame_data=jpeg)
    else:
        ddbo.put_movie_frame({MOVIE_ID: movie_id, FRAME_NUMBER: 0,
                              'trackpoints': [Trackpoint(x=10, y=20, label='Apex').model_dump()]})
    movie = ddbo.get_movie(movie_id)
    frames = ddbo.get_frames(movie_id)
    with pytest.raises(odb.MovieGeometryFinalized):
        odb_movie_data.set_movie_data(movie_id=movie_id, movie_data=b'replacement')
    assert ddbo.get_movie(movie_id) == movie
    assert ddbo.get_frames(movie_id) == frames
    if frame_urn:
        assert odb_movie_data.read_object(frame_urn) == jpeg
