"""Tests for lambda-resize api_get_frame (GET api/v1/frame)."""

import base64

import pytest

from resize_app import resize


class _FakeBody:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data


class _FakeS3:
    def __init__(self, movie_bytes: bytes):
        self.movie_bytes = movie_bytes

    def get_object(self, Bucket, Key):  # pylint: disable=unused-argument
        return {"Body": _FakeBody(self.movie_bytes)}


@pytest.fixture
def valid_event():
    """Minimal event with query params for get-frame."""
    return {
        "queryStringParameters": {
            "api_key": "test-api-key",
            "movie_id": "m0000000-0000-0000-0000-000000000001",
            "frame_number": "0",
            "size": "analysis",
        }
    }


@pytest.fixture
def fake_jpeg_bytes():
    """Minimal JPEG bytes (valid JPEG header)."""
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


def test_get_frame_returns_400_when_api_key_missing(valid_event):
    """Missing api_key returns 400."""
    valid_event["queryStringParameters"].pop("api_key", None)
    resp = resize.api_get_frame(valid_event)
    assert resp["statusCode"] == 400
    body = __import__("json").loads(resp["body"])
    assert body.get("error") is True


def test_get_frame_returns_401_when_api_key_invalid(valid_event, monkeypatch):
    """Invalid api_key returns 401."""
    class FakeDDBO:
        def get_api_key_dict(self, api_key):  # pylint: disable=unused-argument
            return None

    monkeypatch.setattr(resize, "DDBO", FakeDDBO)
    resp = resize.api_get_frame(valid_event)
    assert resp["statusCode"] == 401
    body = __import__("json").loads(resp["body"])
    assert body.get("error") is True


def test_get_frame_returns_200_and_jpeg_when_authorized(
    valid_event, fake_jpeg_bytes, monkeypatch
):
    """With valid auth and S3 movie, returns 200 and base64 JPEG."""
    movie_bytes = b"fake-mp4-bytes"
    s3 = _FakeS3(movie_bytes)

    class FakeDDBO:
        def get_api_key_dict(self, api_key):  # pylint: disable=unused-argument
            return {"user_id": "u1", "enabled": True}

        def get_user(self, user_id):  # pylint: disable=unused-argument
            return {"enabled": True}

    def fake_can_access_movie(*, user_id, movie_id):  # pylint: disable=unused-argument
        return {
            "movie_id": movie_id,
            "movie_data_urn": "s3://bucket/course1/movie1.mov",
            "width": None,
            "height": None,
        }

    def fake_extract_single_frame(data, frame_number):  # pylint: disable=unused-argument
        return fake_jpeg_bytes

    monkeypatch.setattr(resize, "DDBO", lambda: FakeDDBO())
    monkeypatch.setattr(resize.odb, "can_access_movie", fake_can_access_movie)
    monkeypatch.setattr(resize.odb, "is_movie_id", lambda mid: bool(mid and mid.startswith("m")))
    monkeypatch.setattr(resize, "_s3_client", lambda: s3)
    monkeypatch.setattr(resize, "extract_single_frame", fake_extract_single_frame)
    monkeypatch.setattr(resize, "resize_jpeg_to_fit", lambda jpg, _w, _h: jpg)
    monkeypatch.setattr(resize.odb, "set_metadata", lambda *a, **k: None)

    resp = resize.api_get_frame(valid_event)

    assert resp["statusCode"] == 200
    assert resp["headers"].get("Content-Type") == "image/jpeg"
    assert resp.get("isBase64Encoded") is True
    decoded = base64.b64decode(resp["body"])
    assert decoded == fake_jpeg_bytes
