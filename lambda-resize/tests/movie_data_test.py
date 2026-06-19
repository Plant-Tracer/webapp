import json
from types import SimpleNamespace
from unittest.mock import patch

from resize_app.main import lambda_handler


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
    event = make_http_event("/api/v1/movie-data", "api_key=test-key&movie_id=m123&format=json")
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
        {"movie_id": "m123", "frame_start": 7, "frame_end": 20},
        {"x-api-key": "test-key"},
    )
    with patch("resize_app.main.movie_glue.prepare_tracing_request") as prepare, \
         patch("resize_app.main.movie_glue.queue_tracing", return_value={"error": False, "message": "queued"}) as queue:
        response = lambda_handler(event, DummyContext())

    assert response["statusCode"] == 200
    prepare.assert_called_once_with(api_key="test-key", movie_id="m123", frame_start=7, frame_end=20)
    queue.assert_called_once_with("test-key", "m123", 7, 20)
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
