import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from resize_app import movie_glue
from resize_app.main import lambda_handler
from resize_app.src.app import s3_presigned


class DummyContext:
    function_name = "test-movie-data"
    memory_limit_in_mb = 128
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-movie-data"
    aws_request_id = "test-request-id"


def make_http_event(path: str, query: str) -> dict:
    return {
        "version": "2.0",
        "routeKey": f"GET {path}",
        "rawPath": path,
        "rawQueryString": query,
        "queryStringParameters": dict(part.split("=", 1) for part in query.split("&") if part),
        "headers": {},
        "requestContext": {
            "stage": "$default",
            "http": {
                "method": "GET",
                "path": path,
                "sourceIp": "127.0.0.1",
            }
        },
        "isBase64Encoded": False,
    }


def make_post_event(path: str, body: dict | None, headers: dict | None = None) -> dict:
    return {
        "version": "2.0",
        "routeKey": f"POST {path}",
        "rawPath": path,
        "rawQueryString": "",
        "queryStringParameters": None,
        "headers": headers or {},
        "requestContext": {
            "stage": "$default",
            "http": {
                "method": "POST",
                "path": path,
                "sourceIp": "127.0.0.1",
            }
        },
        "body": "" if body is None else json.dumps(body),
        "isBase64Encoded": False,
    }


def test_movie_data_json_response():
    event = make_http_event("/resize-api/v1/movie-data", "api_key=test-key&movie_id=m123&format=json")
    mock_urls = SimpleNamespace(
        signed_movie_url="https://example.com/movie.mp4",
        signed_zipfile_url="https://example.com/movie.zip",
    )
    with patch("resize_app.main.movie_glue.get_movie_download_urls", return_value=mock_urls):
        response = lambda_handler(event, DummyContext())

    assert response["statusCode"] == 200
    data = json.loads(response["body"])
    assert data["error"] is False
    assert data["movie_id"] == "m123"
    assert data["url"] == "https://example.com/movie.mp4"
    assert data["zip_url"] == "https://example.com/movie.zip"


def test_movie_data_redirect_response():
    event = make_http_event("/resize-api/v1/movie-data", "api_key=test-key&movie_id=m123")
    mock_urls = SimpleNamespace(
        signed_movie_url="https://example.com/movie.mp4",
        signed_zipfile_url=None,
    )
    with patch("resize_app.main.movie_glue.get_movie_download_urls", return_value=mock_urls):
        response = lambda_handler(event, DummyContext())

    assert response["statusCode"] == 302
    assert response["headers"]["Location"] == "https://example.com/movie.mp4"


def test_trace_movie_requires_api_key_header():
    event = make_post_event("/resize-api/v1/trace-movie", {"movie_id": "m123"})

    response = lambda_handler(event, DummyContext())

    assert response["statusCode"] == 401
    assert "x-api-key header" in response["body"]


def test_process_upload_requires_authentication_and_movie_id():
    path = "/resize-api/v1/process-upload"
    response = lambda_handler(make_post_event(path, {"movie_id": "m123"}), DummyContext())
    assert response["statusCode"] == 401

    response = lambda_handler(
        make_post_event(path, None, {"X-API-Key": "test-key"}),
        DummyContext(),
    )
    assert response["statusCode"] == 400
    assert "Request body" in response["body"]

    response = lambda_handler(
        make_post_event(path, None, {"x-api-key": "test-key"}),
        DummyContext(),
    )
    assert response["statusCode"] == 400
    assert "Request body" in response["body"]

    response = lambda_handler(
        make_post_event(path, {"other": "value"}, {"x-api-key": "test-key"}),
        DummyContext(),
    )
    assert response["statusCode"] == 400
    assert "movie_id" in response["body"]


def test_process_upload_rejects_missing_s3_object(new_movie):
    movie_id = new_movie[movie_glue.odb.MOVIE_ID]
    ddbo = new_movie["ddbo"]
    movie = ddbo.get_movie(movie_id)
    bucket, _durable_key = s3_presigned.parse_s3_urn(
        urn=movie[movie_glue.MOVIE_DATA_URN],
    )
    staging_urn = s3_presigned.make_urn(
        bucket=bucket,
        object_name=s3_presigned.upload_staging_object_key(
            deployment_id="local",
            course_id=movie[movie_glue.odb.COURSE_ID],
            movie_id=movie_id,
        ),
    )
    ddbo.update_movie(
        movie_id,
        {
            movie_glue.UPLOAD_STAGING_URN: staging_urn,
            movie_glue.UPLOADED_AT: None,
            movie_glue.MOVIE_STATUS: movie_glue.MOVIE_STATE_UPLOADING,
        },
        touch_activity=False,
    )
    event = make_post_event(
        "/resize-api/v1/process-upload",
        {"movie_id": movie_id},
        {"x-api-key": new_movie[movie_glue.odb.API_KEY]},
    )

    response = lambda_handler(event, DummyContext())

    assert response["statusCode"] == 403
    assert "uploaded movie object is not available" in response["body"]


def test_complete_movie_upload_rejects_wrong_byte_count(new_movie):
    ddbo = new_movie["ddbo"]
    movie_id = new_movie[movie_glue.odb.MOVIE_ID]
    movie = ddbo.get_movie(movie_id)
    bucket, durable_key = s3_presigned.parse_s3_urn(
        urn=movie[movie_glue.MOVIE_DATA_URN],
    )
    staging_key = s3_presigned.upload_staging_object_key(
        deployment_id="local",
        course_id=movie[movie_glue.odb.COURSE_ID],
        movie_id=movie_id,
    )
    s3_presigned.s3_client().copy_object(
        Bucket=bucket,
        Key=staging_key,
        CopySource={"Bucket": bucket, "Key": durable_key},
    )
    ddbo.update_movie(
        movie_id,
        {
            movie_glue.UPLOAD_BYTES_EXPECTED: int(movie[movie_glue.TOTAL_BYTES]) + 1,
            movie_glue.UPLOAD_STAGING_URN: s3_presigned.make_urn(
                bucket=bucket,
                object_name=staging_key,
            ),
            movie_glue.UPLOADED_AT: None,
            movie_glue.MOVIE_STATUS: movie_glue.MOVIE_STATE_UPLOADING,
        },
        touch_activity=False,
    )

    with pytest.raises(ValueError, match="does not match expected size"):
        movie_glue.complete_movie_upload(
            api_key=new_movie[movie_glue.odb.API_KEY],
            movie_id=movie_id,
        )


def test_trace_movie_requires_body_and_movie_id():
    missing_body = make_post_event("/resize-api/v1/trace-movie", None, {"x-api-key": "test-key"})
    response = lambda_handler(missing_body, DummyContext())
    assert response["statusCode"] == 400
    assert "Request body" in response["body"]

    missing_movie_id = make_post_event("/resize-api/v1/trace-movie", {"frame_start": 0}, {"x-api-key": "test-key"})
    response = lambda_handler(missing_movie_id, DummyContext())
    assert response["statusCode"] == 400
    assert "movie_id" in response["body"]


def test_trace_movie_queues_with_optional_frame_end():
    event = make_post_event(
        "/resize-api/v1/trace-movie",
        {"movie_id": "m123", "frame_start": 7, "frame_end": 20,
         "analysis_lease_id": "lease-123"},
        {"x-api-key": "test-key"},
    )
    with patch("resize_app.main.movie_glue.prepare_tracing_request", return_value={"job_id": "j1"}) as prepare, \
         patch("resize_app.main.movie_glue.queue_tracing", return_value={"error": False, "message": "queued"}) as queue:
        response = lambda_handler(event, DummyContext())

    assert response["statusCode"] == 200
    prepare.assert_called_once_with(
        api_key="test-key", movie_id="m123", frame_start=7, frame_end=20,
        analysis_lease_id="lease-123")
    queue.assert_called_once_with("test-key", "m123", 7, 20, "j1")
    assert json.loads(response["body"]) == {"error": False, "message": "queued"}


def test_trace_movie_returns_403_for_validation_error():
    event = make_post_event(
        "/resize-api/v1/trace-movie",
        {"movie_id": "m123", "frame_start": 7},
        {"x-api-key": "test-key"},
    )
    with patch("resize_app.main.movie_glue.prepare_tracing_request", side_effect=ValueError("not allowed")):
        response = lambda_handler(event, DummyContext())

    assert response["statusCode"] == 403
    assert "not allowed" in response["body"]


def test_trace_movie_returns_json_for_active_lock():
    event = make_post_event(
        "/resize-api/v1/trace-movie",
        {"movie_id": "m123", "frame_start": 7},
        {"x-api-key": "test-key"},
    )
    with patch("resize_app.main.movie_glue.prepare_tracing_request",
               side_effect=movie_glue.odb.MovieTracingLocked("m123")):
        response = lambda_handler(event, DummyContext())

    assert response["statusCode"] == 409
    assert response["headers"]["Content-Type"] == "application/json"
    assert json.loads(response["body"]) == {
        "error": True,
        "message": "This movie is already being traced",
    }
