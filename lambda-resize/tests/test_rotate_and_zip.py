import json

import pytest

from resize_app import resize


class _FakeBody:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data


class _FakeS3:
    def __init__(self, data: bytes):
        self.data = data
        self.get_calls = []
        self.put_calls = []

    def get_object(self, Bucket, Key):  # pylint: disable=unused-argument
        self.get_calls.append((Bucket, Key))
        return {"Body": _FakeBody(self.data)}

    def put_object(self, **kwargs):  # pylint: disable=unused-argument
        self.put_calls.append(kwargs)


class _FakeLogs:
    def put_item(self, **kwargs):  # pylint: disable=unused-argument
        pass


class _FakeDDBO:
    def __init__(self):
        self.movies = object()
        self.logs = _FakeLogs()
        self.get_movie_calls = []
        self.update_calls = []

    def get_movie(self, movie_id):  # pylint: disable=unused-argument
        self.get_movie_calls.append(movie_id)
        # Minimal movie row for api_rotate_and_zip
        return {
            resize.MOVIE_DATA_URN: "s3://bucket/key",
            "course_id": "COURSE1",
        }

    def update_table(self, table, movie_id, attrs):  # pylint: disable=unused-argument
        self.update_calls.append((movie_id, dict(attrs)))


@pytest.fixture
def fake_env(monkeypatch):
    """Set up fake DDB and S3 for lambda rotate-and-zip tests."""
    ddbo = _FakeDDBO()
    s3 = _FakeS3(b"original-movie-bytes")

    monkeypatch.setattr(resize, "DDBO", lambda: ddbo)
    monkeypatch.setattr(resize, "_s3_client", lambda: s3)

    return ddbo, s3


def _decode_resp_body(resp):
    body = resp.get("body") or ""
    return json.loads(body)


def test_rotate_and_zip_zero_steps_builds_zip_without_rotation(monkeypatch, fake_env):
    """rotation_steps=0 should not rotate, but must still build and upload a zip."""
    ddbo, s3 = fake_env

    # Use a dict with an always-subscriptable default for zip_args so
    # pylint understands the type.
    calls = {"rotated": False, "zip_args": {}}

    def fake_rotate_video_av(data, steps):  # pylint: disable=unused-argument
        calls["rotated"] = True
        return b"rotated-bytes"

    def fake_video_frames_to_zip_av(data, jpeg_quality=60, progress_cb=None, progress_every=5, target_wh=(640, 480)):  # noqa: D401
        # Record the data we were asked to zip; we expect the *original* movie bytes.
        calls["zip_args"] = {
            "data": data,
            "jpeg_quality": jpeg_quality,
            "progress_cb_is_none": progress_cb is None,
            "progress_every": progress_every,
        }
        return b"zip-bytes"

    monkeypatch.setattr(resize, "rotate_video_av", fake_rotate_video_av)
    monkeypatch.setattr(resize, "video_frames_to_zip_av", fake_video_frames_to_zip_av)

    payload = {
        "movie_id": "m0000000-0000-0000-0000-000000000000",
        "rotation_steps": 0,
    }

    resp = resize.api_rotate_and_zip(payload)

    # With the current bug (0 clamped up to 1), this assertion will FAIL
    # because rotate_video_av *is* called. After the fix, it should pass.
    assert calls["rotated"] is False, "rotate_video_av should not be called for rotation_steps=0"

    # Zip must still be built from the original movie bytes and uploaded.
    assert calls["zip_args"] is not None, "video_frames_to_zip_av should be called to build zip"
    zip_args = calls["zip_args"]
    assert isinstance(zip_args, dict)
    assert zip_args["data"] == b"original-movie-bytes"

    # There should be a put_object for the zip with correct content type.
    assert any(
        c.get("ContentType") == "application/zip" and c.get("Body") == b"zip-bytes"
        for c in s3.put_calls
    ), "zip file was not uploaded with expected content"

    body = _decode_resp_body(resp)
    assert body.get("error") is False

    # Final DDB update must include movie_zipfile_urn.
    assert any(
        "movie_zipfile_urn" in attrs for (_mid, attrs) in ddbo.update_calls
    ), "movie_zipfile_urn was not recorded in DDB for zero-rotation zip"

    # Zip must be built with progress callback (proper zip path).
    assert zip_args.get("progress_cb_is_none") is False, "zip should be built with progress_cb"


def test_rotate_and_zip_one_step_rotates_and_builds_zip(monkeypatch, fake_env):
    """rotation_steps=1 should rotate and then build/upload a zip from the rotated bytes."""
    ddbo, s3 = fake_env

    calls = {"rotated": False, "rotated_bytes": None, "zip_args": {}}

    def fake_rotate_video_av(data, steps):  # pylint: disable=unused-argument
        calls["rotated"] = True
        calls["rotated_bytes"] = b"rotated-" + data
        return calls["rotated_bytes"]

    def fake_video_frames_to_zip_av(data, jpeg_quality=60, progress_cb=None, progress_every=5, target_wh=(640, 480)):
        calls["zip_args"] = {
            "data": data,
            "jpeg_quality": jpeg_quality,
            "progress_cb_is_none": progress_cb is None,
            "progress_every": progress_every,
        }
        return b"zip-bytes"

    monkeypatch.setattr(resize, "rotate_video_av", fake_rotate_video_av)
    monkeypatch.setattr(resize, "video_frames_to_zip_av", fake_video_frames_to_zip_av)

    payload = {
        "movie_id": "m0000000-0000-0000-0000-000000000000",
        "rotation_steps": 1,
    }

    resp = resize.api_rotate_and_zip(payload)

    assert calls["rotated"] is True, "rotate_video_av should be called for rotation_steps=1"
    assert calls["zip_args"] is not None, "video_frames_to_zip_av should be called"
    zip_args = calls["zip_args"]
    assert isinstance(zip_args, dict)
    # For rotation, zip must be built from the rotated bytes, not the original.
    assert zip_args["data"] == calls["rotated_bytes"]

    # Expect a zip upload and a recorded URN as above.
    assert any(
        c.get("ContentType") == "application/zip" and c.get("Body") == b"zip-bytes"
        for c in s3.put_calls
    ), "zip file was not uploaded with expected content for rotation"

    body = _decode_resp_body(resp)
    assert body.get("error") is False
    assert any(
        "movie_zipfile_urn" in attrs for (_mid, attrs) in ddbo.update_calls
    ), "movie_zipfile_urn was not recorded in DDB for rotated zip"

    # Zip must be built with progress callback (proper zip path).
    assert zip_args.get("progress_cb_is_none") is False, "zip should be built with progress_cb"


def test_zip_is_created_and_uploaded_with_expected_content(monkeypatch, fake_env):
    """Regardless of rotation, a zip is created from the correct source and uploaded to S3."""
    ddbo, s3 = fake_env
    zip_body = b"fake-zip-content"

    def fake_video_frames_to_zip_av(data, jpeg_quality=60, progress_cb=None, progress_every=5, target_wh=(640, 480)):
        return zip_body

    monkeypatch.setattr(resize, "video_frames_to_zip_av", fake_video_frames_to_zip_av)

    payload = {
        "movie_id": "m0000000-0000-0000-0000-000000000000",
        "rotation_steps": 0,
    }
    resp = resize.api_rotate_and_zip(payload)

    body = _decode_resp_body(resp)
    assert body.get("error") is False

    # Zip must have been uploaded with the exact bytes returned by video_frames_to_zip_av.
    zip_puts = [c for c in s3.put_calls if c.get("ContentType") == "application/zip"]
    assert len(zip_puts) == 1, "exactly one zip put_object expected"
    assert zip_puts[0].get("Body") == zip_body
    assert "movie_zipfile_urn" in str(ddbo.update_calls), "movie_zipfile_urn must be set in DDB"

