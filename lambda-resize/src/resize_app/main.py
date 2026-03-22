"""
Lambda HTTP API and SQS entry point. Parses the event and delegates to API handlers.
API's primary function:
- resize, rotate, track, and code an MP3 of the movie.
- Creates a ZIP of the tracking with the rotated frames.
- Renders into the frames.
- Uses all the final frames to make a new mp4 that is also uploaded.

Methods:
/resize-api/v1/ping
/resize-api/v1/first-frame
/resize-api/v1/trace-movie


"""

import time
import sys
from typing import Any, Dict

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, CORSConfig, Response
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.utilities.batch import (
    BatchProcessor,
    EventType,
    process_partial_response,
)

from . import movie_glue
from . import mpeg_jpeg_zip
from . import lambda_tracking_handler

LOGGER = Logger(service="planttracer")

# Permissive CORS automatically applied to all routes
cors_config = CORSConfig(
    allow_origin="*",
    allow_headers=["*"]
)

app = APIGatewayHttpResolver(cors=cors_config)

@app.get("/resize-api/v1/ping")
def api_ping() -> Dict[str, Any]:
    LOGGER.info("ping")
    return {
        "error": False,
        "message": "ok",
        "time": time.time(),
        "path": sys.path
    }

@app.get("/resize-api/v1/first-frame")
def handle_first_frame() -> Any:
    """GET /api/v1/first-frame.
    Returns the first frame (frame 0) with proper rotation.
    :param api_key: the actual api_key
    :param movie_id: the movie_id of the movie
    Note: special values for movie_id:
    'red-0'   - a 640x480 red rectangle not rotated
    'red-90'  - a 640x480 red rectangle rotated 90 degrees
    'red-180' - a 640x480 red rectangle rotated 180 degrees
    'red-270' - a 640x480 red rectangle rotated 270 degrees
    """

    api_key = app.current_event.get_query_string_value(name="api_key", default_value=None)
    movie_id = app.current_event.get_query_string_value(name="movie_id", default_value=None)
    LOGGER.info("first_frame movie_id=%s",movie_id)
    match movie_id:
        case "red-0":
            data = mpeg_jpeg_zip.generate_test_jpeg(0)
        case "red-90":
            data = mpeg_jpeg_zip.generate_test_jpeg(90)
        case "red-180":
            data = mpeg_jpeg_zip.generate_test_jpeg(180)
        case "red-270":
            data = mpeg_jpeg_zip.generate_test_jpeg(270)
        case _:
            try:
                obj = movie_glue.get_movie_url_and_rotation(api_key=api_key, movie_id=movie_id)
                frame = mpeg_jpeg_zip.get_first_frame_from_url(obj.signed_url,obj.rotation)
                data = mpeg_jpeg_zip.convert_frame_to_jpeg(frame)
            except ValueError as e:
                LOGGER.exception("e=%s",e)
                return Response(status_code=403, body=str(e.args))

    return Response(status_code=200, content_type="image/jpeg", body=data)

@app.post("/resize-api/v1/trace-movie")
def handle_post_actions():
    """Queue the tracing of the movie"""
    LOGGER.info("trace-movie. movie_id=%s",movie_id)
    api_key = app.current_event.get_query_string_value(name="api_key")
    if not api_key:
        raise ValueError("api_key must be provided")
    movie_id = app.current_event.get_query_string_value(name="movie_id")
    if not movie_id:
        raise ValueError("movie_id must be provided")
    frame_start = app.current_event.get_query_string_value(name="frame_start") or 0

    return movie_glue.queue_tracing(api_key, movie_id, frame_start)

@LOGGER.inject_lambda_context(log_event=True)
def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """Unified Lambda entrypoint: dispatch between HTTP API and SQS events."""
    if isinstance(event, dict) and "Records" in event:
        # Route to SQS handler for partial batch processing
        return process_partial_response( event=event, context=context,
                                         processor=BatchProcessor(event_type=EventType.SQS),
                                         record_handler=lambda_tracking_handler.process_tracking_record)
    # Powertools resolves HTTP events natively
    return app.resolve(event, context)
