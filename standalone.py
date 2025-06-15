"""
CLI for running standalone webserver.
"""

################################################################
# Bottle App
##

import sys
import os
import argparse
import logging

from deploy.app import clogging
from deploy.app import db_object

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Bottle App with Bottle's built-in server unless a command is given",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--storelocal', help='Store new objects locally, not in S3', action='store_true')
    parser.add_argument("--info", help='print info about the runtime environment', action='store_true')
    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if args.info:
        for name in logging.root.manager.loggerDict: # pylint: disable=no-member
            print("Logger: ",name)
        sys.exit(0)

    if args.storelocal:
        db_object.STORE_LOCAL=True

    cmd = f'gunicorn --bind 127.0.0.1:{args.port} --workers 2 --reload --log-level DEBUG deploy.app.bottle_app:app '
    print(cmd)
    os.system(cmd)
