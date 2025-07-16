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
from deploy.app.constants import C
from deploy.app import db_object

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Bottle App with Bottle's built-in server unless a command is given",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--port', type=int, help='bind to port on 127.0.01 interface', default=8080)
    parser.add_argument('--bind', help='bind to gunicorn endpoint', action='extend', nargs='*', type=str)
    parser.add_argument('--storelocal', help='Store new objects locally, not in S3', action='store_true')
    parser.add_argument("--info", help='print info about the runtime environment', action='store_true')
    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if C.PLANTTRACER_CREDENTIALS not in os.environ:
        print(f"Please define {C.PLANTTRACER_CREDENTIALS} and restart",file=sys.stderr)
        sys.exit(1)

    if args.info:
        for name in logging.root.manager.loggerDict: # pylint: disable=no-member
            print("Logger: ",name)
        sys.exit(0)

    if args.storelocal:
        db_object.STORE_LOCAL=True

    bind_args = ''
    if args.bind:
        if len(args.bind) > 0:
            for b in args.bind:
                bind_args += ' --bind ' + b

    # Now make sure that the credentials work
    # We only do this with the standalone program
    # the try/except is for when we run under a fixture in the pytest unit tests, which messes up ROOT_DIR
    try:
        from tests.dbreader_test import test_db_connection
        test_db_connection()
    except ModuleNotFoundError:
        pass

    cmd = f'gunicorn --bind 127.0.0.1:{args.port} {bind_args} --workers 2 --reload --log-level DEBUG deploy.app.bottle_app:app '
    print(cmd)
    os.system(cmd)
