#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "boto3>=1.42.72,<2",
#   "pillow>=11,<12",
#   "pydantic>=2,<3",
#   "requests>=2.32.4,<3",
#   "webapp",
# ]
# [tool.uv.sources]
# webapp = { path = "..", editable = true }
# ///
"""Exercise deployed upload, listing, tracing, and downloads against references."""

import argparse
import csv
import hashlib
import io
import logging
import math
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from PIL import Image, ImageChops
from pydantic import BaseModel, Field

from app import odb, odb_movie_data
from app.paths import ffmpeg_path
from app.schema import Trackpoint


API_KEY_FIELD = "api_key"
APEX_LABEL = "Apex"
JSON_FORMAT = "json"
LIST_MOVIES_PATH = "api/list-movies"
MOVIE_DATA_PATH = "resize-api/v1/movie-data"
MOVIE_ID_FIELD = "movie_id"
NEW_MOVIE_PATH = "api/new-movie"
RULER_0_LABEL = "Ruler 0mm"
RULER_10_LABEL = "Ruler 10mm"
TRACE_MOVIE_PATH = "resize-api/v1/trace-movie"
TRACKPOINTS_PATH = "api/get-movie-trackpoints"
XLSX_FORMAT = "xlsx"
TRACKING_TOLERANCE_PIXELS = 2
XLSX_SHEET1 = "xl/worksheets/sheet1.xml"
XLSX_NAMESPACE = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
APEX_X_COLUMN = "Apex x (mm)"
APEX_Y_COLUMN = "Apex y (mm)"
RULER_0_X_COLUMN = "Ruler 0mm x (px)"
RULER_0_Y_COLUMN = "Ruler 0mm y (px)"
RULER_10_X_COLUMN = "Ruler 10mm x (px)"
RULER_10_Y_COLUMN = "Ruler 10mm y (px)"


class PresignedPost(BaseModel):
    """S3 POST returned by the deployed Flask API."""

    url: str
    fields: dict[str, str]


class NewMovieResponse(BaseModel):
    """Successful new-movie response."""

    error: bool
    movie_id: str
    presigned_post: PresignedPost
    upload_completion_mode: str


class ListedMovie(BaseModel):
    """The deployed list-movies fields exercised by this test."""

    movie_id: str
    movie_traced_url: str | None = None


class ListMoviesResponse(BaseModel):
    """Successful list-movies response."""

    error: bool
    movies: list[ListedMovie]


class MovieDataResponse(BaseModel):
    """Signed original-movie download URL returned by lambda-resize."""

    error: bool
    movie_id: str
    url: str


class TrackpointResponse(BaseModel):
    """JSON form of the trackpoint export."""

    error: str
    trackpoint_dicts: list[Trackpoint]


class ReferenceTrackpoint(BaseModel):
    """A row of the committed calibrated CSV reference."""

    frame_number: int
    apex_x: float = Field(alias=APEX_X_COLUMN)
    apex_y: float = Field(alias=APEX_Y_COLUMN)
    ruler_0_x: int = Field(alias=RULER_0_X_COLUMN)
    ruler_0_y: int = Field(alias=RULER_0_Y_COLUMN)
    ruler_10_x: int = Field(alias=RULER_10_X_COLUMN)
    ruler_10_y: int = Field(alias=RULER_10_Y_COLUMN)


def wait_for_movie(ddbo, movie_id, predicate, *, timeout, phase):
    """Poll one DynamoDB movie row until a phase-specific predicate succeeds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        movie = ddbo.get_movie(movie_id)
        if predicate(movie):
            return movie
        time.sleep(2)
    raise TimeoutError(f"timed out waiting for deployed movie {movie_id} to finish {phase}")


def ensure_test_identity(*, stack_name):
    """Create or reuse the deployment test course, user, and API key."""
    course_id = f"{stack_name}-deployment-test"
    email = f"planttracer-deployment-test+{stack_name}@planttracer.com"
    try:
        odb.lookup_course_by_id(course_id=course_id)
    except odb.InvalidCourse_Id:
        odb.create_course(course_id=course_id, course_name=f"{stack_name} deployment workflow test",
                          course_key=f"{stack_name}-deployment-workflow")
    user_id = odb.register_email(email=email, user_name=f"{stack_name} deployment test",
                                 course_id=course_id)[odb.USER_ID]
    return course_id, user_id, odb.make_new_api_key_for_user_id(user_id=user_id)


def reference_trackpoints(reference_csv_path):
    """Read the first and final positions from the calibrated CSV reference."""
    with reference_csv_path.open(newline="", encoding="utf-8") as reference_csv:
        rows = [ReferenceTrackpoint.model_validate(row) for row in csv.DictReader(reference_csv)]
    if not rows:
        raise ValueError(f"reference CSV has no trackpoints: {reference_csv_path}")
    return rows[0], rows[-1]


def reference_scale(reference):
    """Return calibrated millimetres per pixel from the two ruler markers."""
    pixels = math.hypot(reference.ruler_10_x - reference.ruler_0_x,
                        reference.ruler_10_y - reference.ruler_0_y)
    if pixels == 0:
        raise ValueError("reference ruler markers must not overlap")
    return 10 / pixels


def reference_seed_trackpoints(reference):
    """Convert calibrated reference coordinates into initial stored trackpoints."""
    scale = reference_scale(reference)
    return [
        Trackpoint(x=round(reference.apex_x / scale), y=round(reference.apex_y / scale),
                   label=APEX_LABEL, frame_number=0),
        Trackpoint(x=reference.ruler_0_x, y=reference.ruler_0_y, label=RULER_0_LABEL,
                   frame_number=0, undeletable=True),
        Trackpoint(x=reference.ruler_10_x, y=reference.ruler_10_y, label=RULER_10_LABEL,
                   frame_number=0, undeletable=True),
    ]


def assert_position(actual, expected, *, scale, frame_number):
    """Assert that an Apex position is within the allowed pixel drift."""
    expected_x, expected_y = expected.apex_x / scale, expected.apex_y / scale
    if isinstance(actual, ReferenceTrackpoint):
        actual_x, actual_y = actual.apex_x / scale, actual.apex_y / scale
    else:
        actual_x, actual_y = actual.x, actual.y
    if abs(actual_x - expected_x) > TRACKING_TOLERANCE_PIXELS:
        raise AssertionError(f"frame {frame_number} Apex x={actual_x}, expected {expected_x} +/- "
                             f"{TRACKING_TOLERANCE_PIXELS} pixels")
    if abs(actual_y - expected_y) > TRACKING_TOLERANCE_PIXELS:
        raise AssertionError(f"frame {frame_number} Apex y={actual_y}, expected {expected_y} +/- "
                             f"{TRACKING_TOLERANCE_PIXELS} pixels")


def _xlsx_shared_strings(zip_file):
    """Read the optional XLSX shared-string table."""
    shared_strings_path = "xl/sharedStrings.xml"
    if shared_strings_path not in zip_file.namelist():
        return []
    return ["".join(item.itertext()) for item in ET.fromstring(zip_file.read(shared_strings_path))]


def _xlsx_column(cell):
    """Return zero-based column index for an XLSX cell."""
    column = 0
    for character in cell.get("r", ""):
        if not character.isalpha():
            break
        column = column * 26 + ord(character) - ord("A") + 1
    return column - 1


def _xlsx_value(cell, shared_strings):
    """Decode one XLSX cell value."""
    value = cell.find("s:v", XLSX_NAMESPACE)
    if value is None:
        return ""
    if cell.get("t") == "s":
        return shared_strings[int(value.text)]
    return float(value.text)


def xlsx_trackpoint_rows(xlsx_data):
    """Read the first worksheet as rows of the exported trackpoint table."""
    with zipfile.ZipFile(io.BytesIO(xlsx_data)) as zip_file:
        shared_strings = _xlsx_shared_strings(zip_file)
        root = ET.fromstring(zip_file.read(XLSX_SHEET1))
    rows = []
    for row in root.findall(".//s:sheetData/s:row", XLSX_NAMESPACE):
        values = []
        for cell in row.findall("s:c", XLSX_NAMESPACE):
            column = _xlsx_column(cell)
            while len(values) <= column:
                values.append("")
            values[column] = _xlsx_value(cell, shared_strings)
        rows.append(values)
    return rows


def assert_export_endpoints(rows, expected_start, expected_end, *, scale, export_name):
    """Verify one tabular export has reference headers and endpoint values."""
    headers = rows[0]
    expected_headers = ["frame_number", APEX_X_COLUMN, APEX_Y_COLUMN, RULER_0_X_COLUMN,
                        RULER_0_Y_COLUMN, RULER_10_X_COLUMN, RULER_10_Y_COLUMN]
    if headers != expected_headers:
        raise AssertionError(f"unexpected {export_name} headers: {headers}")
    actual_start = ReferenceTrackpoint.model_validate(dict(zip(headers, rows[1])))
    actual_end = ReferenceTrackpoint.model_validate(dict(zip(headers, rows[-1])))
    if actual_start.frame_number != expected_start.frame_number:
        raise AssertionError(f"{export_name} starts at frame {actual_start.frame_number}")
    if actual_end.frame_number != expected_end.frame_number:
        raise AssertionError(f"{export_name} ends at frame {actual_end.frame_number}")
    assert_position(actual_start, expected_start, scale=scale, frame_number=actual_start.frame_number)
    assert_position(actual_end, expected_end, scale=scale, frame_number=actual_end.frame_number)


def assert_final_frame(downloaded_movie, reference_frame):
    """Compare a downloaded traced movie's final frame with the committed reference."""
    executable = ffmpeg_path()
    if not executable:
        raise RuntimeError("ffmpeg is required to compare the traced movie's final frame")
    with tempfile.TemporaryDirectory() as temp_dir:
        movie_path = Path(temp_dir) / "traced.mov"
        actual_frame = Path(temp_dir) / "last-frame.png"
        movie_path.write_bytes(downloaded_movie)
        subprocess.run([executable, "-v", "error", "-y", "-i", str(movie_path), "-vf", "reverse",
                        "-frames:v", "1", str(actual_frame)], check=True)
        with Image.open(reference_frame) as expected, Image.open(actual_frame) as actual:
            expected_rgb = expected.convert("RGB")
            actual_rgb = actual.convert("RGB")
            if expected_rgb.size != actual_rgb.size or ImageChops.difference(
                    expected_rgb, actual_rgb).getbbox() is not None:
                raise AssertionError("traced movie final frame does not match the reference rendering")


def post_api(endpoint, path, *, api_key, movie_id, response_format=None):
    """Call a deployed Flask endpoint that requires the temporary API key."""
    data = {API_KEY_FIELD: api_key, MOVIE_ID_FIELD: movie_id}
    if response_format:
        data["format"] = response_format
    response = requests.post(f"{endpoint.rstrip('/')}/{path}", data=data, timeout=30)
    response.raise_for_status()
    return response


def run_workflow(*, endpoint, stack_name, movie_path, reference_csv_path, reference_xlsx_path,
                 reference_traced_movie_path, reference_frame_path, timeout):
    """Run the deployed workflow and always revoke its temporary API key."""
    ddbo = odb.DDBO()
    course_id, _user_id, api_key = ensure_test_identity(stack_name=stack_name)
    movie_id = None
    try:
        expected_start, expected_end = reference_trackpoints(reference_csv_path)
        scale = reference_scale(expected_start)
        assert_final_frame(reference_traced_movie_path.read_bytes(), reference_frame_path)
        movie_bytes = movie_path.read_bytes()
        response = requests.post(f"{endpoint.rstrip('/')}/{NEW_MOVIE_PATH}", data={
            API_KEY_FIELD: api_key, "title": f"deployment test {int(time.time())}",
            "description": "automated post-deploy EventBridge workflow test",
            "movie_data_sha256": hashlib.sha256(movie_bytes).hexdigest(),
            "movie_data_length": len(movie_bytes), "fpm": "30"}, timeout=30)
        response.raise_for_status()
        created = NewMovieResponse.model_validate(response.json())
        if created.error or created.upload_completion_mode != "eventbridge":
            raise RuntimeError("deployed new-movie did not select EventBridge completion")
        movie_id = created.movie_id
        upload = requests.post(created.presigned_post.url, data=created.presigned_post.fields,
                               files={"file": (movie_path.name, movie_bytes, "video/mp4")}, timeout=timeout)
        upload.raise_for_status()
        uploaded_movie = wait_for_movie(ddbo, movie_id, lambda movie: bool(movie.get(odb.RESIZED_AT)),
                                         timeout=timeout, phase="upload processing")
        if uploaded_movie.get(odb.MOVIE_STATUS) != odb.MOVIE_STATE_READY:
            raise RuntimeError(f"movie {movie_id} is not ready after upload processing")
        listed = ListMoviesResponse.model_validate(
            post_api(endpoint, LIST_MOVIES_PATH, api_key=api_key, movie_id=movie_id).json())
        if listed.error or movie_id not in {movie.movie_id for movie in listed.movies}:
            raise AssertionError(f"uploaded movie {movie_id} is absent from deployed list-movies")
        metadata_response = requests.get(f"{endpoint.rstrip('/')}/{MOVIE_DATA_PATH}", params={
            API_KEY_FIELD: api_key, MOVIE_ID_FIELD: movie_id, "format": JSON_FORMAT}, timeout=30)
        metadata_response.raise_for_status()
        original = MovieDataResponse.model_validate(metadata_response.json())
        original_download = requests.get(original.url, timeout=timeout)
        original_download.raise_for_status()
        if hashlib.sha256(original_download.content).digest() != hashlib.sha256(movie_bytes).digest():
            raise AssertionError("downloaded original movie differs from the uploaded fixture")
        odb.put_frame_trackpoints(movie_id=movie_id, frame_number=0,
                                  trackpoints=reference_seed_trackpoints(expected_start))
        traced = requests.post(f"{endpoint.rstrip('/')}/{TRACE_MOVIE_PATH}", headers={"x-api-key": api_key},
                               json={MOVIE_ID_FIELD: movie_id, "frame_start": 0,
                                     "frame_end": expected_end.frame_number}, timeout=30)
        traced.raise_for_status()
        wait_for_movie(ddbo, movie_id,
                       lambda movie: movie.get(odb.MOVIE_STATUS) == odb.MOVIE_STATE_TRACING_COMPLETED,
                       timeout=timeout, phase="tracing")
        trackpoints = TrackpointResponse.model_validate(post_api(
            endpoint, TRACKPOINTS_PATH, api_key=api_key, movie_id=movie_id,
            response_format=JSON_FORMAT).json())
        apexes = {point.frame_number: point for point in trackpoints.trackpoint_dicts
                  if point.label == APEX_LABEL}
        assert_position(apexes[expected_start.frame_number], expected_start, scale=scale,
                        frame_number=expected_start.frame_number)
        assert_position(apexes[expected_end.frame_number], expected_end, scale=scale,
                        frame_number=expected_end.frame_number)
        csv_rows = list(csv.reader(io.StringIO(post_api(
            endpoint, TRACKPOINTS_PATH, api_key=api_key, movie_id=movie_id).text)))
        assert_export_endpoints(csv_rows, expected_start, expected_end, scale=scale, export_name="CSV")
        xlsx_rows = xlsx_trackpoint_rows(post_api(
            endpoint, TRACKPOINTS_PATH, api_key=api_key, movie_id=movie_id,
            response_format=XLSX_FORMAT).content)
        assert_export_endpoints(xlsx_rows, expected_start, expected_end, scale=scale, export_name="XLSX")
        reference_xlsx_rows = xlsx_trackpoint_rows(reference_xlsx_path.read_bytes())
        assert_export_endpoints(reference_xlsx_rows, expected_start, expected_end, scale=scale,
                                export_name="reference XLSX")
        if xlsx_rows[0] != reference_xlsx_rows[0]:
            raise AssertionError("downloaded XLSX headers differ from the reference XLSX")
        traced_listing = ListMoviesResponse.model_validate(
            post_api(endpoint, LIST_MOVIES_PATH, api_key=api_key, movie_id=movie_id).json())
        traced_movie = next(movie for movie in traced_listing.movies if movie.movie_id == movie_id)
        if not traced_movie.movie_traced_url:
            raise AssertionError("deployed list-movies did not provide a traced movie download URL")
        traced_download = requests.get(traced_movie.movie_traced_url, timeout=timeout)
        traced_download.raise_for_status()
        assert_final_frame(traced_download.content, reference_frame_path)
        logging.info("deployed workflow passed for stack=%s course=%s", stack_name, course_id)
    finally:
        if movie_id:
            odb_movie_data.purge_movie(movie_id=movie_id)
            ddbo.batch_delete_movie_ids([movie_id])
        ddbo.api_keys.delete_item(Key={odb.API_KEY: api_key})


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--stack-name", required=True)
    parser.add_argument("--movie", type=Path, required=True)
    parser.add_argument("--reference-csv", type=Path, required=True)
    parser.add_argument("--reference-xlsx", type=Path, required=True)
    parser.add_argument("--reference-traced-movie", type=Path, required=True)
    parser.add_argument("--reference-frame", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    for fixture in (args.movie, args.reference_csv, args.reference_xlsx,
                    args.reference_traced_movie, args.reference_frame):
        if not fixture.is_file():
            raise SystemExit(f"test fixture does not exist: {fixture}")
    run_workflow(endpoint=args.endpoint, stack_name=args.stack_name, movie_path=args.movie,
                 reference_csv_path=args.reference_csv, reference_xlsx_path=args.reference_xlsx,
                 reference_traced_movie_path=args.reference_traced_movie,
                 reference_frame_path=args.reference_frame,
                 timeout=args.timeout)


if __name__ == "__main__":
    main()
