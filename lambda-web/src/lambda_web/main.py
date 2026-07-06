"""Lambda entry point for the Flask web application."""

from typing import Any

import apig_wsgi
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEventV2

from app.flask_app import app as flask_app

RAW_PATH = "rawPath"
REQUEST_CONTEXT = "requestContext"
HTTP = "http"
PATH = "path"
STAGE = "stage"

LOGGER = Logger(service="planttracer-web")
_wsgi_handler: Any = apig_wsgi.make_lambda_handler(flask_app)
_FLASK_ROUTES = tuple(sorted(str(rule) for rule in flask_app.url_map.iter_rules()))
LOGGER.info("registered_flask_routes count=%s routes=%s", len(_FLASK_ROUTES), _FLASK_ROUTES)


def _strip_stage_prefix(path: str, stage: str) -> str:
    if not stage or stage == "$default":
        return path
    prefix = f"/{stage}"
    if path == prefix:
        return "/"
    if path.startswith(f"{prefix}/"):
        return path[len(prefix):]
    return path


def _normalize_stage_path(event: dict[str, Any]) -> dict[str, Any]:
    if event.get("version") != "2.0":
        return event
    try:
        api_event = APIGatewayProxyEventV2(event)
        request_context = api_event.request_context
        stage = request_context.stage
        raw_path = api_event.raw_path
    except (KeyError, TypeError):
        return event

    normalized_path = _strip_stage_prefix(raw_path, stage)
    LOGGER.info(
        "lambda_web_request raw_path=%s normalized_path=%s stage=%s route_key=%s",
        raw_path,
        normalized_path,
        stage,
        api_event.route_key,
    )
    if normalized_path == raw_path:
        return event

    normalized = dict(event)
    normalized[RAW_PATH] = normalized_path
    if isinstance(normalized.get(PATH), str):
        normalized[PATH] = _strip_stage_prefix(normalized[PATH], stage)

    normalized_context = dict(event[REQUEST_CONTEXT])
    http = normalized_context.get(HTTP)
    if isinstance(http, dict) and isinstance(http.get(PATH), str):
        normalized_http = dict(http)
        normalized_http[PATH] = _strip_stage_prefix(normalized_http[PATH], stage)
        normalized_context[HTTP] = normalized_http
    normalized[REQUEST_CONTEXT] = normalized_context
    return normalized


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return _wsgi_handler(_normalize_stage_path(event), context)
