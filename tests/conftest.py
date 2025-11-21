"""
conftest.py shares fixtures across multiple files.
It is automatically imported at the start of all other pytest files in this directory and those below it.
There can be a conftest for each directory
See - https://stackoverflow.com/questions/34466027/what-is-conftest-py-for-in-pytest
"""

import logging
import sys
from os.path import abspath, dirname, join

MY_DIR = dirname(abspath(__file__))
GIT_ROOT = dirname(MY_DIR)

SRC_DIR = join(GIT_ROOT, "src")
sys.path.append(SRC_DIR)

APP_DIR = join(SRC_DIR, "app")
sys.path.append(APP_DIR)

print("sys.path=",sys.path)
logger = logging.getLogger(__name__)

# Import fixtures so pytest can discover them
from .fixtures.local_aws import local_ddb, local_s3, new_course, api_key, new_movie  # noqa: F401, E402
from .fixtures.localmail_config import mailer_config  # noqa: F401, E402
from .fixtures.app_client import client  # noqa: F401, E402
