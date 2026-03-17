"""Test that tracking shrinks large movies for zip frames even when DB width/height
already reflect analysis size (e.g. after get-frame?size=analysis).
"""

import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image  # pylint: disable=import-outside-toplevel

from resize_app.tracker import (
    TrackingEnv,
    run_tracking,
)
from resize_app.src.app.constants import C
from resize_app.src.app.odb import (
    LAST_FRAME_TRACKED,
    MOVIE_DATA_URN,
    MOVIE_ZIPFILE_URN,
)


BIG_MOVIE_FIXTURE = (
    Path(__file__).resolve().parent.parent.parent
    / "tests"
    / "data"
    / "big-test-movie.mp4"
)


class _FakeEnv(TrackingEnv):
    """Minimal TrackingEnv for exercising run_tracking shrink logic."""

    def __init__(self, movie_id: str, movie_bytes: bytes):
        self.movie_id = movie_id
        self._movie_bytes = movie_bytes
        # Simulate DB metadata after Lambda get-frame(size=analysis) has already
        # written analysis-sized width/height (640x480), even though the actual
        # movie bytes are larger. This is the bug scenario we want to cover.
        self._movie_record = {
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

    # TrackingEnv interface
    def get_movie_data(self, movie_id):
        assert movie_id == self.movie_id
        return self._movie_bytes

    def get_movie_metadata(self, movie_id):
        assert movie_id == self.movie_id
        return dict(self._movie_record)

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
        self._movie_record.update(movie_metadata)
        self.movie_updates.append(("set_movie_metadata", user_id, movie_id, dict(movie_metadata)))

    def write_object(self, *, urn, data):
        self.objects[urn] = bytes(data)

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
        self._movie_record.update(updates)
        self.movie_updates.append(("update_movie", movie_id, dict(updates)))


@pytest.mark.skipif(not BIG_MOVIE_FIXTURE.exists(), reason="big-test-movie.mp4 fixture missing")
def test_run_tracking_shrinks_zip_frames_even_if_db_width_is_analysis_size(tmp_path):
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

    # Run tracking from frame 0; TrackingCallback will build a zip and env.write_object
    # will capture it in env.objects under a *_mp4.zip URN.
    run_tracking(user_id="u-test", movie_id=movie_id, frame_start=0, env=env)

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
        isinstance(prop, str) and prop == MOVIE_ZIPFILE_URN
        for (_user, _mid, prop, _value) in env.metadata_sets
    ), "MOVIE_ZIPFILE_URN must be written via set_metadata"

