"""
Create a lambda_handler and catch any import errors
This is kind of gross, but it was the easiest way I found to persist the info in e into the function definition.
The problem is that the act of importing the bottle app causes startup code to run.
Perhaps we can refactor the bottle app so that the app is created here?
"""

import logging
import traceback

IMPORT_ERROR_FILE = '/tmp/import-error'

try:
    from apig_wsgi import make_lambda_handler
    from app.bottle_app import lambda_startup,app

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    logger = logging.getLogger(__name__)
    lambda_startup()
    lambda_app = make_lambda_handler(app)

# pylint: disable=broad-exception-caught
except Exception as e:
    with open(IMPORT_ERROR_FILE,'w') as f:
        f.write(str(e))
        f.write("\n")
        f.write(''.join(traceback.TracebackException.from_exception(e).format()))
    def lambda_handler(event, context): # pylint: disable=unused-argument
        with open(IMPORT_ERROR_FILE,'r') as f:
            return {
                "statusCode": 200,
                "body": "error:\n" + f.read()
            }
    lambda_app = lambda_handler
