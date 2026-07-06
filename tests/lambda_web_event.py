"""Shared Lambda-web API Gateway event helpers for tests."""


class DummyContext:
    function_name = "test-lambda-web"
    memory_limit_in_mb = 128
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-web"
    aws_request_id = "test-request-id"


def make_http_event(
    path: str,
    *,
    method: str = "GET",
    body: str = "",
    content_type: str | None = None,
    cookies: list[str] | None = None,
    stage: str = "$default",
) -> dict:
    headers = {
        "host": "lambda-web.test",
        "x-forwarded-for": "127.0.0.1",
        "x-forwarded-port": "443",
        "x-forwarded-proto": "https",
    }
    if content_type:
        headers["content-type"] = content_type
    event = {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": headers,
        "requestContext": {
            "stage": stage,
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
            },
        },
        "body": body,
        "isBase64Encoded": False,
    }
    if cookies:
        event["cookies"] = cookies
    return event
