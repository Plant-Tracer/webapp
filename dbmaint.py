"""
Database Management Tool for webapp

"""

import sys
import os
import configparser
import subprocess
import socket
import logging

import uuid
import pymysql
from tabulate import tabulate

# pylint: disable=no-member

import mailer
import db
from auth import get_dbreader,get_dbwriter
from paths import TEMPLATE_DIR, SCHEMA_FILE
from lib.ctools import clogging
from lib.ctools import dbfile
from pronounceable import generate_word

assert os.path.exists(TEMPLATE_DIR)

MYSQL_HOST = 'MYSQL_HOST'
MYSQL_USER = 'MYSQL_USER'
MYSQL_PASSWORD = 'MYSQL_PASSWORD'
MYSQL_DATABASE = 'MYSQL_DATABASE'
LOCALHOST = 'localhost'
dbreader = 'dbreader'
dbwriter = 'dbwriter'

DEFAULT_MAX_ENROLLMENT = 10
DEMO_EMAIL = 'demo@planttracer.com'
DEMO_NAME  = 'Plant Tracer Demo Account'

__version__ = '0.0.1'

def hostnames():
    hostname = socket.gethostname()
    return socket.gethostbyname_ex(hostname)[2] + [LOCALHOST,hostname]

def clean():
    sizes = {}
    d = dbfile.DBMySQL(get_dbwriter())
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
    c.execute( "delete from movies where user_id in (select id from users where name like 'Test%')")
    c.execute( "delete from admins where course_id in (select id from courses where course_name like '%course name%')")
    c.execute( "delete from api_keys where user_id in (select id from users where name like 'Test%')")
    c.execute( "delete from users where name like 'Test%'")
    c.execute( "delete from courses where course_name like '%course name%'")
    c.execute( "delete from engines where name like 'engine %'")

def create_db(args, cp):
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
    print("Current interfaces and hostnames:")
    print("ifconfig -a:")
    subprocess.call(['ifconfig','-a'])
    print("Hostnames:",hostnames())
    for ipaddr in hostnames() + ['%']:
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
            print("writing config to ",args.writeconfig)
            cp.write(fp)

def report():
    dbreader = get_dbreader()
    headers = []
    rows = dbfile.DBMySQL.csfr(dbreader,
                               """SELECT id,course_name,course_section,course_key,max_enrollment,A.ct as enrolled,B.movie_count from courses
                               right join (select primary_course_id,count(*) ct from users group by primary_course_id) A on id=A.primary_course_id
                               right join (select count(*) movie_count, course_id from movies group by course_id ) B on courses.id=B.course_id
                               order by 1,2""",
                               get_column_names=headers)
    print(tabulate(rows,headers=headers))
    print("\n")

    headers = []
    rows = dbfile.DBMySQL.csfr(dbreader,
                               """SELECT * from movies order by id""",get_column_names=headers)
    print(tabulate(rows,headers=headers))


def create_course(*, course_key, course_name, admin_email,
                  admin_name,max_enrollment=DEFAULT_MAX_ENROLLMENT,
                  create_demo = False):
    db.create_course(course_key = course_key,
                     course_name = course_name,
                     max_enrollment = max_enrollment)
    admin_id = db.register_email(email=admin_email, course_key=course_key, name=admin_name)['user_id']
    db.make_course_admin(email=admin_email, course_key=course_key)
    logging.info("generated course_key=%s  admin_email=%s admin_id=%s",course_key,admin_email,admin_id)

    if create_demo:
        db.register_email(email=DEMO_EMAIL, course_key = course_key, name=DEMO_NAME, demo_user=1)
        db.make_new_api_key(email=DEMO_EMAIL)
    return admin_id

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Bottle App with Bottle's built-in server unless a command is given",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    required = parser.add_argument_group('required arguments')

    required.add_argument(
        "--rootconfig",
        help='specify config file with MySQL database root credentials in [client] section. '
        'Format is the same as the mysql --defaults-extra-file= argument')
    parser.add_argument("--sendlink", help="send link to the given email address, registering it if necessary.")
    parser.add_argument("--mailer_config", help="print mailer configuration",action='store_true')
    parser.add_argument('--planttracer_endpoint',help='https:// endpoint where planttracer app can be found')
    parser.add_argument("--createdb", help='Create a new database and a dbreader and dbwriter user. Database must not exist. '
                        'Requires that the variables MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, and MYSQL_USER '
                        'are all set with a MySQL username that can issue the "CREATE DATABASE" command. '
                        'Outputs setenv for DBREADER and DBWRITER')
    parser.add_argument("--dropdb",  help='Drop an existing database.')
    parser.add_argument("--writeconfig",  help="specify the config.ini file to write.")
    parser.add_argument('--clean', help='Remove the test data from the database', action='store_true')
    parser.add_argument("--create_root",help="create a [client] section with a root username and the specified password")
    parser.add_argument("--create_course",help="Create a course and register --admin as the administrator")
    parser.add_argument('--create_demo',help='If create_course is specified, also create a demo user',action='store_true')
    parser.add_argument("--admin_email",help="Specify the email address of the course administrator")
    parser.add_argument("--admin_name",help="Specify the name of the course administrator")
    parser.add_argument("--max_enrollment",help="Max enrollment for course",type=int,default=20)
    parser.add_argument("--report",help="print a report of the database",action='store_true')
    parser.add_argument("--purge_movie",help="remove the movie and all of its associated data from the database",type=int)
    parser.add_argument("--purge_all_movies",help="remove the movie and all of its associated data from the database",type=int)

    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if args.mailer_config:
        print("mailer config:",mailer.smtp_config_from_environ())
        exit(0)

    if args.sendlink:
        if not args.planttracer_endpoint:
            raise RuntimeError("Please specify --planttracer_endpoint")
        db.send_links(email=args.sendlink, planttracer_endpoint = args.planttracer_endpoint)
        sys.exit(0)

    cp = configparser.ConfigParser()
    if args.writeconfig:
        cp.read(args.writeconfig)

    if args.create_root:
        if 'client' not in cp:
            cp.add_section('client')
        cp['client']['user']='root'
        cp['client']['password']=args.create_root
        cp['client']['host'] = 'localhost'
        cp['client']['database'] = 'sys'
        with open(args.writeconfig, 'w') as fp:
            cp.write(fp)
        print(args.writeconfig,"is written with a root configuration")
        sys.exit(0)

    if args.clean:
        clean()

    if args.create_course:
        if not args.admin_email:
            print("Must provide --admin_email",file=sys.stderr)
        if not args.admin_name:
            print("Must provide --admin_name",file=sys.stderr)
        if not args.admin_email or not args.admin_name:
            exit(1)
        course_key = "-".join([generate_word(),generate_word(),generate_word()])
        create_course(course_key = course_key,
                      course_name = args.create_course,
                      admin_email = args.admin_email,
                      admin_name = args.admin_name,
                      max_enrollment = args.max_enrollment,
                      create_demo = args.create_demo
                      )
        print(f"course_key: {course_key}")
        exit(0)

    if args.report:
        report()
        exit(0)

    if args.purge_movie:
        db.purge_movie(movie_id=args.purge_movie)
        exit(0)

    # The following all require a root config
    if args.rootconfig is None:
        print("Please specify --rootconfig for --createdb or --dropdb",file=sys.stderr)
        exit(1)
    if not os.path.exists(args.rootconfig):
        print("File not found: ",args.rootconfig,file=sys.stderr)
        exit(1)
    auth = dbfile.DBMySQLAuth.FromConfigFile(args.rootconfig, 'client')
    try:
        d = dbfile.DBMySQL(auth)
    except pymysql.err.OperationalError:
        print("Invalid auth: ", auth, file=sys.stderr)
        raise

    if args.createdb:
        create_db(args, cp)

    if args.dropdb:
        dbreader_user = 'dbreader_' + args.dropdb
        dbwriter_user = 'dbwriter_' + args.dropdb
        for ipaddr in hostnames():
            d.execute(f'DROP USER `{dbreader_user}`@`{ipaddr}`')
            d.execute(f'DROP USER `{dbwriter_user}`@`{ipaddr}`')
        d.execute(f'DROP DATABASE {args.dropdb}')
