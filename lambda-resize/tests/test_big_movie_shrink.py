"""Test that a large movie is shrunk to analysis size and MOVIE_DATA_URN becomes *_processed.mp4."""
# pylint: disable=duplicate-code  # _FakeBody/_FakeS3/_FakeDDBO mirror test_rotate_and_zip for same API

import io
import zipfile
from pathlib import Path

from resize_app import resize
from resize_app.src.app.constants import C, logger

# Fixture path: test fails with an error if this file is missing.
BIG_MOVIE_FIXTURE = Path(__file__).resolve().parent / "data" / "big-test-movie.mp4"


def test_big_movie_tracking_uses_processed_mp4_and_shrunk_zip(monkeypatch):
    """
    End-to-end style test (Lambda-level) for a large movie:

    - Simulate an existing big MP4 in S3 and a movies row with movie_data_urn pointing to it.
    - Run rotate-and-zip / tracking path so that:
      - MOVIE_DATA_URN is updated to point to a *_processed.mp4.
      - The processed MP4 has ANALYSIS_FRAME_MAX_* dimensions.
      - The generated zip contains JPEG frames whose dimensions do not exceed ANALYSIS_FRAME_MAX_*.
    - Validate movie_data_urn and zip contents against constants.ANALYSIS_FRAME_MAX_*.

    Requires lambda-resize/tests/data/big-test-movie.mp4; fails with an error if missing.
    """
    assert BIG_MOVIE_FIXTURE.exists(), f"Fixture required but missing: {BIG_MOVIE_FIXTURE}"

    big_bytes = BIG_MOVIE_FIXTURE.read_bytes()
    BIG_MOVIE_ID = "m-big-test-movie"
    BIG_MOVIE_COURSE = "BIGCOURSE"

    class _FakeBody:
        def __init__(self, data: bytes):
            self._data = data

        def read(self):
            return self._data

    class _FakeS3:
        def __init__(self, movie_bytes: bytes):
            self.movie_bytes = movie_bytes
            self.get_calls = []
            self.put_calls = []

        def get_object(self, Bucket, Key):  # pylint: disable=unused-argument
            self.get_calls.append((Bucket, Key))
            return {"Body": _FakeBody(self.movie_bytes)}

        def put_object(self, **kwargs):  # pylint: disable=unused-argument
            self.put_calls.append(kwargs)

    class _FakeLogs:
        def put_item(self, **kwargs):  # pylint: disable=unused-argument
            pass

    class _FakeDDBO:
        def __init__(self):
            self.movies = object()
            self.logs = _FakeLogs()
            self.movie_row = {
                resize.MOVIE_DATA_URN: "s3://bucket/original-big.mp4",
                "course_id": BIG_MOVIE_COURSE,
                "width": 1920,
                "height": 1080,
            }
            self.update_calls = []

        def get_movie(self, movie_id):  # pylint: disable=unused-argument
            assert movie_id == BIG_MOVIE_ID
            return dict(self.movie_row)

        def update_table(self, table, movie_id, attrs):  # pylint: disable=unused-argument
            assert movie_id == BIG_MOVIE_ID
            self.update_calls.append(dict(attrs))
            # Keep an in-memory view of movie_data_urn for later assertions.
            if resize.MOVIE_DATA_URN in attrs:
                self.movie_row[resize.MOVIE_DATA_URN] = attrs[resize.MOVIE_DATA_URN]

    ddbo = _FakeDDBO()
    s3 = _FakeS3(big_bytes)

    monkeypatch.setattr(resize, "DDBO", lambda: ddbo)
    monkeypatch.setattr(resize, "_s3_client", lambda: s3)

    # When we ask Lambda to build the zip, it should:
    # - shrink/rotate the movie (writing *_processed.mp4)
    # - update MOVIE_DATA_URN to point to that processed URN
    # - build the zip from the processed movie
    payload = {
        "movie_id": BIG_MOVIE_ID,
        "rotation_steps": 0,
    }

    resp = resize.api_rotate_and_zip(payload)
    body = resp.get("body") or "{}"
    assert '"error": false' in body.lower()

    # Assert that MOVIE_DATA_URN now points to *_processed.mp4.
    final_urn = ddbo.movie_row[resize.MOVIE_DATA_URN]
    assert final_urn.endswith(C.MOVIE_PROCESSED_EXTENSION), final_urn

    # Extract the uploaded zip bytes from fake S3 and inspect a few frames.
    zip_puts = [c for c in s3.put_calls if c.get("ContentType") == "application/zip"]
    assert zip_puts, "expected a zip put_object"
    zip_body = zip_puts[-1]["Body"]
    max_w = C.ANALYSIS_FRAME_MAX_WIDTH
    max_h = C.ANALYSIS_FRAME_MAX_HEIGHT
    count = 0
    with zipfile.ZipFile(io.BytesIO(zip_body), "r") as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".jpg")]
        assert names, "zip must contain JPEG frames"
        for name in names[:10]:
            count += 1
            data = zf.read(name)
            from PIL import Image  # pylint: disable=import-outside-toplevel

            img = Image.open(io.BytesIO(data))
            img.load()
            w, h = img.size
            assert w <= max_w and h <= max_h, f"{name} is {w}x{h}, exceeds {max_w}x{max_h}"
    logger.info("test_big_movie_shrink count=%s", count)
