#
# conftest.py shares fixtures across multiple files.
# It is automatically imported at the start of all other pytest files in this directory and those below it.
# There can be a conftest for each directory
# See - https://stackoverflow.com/questions/34466027/what-is-conftest-py-for-in-pytest

import sys
from os.path import abspath, dirname,join
import pytest

MY_DIR = dirname(abspath(__file__))
APP_DIR = dirname(MY_DIR)
DEPLOY_DIR   = join(APP_DIR,'deploy')
sys.path.append(APP_DIR)
sys.path.append(MY_DIR)

from endpoint_test import http_endpoint
