"""Test that tracking shrinks large movies for zip frames even when DB width/height
already reflect analysis size (e.g. after get-frame?size=analysis).
"""

import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from resize_app import tracker as tracker_mod
from resize_app.tracker import run_tracking
from resize_app.src.app.constants import C
from resize_app.src.app.odb import (
    LAST_FRAME_TRACKED,
    MOVIE_ZIPFILE_URN,
)


BIG_MOVIE_FIXTURE = (
    Path(__file__).resolve().parent.parent.parent
    / "tests"
    / "data"
    / "big-test-movie.mp4"
)


# pylint: disable=too-many-instance-attributes
class _FakeEnv:
    """Minimal fake tracking backend for exercising run_tracking shrink logic."""

    def __init__(self, movie_id: str, movie_bytes: bytes):
        self.movie_id = movie_id
        self._movie_bytes = movie_bytes
        # Simulate DB metadata after Lambda get-frame(size=analysis) has already
        # written analysis-sized width/height (640x480), even though the actual
        # movie bytes are larger. This is the bug scenario we want to cover.
        self.movie_record = {
            "movie_id": movie_id,
            "course_id": "BIGCOURSE",
            "width": C.ANALYSIS_FRAME_MAX_WIDTH,
            "height": C.ANALYSIS_FRAME_MAX_HEIGHT,
            "total_frames": None,
            "total_bytes": None,
            "fps": None,
            "rotation_steps": 0,
            "research_use": 1,
            "credit_by_name": 1,
            "attribution_name": "Test Student",
        }
        self._trackpoints = []  # start with empty trackpoints; frame 0 only
        self.objects = {}  # urn -> bytes
        self.movie_updates = []
        self.metadata_sets = []
        self.movie_id_for_course = "BIGCOURSE"
        self.movies = object()

    def get_movie_data(self, movie_id):
        assert movie_id == self.movie_id
        return self._movie_bytes

    def get_movie_metadata(self, movie_id):
        assert movie_id == self.movie_id
        return dict(self.movie_record)

    def get_object_data(self, *, urn):
        if urn not in self.objects:
            raise KeyError(urn)
        return self.objects[urn]

    def get_movie_trackpoints(self, movie_id):
        assert movie_id == self.movie_id
        return list(self._trackpoints)

    def put_frame_trackpoints(self, *, movie_id, frame_number, trackpoints):
        assert movie_id == self.movie_id
        # Store trackpoints; we do not need per-frame grouping for this test.
        for tp in trackpoints:
            tp = dict(tp)
            tp["frame_number"] = frame_number
            self._trackpoints.append(tp)

    def set_metadata(self, *, user_id, movie_id, prop, value):
        assert movie_id == self.movie_id
        self.metadata_sets.append((user_id, movie_id, prop, value))

    def set_movie_metadata(self, *, user_id, movie_id, movie_metadata):
        assert movie_id == self.movie_id
        self.movie_record.update(movie_metadata)
        self.movie_updates.append(("set_movie_metadata", user_id, movie_id, dict(movie_metadata)))

    def write_object(self, *, urn, object_data):
        self.objects[urn] = bytes(object_data)

    def write_object_from_path(self, *, urn, path):
        with open(path, "rb") as f:
            self.objects[urn] = f.read()

    def make_object_name(self, *, course_id, movie_id, ext, frame_number=None):
        assert course_id == self.movie_id_for_course
        assert movie_id == self.movie_id
        if frame_number is None:
            return f"{course_id}/{movie_id}{ext}"
        return f"{course_id}/{movie_id}/{frame_number:06d}{ext}"

    def make_urn(self, *, object_name):
        return f"s3://bucket/{object_name}"

    def course_id_for_movie_id(self, movie_id):
        assert movie_id == self.movie_id
        return self.movie_id_for_course

    def update_movie(self, movie_id, updates):
        assert movie_id == self.movie_id
        self.movie_record.update(updates)
        self.movie_updates.append(("update_movie", movie_id, dict(updates)))

    def update_table(self, table, key_value, updates):
        assert table is self.movies
        assert key_value == self.movie_id
        self.update_movie(key_value, updates)


def _patch_tracker_helpers(monkeypatch, env):
    monkeypatch.setattr(tracker_mod, "DDBO", lambda: env)
    monkeypatch.setattr(tracker_mod, "get_movie_data", env.get_movie_data)
    monkeypatch.setattr(tracker_mod, "get_movie_metadata", env.get_movie_metadata)
    monkeypatch.setattr(tracker_mod, "get_object_data", env.get_object_data)
    monkeypatch.setattr(tracker_mod, "get_movie_trackpoints", env.get_movie_trackpoints)
    monkeypatch.setattr(tracker_mod, "put_frame_trackpoints", env.put_frame_trackpoints)
    monkeypatch.setattr(tracker_mod, "write_object", env.write_object)
    monkeypatch.setattr(tracker_mod, "write_object_from_path", env.write_object_from_path)
    monkeypatch.setattr(tracker_mod, "make_object_name", env.make_object_name)
    monkeypatch.setattr(tracker_mod, "make_urn", env.make_urn)
    monkeypatch.setattr(tracker_mod, "course_id_for_movie_id", env.course_id_for_movie_id)


@pytest.mark.skipif(not BIG_MOVIE_FIXTURE.exists(), reason="big-test-movie.mp4 fixture missing")
def test_run_tracking_shrinks_zip_frames_even_if_db_width_is_analysis_size(tmp_path, monkeypatch):
    """
    End-to-end style check for run_tracking shrink decision:

    - Underlying movie bytes are large (bigger than ANALYSIS_FRAME_MAX_*).
    - DB metadata width/height already equal ANALYSIS_FRAME_MAX_* (as if Lambda
      get-frame?size=analysis had written analysis-sized dimensions).
    - run_tracking must still process the movie for tracking so that the JPEG
      frames inside the zip do not exceed ANALYSIS_FRAME_MAX_*.
    """
    movie_bytes = BIG_MOVIE_FIXTURE.read_bytes()
    movie_id = "m-big-test-track"
    env = _FakeEnv(movie_id=movie_id, movie_bytes=movie_bytes)
    _patch_tracker_helpers(monkeypatch, env)

    # Run tracking from frame 0; the fake backend will capture the zip in-memory.
    run_tracking(user_id="u-test", movie_id=movie_id, frame_start=0)

    # Find the zip URN and bytes written by TrackingCallback.
    zip_urns = [urn for urn in env.objects if urn.endswith(C.ZIP_MOVIE_EXTENSION)]
    assert zip_urns, "Expected a zip object to be written by run_tracking"
    zip_urn = zip_urns[-1]
    zip_bytes = env.objects[zip_urn]

    max_w = C.ANALYSIS_FRAME_MAX_WIDTH
    max_h = C.ANALYSIS_FRAME_MAX_HEIGHT
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".jpg")]
        assert names, "zip must contain JPEG frames"
        for name in names[:10]:
            data = zf.read(name)
            img = Image.open(io.BytesIO(data))
            img.load()
            w, h = img.size
            assert w <= max_w and h <= max_h, (
                f"{name} is {w}x{h}, exceeds analysis size {max_w}x{max_h}"
            )

    # Sanity check: LAST_FRAME_TRACKED (update_movie) and MOVIE_ZIPFILE_URN (set_metadata) should be updated.
    last_frame_keys = set()
    for entry in env.movie_updates:
        if isinstance(entry, tuple) and len(entry) >= 3 and isinstance(entry[2], dict):
            last_frame_keys.update(entry[2].keys())
    assert LAST_FRAME_TRACKED in last_frame_keys

    assert any(
        isinstance(entry, tuple)
        and len(entry) >= 3
        and isinstance(entry[2], dict)
        and MOVIE_ZIPFILE_URN in entry[2]
        for entry in env.movie_updates
    ), "MOVIE_ZIPFILE_URN must be written via update_table"


@pytest.mark.skipif(not BIG_MOVIE_FIXTURE.exists(), reason="big-test-movie.mp4 fixture missing")
def test_run_tracking_appends_to_existing_zip_for_later_batches(monkeypatch):
    """Later tracking batches should preserve earlier JPEGs in the zip archive."""
    movie_bytes = BIG_MOVIE_FIXTURE.read_bytes()
    movie_id = "m-big-test-zip-append"
    env = _FakeEnv(movie_id=movie_id, movie_bytes=movie_bytes)
    _patch_tracker_helpers(monkeypatch, env)
    env.movie_record["research_use"] = 0
    env.movie_record["credit_by_name"] = 0
    env.movie_record["attribution_name"] = None
    existing_zip_urn = env.make_urn(object_name=f"{env.movie_id_for_course}/{movie_id}.zip")
    env.movie_record[MOVIE_ZIPFILE_URN] = existing_zip_urn

    buf = io.BytesIO()
    original_jpg_bytes = None
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        img = Image.new("RGB", (1, 1), color="red")
        jpg_buf = io.BytesIO()
        img.save(jpg_buf, format="JPEG")
        original_jpg_bytes = jpg_buf.getvalue()
        zf.writestr("frame_0000.jpg", original_jpg_bytes)
    env.objects[existing_zip_urn] = buf.getvalue()

    monkeypatch.setattr(
        tracker_mod,
        "extract_movie_metadata",
        lambda movie_data: {
            "width": C.ANALYSIS_FRAME_MAX_WIDTH,
            "height": C.ANALYSIS_FRAME_MAX_HEIGHT,
            "total_frames": 3,
            "total_bytes": len(movie_data),
            "fps": "30",
        },
    )
    monkeypatch.setattr(tracker_mod, "convert_frame_to_jpeg", lambda _img, quality=60: jpg_buf.getvalue())
    monkeypatch.setattr(tracker_mod.mp4_metadata_lib, "add_comment_to_jpeg", lambda jpeg, _comment, quality=60: jpeg)

    def fake_track_movie(*, callback, **_kwargs):
        callback(frame_number=1, frame_data=object(), frame_trackpoints=[{"x": 1, "y": 2, "label": "A"}])
        callback(frame_number=2, frame_data=object(), frame_trackpoints=[{"x": 3, "y": 4, "label": "A"}])

    monkeypatch.setattr(tracker_mod, "track_movie", fake_track_movie)

    run_tracking(user_id="u-test", movie_id=movie_id, frame_start=1)

    zip_urns = [urn for urn in env.objects if urn.endswith(C.ZIP_MOVIE_EXTENSION)]
    assert zip_urns, "Expected a zip object to be written by run_tracking"
    zip_bytes = env.objects[zip_urns[-1]]
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = sorted(name for name in zf.namelist() if name.lower().endswith(".jpg"))
        assert names == ["frame_0000.jpg", "frame_0001.jpg", "frame_0002.jpg"]
        assert zf.read("frame_0000.jpg") == original_jpg_bytes
        assert zf.read("frame_0001.jpg") == original_jpg_bytes
        assert zf.read("frame_0002.jpg") == original_jpg_bytes
