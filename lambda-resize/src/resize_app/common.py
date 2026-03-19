"""
Main entry point for AWS Lambda Dashboard

Generate the https://camera.planttracer.org/ home page.
Runs the camera.
"""

# at top of home_app/home.py (module import time)
from os.path import dirname
import functools
import logging
import os
import json
from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, CORSConfig, Response

MY_DIR = dirname(__file__)
LOGGER = Logger(service="planttracer")

__version__ = "0.1.0"

def json_error(status_code: int, message: str) -> Response:
    """Helper for 400/500 errors so Powertools handles them natively."""
    return Response(
        status_code=status_code,
        content_type="application/json",
        body=json.dumps({"error": True, "message": message})
    )


def resp_redirect(location: str, status: int = 302) -> Dict[str, Any]:
    return Response(
        status_code=302,
        headers={"Location": location},
        body=f"Redirecting to <a href='{location}'>{location}</a>"
    )
