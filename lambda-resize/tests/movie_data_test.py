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
        "queryStringParameters": {
            key: value for (key, value) in (part.split("=", 1) for part in query.split("&") if part)
        },
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
