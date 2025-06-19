"""
CLI for running standalone webserver.
"""

################################################################
# Flask App
##

import sys
import os
import argparse
import logging

from gunicorn.app.wsgiapp import run


from deploy.app import clogging
from deploy.app import db_object

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--info", help='print info about the runtime environment', action='store_true')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--workers', type=int, default=2)
    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if args.info:
        for name in logging.root.manager.loggerDict: # pylint: disable=no-member
            print("Logger: ",name)
        sys.exit(0)

    sys.argv = [
        "gunicorn",
        "--bind", f"127.0.0.1:{args.port}",
        "--workers", str(args.workers),
        "--reload",                 # autoreload on code change
        "--preload",
        "--log-level", args.loglevel,
        "--access-logfile", "-",
        "--error-logfile", "-",
        "deploy.app.bottle_app:app"
    ]
    print(" ".join(sys.argv))
    run()

if __name__ == "__main__":
    main()
