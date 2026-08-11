"""
conftest.py shares fixtures across multiple files.
It is automatically imported at the start of all other pytest files in this directory and those below it.
There can be a conftest for each directory
See - https://stackoverflow.com/questions/34466027/what-is-conftest-py-for-in-pytest
"""

import os
import time
import threading
import logging
from os.path import abspath, dirname, join
from typing import Generator

import urllib.parse
import pytest
from werkzeug.serving import make_server

# Set FFMPEG_PATH before importing flask_app if ffmpeg is available (for tests that use resize_app.tracer).
from app.constants import C
from app.paths import ffmpeg_path
_ffmpeg = ffmpeg_path()
if _ffmpeg:
    os.environ.setdefault(C.FFMPEG_PATH, _ffmpeg)

from app import flask_app  # pylint: disable=wrong-import-position
from app import local_lambda_debug  # pylint: disable=wrong-import-position
from app import odb_movie_data  # pylint: disable=wrong-import-position
from app.s3_presigned import s3_client  # pylint: disable=wrong-import-position

# Import fixtures so pytest can discover them (after env/path setup above)
from .fixtures.local_aws import local_ddb, local_s3, new_course, api_key, new_movie  # pylint: disable=wrong-import-position,unused-import
from .fixtures.localmail_config import mailer_config  # pylint: disable=wrong-import-position,unused-import
from .fixtures.app_client import client  # pylint: disable=wrong-import-position,unused-import

# Suppress verbose logging from urllib3 and selenium
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('selenium').setLevel(logging.WARNING)

pytest_plugins = ("browser_tests.chrome",)

# Cursor/Electron inject env vars that can make Chrome crash when launched as a subprocess (e.g. Selenium).
# Strip them so browser tests don't take down Chrome or the IDE.
for var in (
    "ELECTRON_RUN_AS_NODE",
    "ELECTRON_NO_ATTACH_CONSOLE",
    "NODE_OPTIONS",
    "CHROME_HEADLESS",
    "CHROME_NO_SANDBOX",
    "CHROME_DEVEL_SANDBOX",
):
    os.environ.pop(var, None)
for key in list(os.environ):
    if key.startswith("VSCODE_") or key.startswith("ELECTRON_"):
        os.environ.pop(key, None)



MY_DIR = dirname(abspath(__file__))
GIT_ROOT = dirname(MY_DIR)
SRC_DIR = join(GIT_ROOT, "src")
APP_DIR = join(SRC_DIR, "app")

class ServerThread(threading.Thread):
    """Run Flask server in a background thread for testing."""

    def __init__(self, app, port: int = 8765) -> None:
        threading.Thread.__init__(self, daemon=True)
        self.server = make_server('127.0.0.1', port, app)

    def run(self) -> None:
        self.server.serve_forever()

    def shutdown(self) -> None:
        self.server.shutdown()


@pytest.fixture(scope="module")
def live_server(local_ddb, local_s3) -> Generator[str, None, None]:
    """Start the live Flask and lambda-resize bridge servers for Selenium tests.

    Depends on local_ddb and local_s3 fixtures to ensure AWS services are available.
    """
    app = flask_app.app
    app.config['TESTING'] = True
    previous_lambda_api_base = os.environ.get(C.PLANTTRACER_LAMBDA_API_BASE)
    lambda_port = 9812
    os.environ[C.PLANTTRACER_LAMBDA_API_BASE] = f"http://127.0.0.1:{lambda_port}/"

    # Use a different port to avoid conflicts
    port = 8765
    server = ServerThread(app, port)
    lambda_server = ServerThread(local_lambda_debug.bridge_app, lambda_port)
    server.start()
    lambda_server.start()

    # Give server time to start
    time.sleep(2)

    yield f"http://127.0.0.1:{port}"

    server.shutdown()
    lambda_server.shutdown()
    if previous_lambda_api_base is None:
        os.environ.pop(C.PLANTTRACER_LAMBDA_API_BASE, None)
    else:
        os.environ[C.PLANTTRACER_LAMBDA_API_BASE] = previous_lambda_api_base


def get_movie_bytes(movie_id: str) -> bytes:
    """Test-only helper: fetch full movie bytes for a given movie_id."""
    movie = odb_movie_data.DDBO().get_movie(movie_id)
    urn = movie.get(odb_movie_data.MOVIE_DATA_URN)
    if not urn:
        raise RuntimeError(f"Movie {movie_id} has no data URN")
    o = urllib.parse.urlparse(urn)
    if o.scheme != "s3":
        return odb_movie_data.read_object(urn)
    return s3_client().get_object(Bucket=o.netloc, Key=o.path[1:])["Body"].read()
