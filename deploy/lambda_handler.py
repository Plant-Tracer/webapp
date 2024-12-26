"""
Handle the AWS Lambda function
"""

import os
import logging

from apig_wsgi import make_lambda_handler

from .bottle_app import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)

def dump_files(path="."):
    """For debugging."""
    for (root, dirs, files) in os.walk(path): # pylint: disable=unused-variable
        for fn in files:
            logging.error("%s/%s",root,fn)

if os.environ.get('DEBUG_DUMP_FILES', 'NO') == 'YES':
    dump_files('/')

# Configure this as your entry point in AWS Lambda
#
lambda_handler = make_lambda_handler(app)
