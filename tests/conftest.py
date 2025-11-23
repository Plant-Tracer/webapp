"""
conftest.py shares fixtures across multiple files.
It is automatically imported at the start of all other pytest files in this directory and those below it.
There can be a conftest for each directory
See - https://stackoverflow.com/questions/34466027/what-is-conftest-py-for-in-pytest
"""

import logging
import os
import time
import threading
from os.path import abspath, dirname, join

import pytest
from werkzeug.serving import make_server
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException

from app import flask_app

# Import fixtures so pytest can discover them
from .fixtures.local_aws import local_ddb, local_s3, new_course, api_key, new_movie  # noqa: F401, E402 pylint: disable=unused-import
from .fixtures.localmail_config import mailer_config  # noqa: F401, E402  pylint: disable=unused-import
from .fixtures.app_client import client  # noqa: F401, E402 pylint: disable=unused-import

MY_DIR = dirname(abspath(__file__))
GIT_ROOT = dirname(MY_DIR)
SRC_DIR = join(GIT_ROOT, "src")
APP_DIR = join(SRC_DIR, "app")

logger = logging.getLogger(__name__)


class ServerThread(threading.Thread):
    """Run Flask server in a background thread for testing."""

    def __init__(self, app, port=8765):
        threading.Thread.__init__(self, daemon=True)
        self.server = make_server('127.0.0.1', port, app)

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()


@pytest.fixture(scope="module")
def live_server(local_ddb, local_s3):
    """Start a live Flask server for Selenium tests.

    Depends on local_ddb and local_s3 fixtures to ensure AWS services are available.
    """
    app = flask_app.app
    app.config['TESTING'] = True

    # Use a different port to avoid conflicts
    port = 8765
    server = ServerThread(app, port)
    server.start()

    # Give server time to start
    time.sleep(2)

    yield f"http://127.0.0.1:{port}"

    server.shutdown()


@pytest.fixture(scope="function")
def chrome_driver():
    """Fixture to provide a configured Chrome/Chromium WebDriver."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    # Set Chrome path if specified in environment
    if 'CHROME_PATH' in os.environ:
        options.binary_location = os.environ['CHROME_PATH']

    try:
        driver = webdriver.Chrome(options=options)
        yield driver
        driver.quit()
    except WebDriverException as e:
        pytest.skip(f"Chrome/Chromium not available: {e}")
