"""
Movie tool

"""

import sys
import os
import configparser

import uuid
import pymysql

# pylint: disable=no-member

import db
from paths import TEMPLATE_DIR, SCHEMA_FILE
from lib.ctools import clogging
from lib.ctools import dbfile

__version__ = '0.0.1'

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Work with movies in the database",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    required = parser.add_argument_group('required arguments')

    required.add_argument(
        "--rootconfig", help='specify config file with MySQL database root credentials in [client] section. Format is the same as the mysql --defaults-extra-file= argument', required=True)
    parser.add_argument( "--list",  help="List all the movies", action='store_true')
    parser.add_argument( "--extract",  help="extract all of the frames for the given movie",type=int)

    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    auth = dbfile.DBMySQLAuth.FromConfigFile(args.rootconfig, 'client')
    try:
        d = dbfile.DBMySQL(auth)
    except pymysql.err.OperationalError:
        print("Invalid auth: ", auth, file=sys.stderr)
        raise
