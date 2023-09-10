"""
Database Management Tool for webapp

"""

import sys
import os
import io
import datetime
import logging

import uuid
import pymysql

# pylint: disable=no-member

import db
from paths import view,STATIC_DIR,TEMPLATE_DIR,PLANTTRACER_ENDPOINT,SCHEMA_FILE
from lib.ctools import clogging
from lib.ctools import dbfile

assert os.path.exists(TEMPLATE_DIR)



__version__='0.0.1'

if __name__=="__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Bottle App with Bottle's built-in server unless a command is given",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--sendlink",help="send link to the given email address, registering it if necessary.")
    parser.add_argument("--createdb",help='Create a new database and a dbreader and dbwriter user. Database must not exist. Requires that the variables MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, and MYSQL_USER are all set with a MySQL username that can issue the "CREATE DATABASE"command. Outputs setenv for DBREADER and DBWRITER')
    parser.add_argument("--dropdb", help='Drop an existing database.')

    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if args.sendlink:
        db.send_links( args.sendlink )
        sys.exit(0)

    auth = dbfile.DBMySQLAuth.FromEnv()
    try:
        d = dbfile.DBMySQL( auth)
    except pymysql.err.OperationalError:
        print("Invalid auth: ",auth,file=sys.stderr)
        raise


    if args.createdb:
        dbreader_user = 'dbreader_' + args.createdb
        dbwriter_user = 'dbwriter_' + args.createdb
        dbreader_password = str(uuid.uuid4())
        dbwriter_password = str(uuid.uuid4())
        assert( args.createdb.isalnum())
        d.execute(f'CREATE DATABASE {args.createdb}')
        d.execute(f'USE {args.createdb}')
        with open(SCHEMA_FILE,'r') as f:
            d.create_schema( f.read())
        d.execute(f'CREATE USER `{dbreader_user}`@`localhost` identified by "{dbreader_password}"')
        d.execute(f'GRANT SELECT on {args.createdb}.* to `{dbreader_user}`@`localhost`')
        d.execute(f'CREATE USER `{dbwriter_user}`@`localhost` identified by "{dbreader_password}"')
        d.execute(f'GRANT ALL on {args.createdb}.* to `{dbwriter_user}`@`localhost`')

        def prn(k,v):
            print(f"{k}={v}")
        if sys.stdout.isatty():
            print("Contents for dbauth.ini:")
        print("[dbreader]")
        prn("MYSQL_HOST",'localhost')
        prn("MYSQL_USER",dbreader_user)
        prn("MYSQL_PASSWORD",dbreader_password)
        prn("MYSQL_DATABASE",args.createdb)
        print("[dbwriter]")
        prn("MYSQL_HOST",'localhost')
        prn("MYSQL_USER",dbreader_user)
        prn("MYSQL_PASSWORD",dbreader_password)
        prn("MYSQL_DATABASE",args.createdb)


    if args.dropdb:
        assert( args.dropdb.isalnum())
        dbreader_user = 'dbreader_' + args.dropdb
        dbwriter_user = 'dbwriter_' + args.dropdb
        d.execute(f'DROP USER `{dbreader_user}`@`localhost`')
        d.execute(f'DROP USER `{dbwriter_user}`@`localhost`')
        d.execute(f'DROP DATABASE {args.dropdb}')
