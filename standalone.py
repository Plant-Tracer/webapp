#!/usr/bin/env python3.11

################################################################
# Bottle App
##

import sys
import os
import uvicorn
import argparse

import deploy.clogging as clogging
from deploy.constants import C

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Bottle App with Bottle's built-in server unless a command is given",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--storelocal', help='Store new objects locally, not in S3', action='store_true')
    parser.add_argument("--info", help='print info about the runtime environment', action='store_true')
    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if C.PLANTTRACER_CREDENTIALS not in os.environ:
        print(f"Please define {C.PLANTTRACER_CREDENTIALS} and restart",file=sys.stderr)
        sys.exit(1)

    if args.info:
        for name in logging.root.manager.loggerDict:
            print("Logger: ",name)
        sys.exit(0)

    if args.storelocal:
        db_object.STORE_LOCAL=True

    # Now make sure that the credentials work
    # We only do this with the standalone program
    # the try/except is for when we run under a fixture in the pytest unit tests, which messes up ROOT_DIR
    try:
        from tests.dbreader_test import test_db_connection
        test_db_connection()
    except ModuleNotFoundError:
        pass

    cmd = f'gunicorn --bind 127.0.0.1:{args.port} --workers 2 --reload --log-level DEBUG deploy.bottle_app:app '
    print(cmd)
    exit(0)
    os.system(cmd)