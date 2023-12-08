"""
Database Management Tool for webapp

"""

import sys
import os
import configparser

import uuid
import pymysql
import socket

# pylint: disable=no-member

import db
from paths import TEMPLATE_DIR, SCHEMA_FILE
from lib.ctools import clogging
from lib.ctools import dbfile

assert os.path.exists(TEMPLATE_DIR)

MYSQL_HOST = 'MYSQL_HOST'
MYSQL_USER = 'MYSQL_USER'
MYSQL_PASSWORD = 'MYSQL_PASSWORD'
MYSQL_DATABASE = 'MYSQL_DATABASE'
LOCALHOST = 'localhost'
dbreader = 'dbreader'
dbwriter = 'dbwriter'

__version__ = '0.0.1'

def hostnames():
        hostname = socket.gethostname()
        return socket.gethostbyname_ex(hostname)[2] + [LOCALHOST,hostname]

def clean(dbwriter):
    sizes = {}
    d = dbfile.DBMySQL(auth)
    c = d.cursor()
    c.execute('show tables')
    for (table,) in c:
        c2 = d.cursor()
        c2.execute(f'select count(*) from {table}')
        count = c2.fetchone()[0]
        print(f"table {table:20} count: {count:,}")
        sizes[table] = count
    del_movies = "(select id from movies where user_id in (select id from users where name like 'Test%'))"
    for table in ['movie_frame_analysis','movie_frame_trackpoints']:
        cmd = f"delete from {table} where frame_id in (select id from movie_frames where movie_id in {del_movies})"
        print(cmd)
        c.execute(cmd)
    for table in ['movie_analysis','movie_data','movie_frames']:
        cmd = f"delete from {table} where movie_id in {del_movies}"
        print(cmd)
        c.execute(cmd)
    c.execute(f"delete from movie_frames where movie_id in {del_movies}")
    c.execute(f"delete from movies where user_id in (select id from users where name like 'Test%')")
    c.execute(f"delete from admins where course_id in (select id from courses where course_name like '%course name%')")
    c.execute(f"delete from api_keys where user_id in (select id from users where name like 'Test%')")
    c.execute(f"delete from users where name like 'Test%'")
    c.execute(f"delete from courses where course_name like '%course name%'")
    c.execute(f"delete from engines where name like 'engine %'")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Bottle App with Bottle's built-in server unless a command is given",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    required = parser.add_argument_group('required arguments')

    required.add_argument(
        "--rootconfig", help='specify config file with MySQL database root credentials in [client] section. Format is the same as the mysql --defaults-extra-file= argument', required=True)
    parser.add_argument(
        "--sendlink", help="send link to the given email address, registering it if necessary.")
    parser.add_argument('--planttracer_endpoint',help='https:// endpoint where planttracer app can be found')
    parser.add_argument("--createdb", help='Create a new database and a dbreader and dbwriter user. Database must not exist. Requires that the variables MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, and MYSQL_USER are all set with a MySQL username that can issue the "CREATE DATABASE"command. Outputs setenv for DBREADER and DBWRITER')
    parser.add_argument("--dropdb",  help='Drop an existing database.')
    parser.add_argument(
        "--writeconfig",  help="specify the config.ini file to write.")
    parser.add_argument('--clean', help='Remove the test data from the database', action='store_true')

    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if args.sendlink:
        if not args.planttracer_endpoint:
            raise RuntimeError("Please specify --planttracer_endpoint")
        db.send_links(email=args.sendlink, planttracer_endpoint = args.planttracer_endpoint)
        sys.exit(0)

    assert os.path.exists(args.rootconfig)
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
        d.execute(f'DROP DATABASE IF EXISTS {args.createdb}')
        d.execute(f'CREATE DATABASE {args.createdb}')
        d.execute(f'USE {args.createdb}')
        with open(SCHEMA_FILE, 'r') as f:
            d.create_schema(f.read())

        # Now grant on all addresses
        for ipaddr in hostnames():
            print("granting dbreader and dbwriter access from ",ipaddr)
            d.execute( f'DROP   USER IF EXISTS `{dbreader_user}`@`{ipaddr}`')
            d.execute( f'CREATE USER           `{dbreader_user}`@`{ipaddr}` identified by "{dbreader_password}"')
            d.execute( f'GRANT SELECT on {args.createdb}.* to `{dbreader_user}`@`{ipaddr}`')

            d.execute( f'DROP   USER IF EXISTS `{dbwriter_user}`@`{ipaddr}`')
            d.execute( f'CREATE USER           `{dbwriter_user}`@`{ipaddr}` identified by "{dbwriter_password}"')
            d.execute( f'GRANT ALL on {args.createdb}.* to `{dbwriter_user}`@`{ipaddr}`')

        def prn(k, v):
            print(f"{k}={v}")
        if sys.stdout.isatty():
            print("Contents for dbauth.ini:")

        print("[dbreader]")
        prn(MYSQL_HOST, LOCALHOST)
        prn(MYSQL_USER, dbreader_user)
        prn(MYSQL_PASSWORD, dbreader_password)
        prn(MYSQL_DATABASE, args.createdb)

        print("[dbwriter]")
        prn(MYSQL_HOST, LOCALHOST)
        prn(MYSQL_USER, dbwriter_user)
        prn(MYSQL_PASSWORD, dbwriter_password)
        prn(MYSQL_DATABASE, args.createdb)

        if cp:
            if dbreader not in cp:
                cp.add_section(dbreader)
            cp[dbreader][MYSQL_HOST] = LOCALHOST
            cp[dbreader][MYSQL_USER] = dbreader_user
            cp[dbreader][MYSQL_PASSWORD] = dbreader_password
            cp[dbreader][MYSQL_DATABASE] = args.createdb

            if dbwriter not in cp:
                cp.add_section(dbwriter)
            cp[dbwriter][MYSQL_HOST] = LOCALHOST
            cp[dbwriter][MYSQL_USER] = dbwriter_user
            cp[dbwriter][MYSQL_PASSWORD] = dbwriter_password
            cp[dbwriter][MYSQL_DATABASE] = args.createdb
            with open(args.writeconfig, 'w') as fp:
                cp.write(fp)

    if args.dropdb:
        dbreader_user = 'dbreader_' + args.dropdb
        dbwriter_user = 'dbwriter_' + args.dropdb
        for ipaddr in hostnames():
            d.execute(f'DROP USER `{dbreader_user}`@`{ipaddr}`')
            d.execute(f'DROP USER `{dbwriter_user}`@`{ipaddr}`')
        d.execute(f'DROP DATABASE {args.dropdb}')

    if args.clean:
        clean(dbwriter)
