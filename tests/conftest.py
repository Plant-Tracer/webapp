#
# conftest.py shares fixtures across multiple files.
# It is automatically imported at the start of all other pytest files.
# See - https://stackoverflow.com/questions/34466027/what-is-conftest-py-for-in-pytest

import pytest
from endpoint_test import http_endpoint
