import logging

from tests.fixtures.local_aws import (  # pylint: disable=unused-import
    local_ddb,
    local_s3,
    new_course,
    new_movie,
)

# Suppress verbose logging from urllib3 and selenium
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('selenium').setLevel(logging.WARNING)
