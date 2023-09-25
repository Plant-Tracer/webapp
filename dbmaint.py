"""
Database Management Tool for webapp

"""

import sys
import os
import configparser

import uuid
import pymysql

# pylint: disable=no-member

import db
from paths import TEMPLATE_DIR, SCHEMA_FILE, PLANTTRACER_ENDPOINT
from lib.ctools import clogging
from lib.ctools import dbfile

assert os.path.exists(TEMPLATE_DIR)

MYSQL_HOST = 'MYSQL_HOST'
MYSQL_USER = 'MYSQL_USER'
MYSQL_PASSWORD = 'MYSQL_PASSWORD'
MYSQL_DATABASE = 'MYSQL_DATABASE'
localhost = 'localhost'
dbreader = 'dbreader'
dbwriter = 'dbwriter'

__version__ = '0.0.1'

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Bottle App with Bottle's built-in server unless a command is given",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    required = parser.add_argument_group('required arguments')

    required.add_argument(
        "--rootconfig", help='specify config file with MySQL database root credentials in [client] section. Format is the same as the mysql --defaults-extra-file= argument', required=True)
    parser.add_argument(
        "--sendlink", help="send link to the given email address, registering it if necessary.")
    parser.add_argument("--createdb", help='Create a new database and a dbreader and dbwriter user. Database must not exist. Requires that the variables MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, and MYSQL_USER are all set with a MySQL username that can issue the "CREATE DATABASE"command. Outputs setenv for DBREADER and DBWRITER')
    parser.add_argument("--dropdb",  help='Drop an existing database.')
    parser.add_argument(
        "--writeconfig",  help="specify the config.ini file to write.")

    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if args.sendlink:
        db.send_links(email=args.sendlink, planttracer_endpoint = PLANTTRACER_ENDPOINT)
        sys.exit(0)

    auth = dbfile.DBMySQLAuth.FromConfigFile(args.rootconfig, 'client')
    try:
        d = dbfile.DBMySQL(auth)
    except pymysql.err.OperationalError:
        print("Invalid auth: ", auth, file=sys.stderr)
        raise

    if args.writeconfig:
        cp = configparser.ConfigParser()
        cp.read(args.writeconfig)

    if args.createdb:
        dbreader_user = 'dbreader_' + args.createdb
        dbwriter_user = 'dbwriter_' + args.createdb
        dbreader_password = str(uuid.uuid4())
        dbwriter_password = str(uuid.uuid4())
        d.execute(f'CREATE DATABASE {args.createdb}')
        d.execute(f'USE {args.createdb}')
        with open(SCHEMA_FILE, 'r') as f:
            d.create_schema(f.read())
        d.execute(
            f'CREATE USER `{dbreader_user}`@`localhost` identified by "{dbreader_password}"')
        d.execute(
            f'GRANT SELECT on {args.createdb}.* to `{dbreader_user}`@`localhost`')
        d.execute(
            f'CREATE USER `{dbwriter_user}`@`localhost` identified by "{dbreader_password}"')
        d.execute(
            f'GRANT ALL on {args.createdb}.* to `{dbwriter_user}`@`localhost`')

        def prn(k, v):
            print(f"{k}={v}")
        if sys.stdout.isatty():
            print("Contents for dbauth.ini:")

        print("[dbreader]")
        prn(MYSQL_HOST, localhost)
        prn(MYSQL_USER, dbreader_user)
        prn(MYSQL_PASSWORD, dbreader_password)
        prn(MYSQL_DATABASE, args.createdb)

        print("[dbwriter]")
        prn(MYSQL_HOST, localhost)
        prn(MYSQL_USER, dbreader_user)
        prn(MYSQL_PASSWORD, dbreader_password)
        prn(MYSQL_DATABASE, args.createdb)

        if cp:
            if dbreader not in cp:
                cp.add_section(dbreader)
            cp[dbreader][MYSQL_HOST] = localhost
            cp[dbreader][MYSQL_USER] = dbreader_user
            cp[dbreader][MYSQL_PASSWORD] = dbreader_password
            cp[dbreader][MYSQL_DATABASE] = args.createdb

            if dbwriter not in cp:
                cp.add_section(dbwriter)
            cp[dbwriter][MYSQL_HOST] = localhost
            cp[dbwriter][MYSQL_USER] = dbwriter_user
            cp[dbwriter][MYSQL_PASSWORD] = dbwriter_password
            cp[dbwriter][MYSQL_DATABASE] = args.createdb
            with open(args.writeconfig, 'w') as fp:
                cp.write(fp)

    if args.dropdb:
        dbreader_user = 'dbreader_' + args.dropdb
        dbwriter_user = 'dbwriter_' + args.dropdb
        d.execute(f'DROP USER `{dbreader_user}`@`localhost`')
        d.execute(f'DROP USER `{dbwriter_user}`@`localhost`')
        d.execute(f'DROP DATABASE {args.dropdb}')
