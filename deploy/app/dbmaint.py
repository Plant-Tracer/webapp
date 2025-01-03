#!/usr/bin/env python3
"""
Database Management Tool for webapp
"""

import sys
import os
import configparser
import subprocess
import socket
import logging
import json
import re
import glob

import uuid

from tabulate import tabulate
from botocore.exceptions import ClientError,ParamValidationError

from . import paths
from . import db
from . import tracker
from . import auth
from . import clogging
from . import dbfile
from .constants import C
from .paths import TEMPLATE_DIR, SCHEMA_FILE, TEST_DATA_DIR, SCHEMA_TEMPLATE
from .dbfile import MYSQL_HOST,MYSQL_USER,MYSQL_PASSWORD,MYSQL_DATABASE,DBMySQL

assert os.path.exists(TEMPLATE_DIR)

SCHEMA_VERSION = 'schema_version'
LOCALHOST = 'localhost'
dbreader = 'dbreader'
dbwriter = 'dbwriter'
csfr = DBMySQL.csfr

DEFAULT_MAX_ENROLLMENT = 10
DEMO_NAME  = 'Plant Tracer Demo Account'
DEMO_MOVIE_TITLE = 'Demo Movie #{ct}'
DEMO_MOVIE_DESCRIPTION = 'Track this movie!'

__version__ = '0.0.1'

debug = False

def hostnames():
    hostname = socket.gethostname()
    return socket.gethostbyname_ex(hostname)[2] + [LOCALHOST,hostname]

def purge_test_data():
    """Remove all test data from the database"""
    sizes = {}
    d = dbfile.DBMySQL(auth.get_dbwriter())
    c = d.cursor()
    c.execute('show tables')
    for (table,) in c:
        c2 = d.cursor()
        c2.execute(f'select count(*) from {table}')
        count = c2.fetchone()[0]
        print(f"table {table:20} count: {count:,}")
        sizes[table] = count

    c.execute( "delete from admins where course_id in (select id from courses where course_name like 'test-test-%')")
    for where in ['where name like "fake-name-%"',
                  'where name like "Test%"',
                  'where email like "%admin+test%"',
                  'where email like "%demo+admin%"']:
        del_movies = f"(select id from movies where user_id in (select id from users {where}))"
        for table in ['movie_frame_trackpoints']:
            cmd = f"delete from {table} where movie_id in {del_movies})"
            print(cmd)
            c.execute(cmd)
        for table in ['movie_frames']:
            cmd = f"delete from {table} where movie_id in {del_movies}"
            print(cmd)
            c.execute(cmd)
        c.execute(f"delete from movie_frames where movie_id in {del_movies}")
        c.execute(f"delete from movies where user_id in (select id from users {where})")
        c.execute( f"delete from api_keys where user_id in (select id from users {where})")
        c.execute( f"delete from users {where}")
        c.execute( f"delete from users {where}")
    c.execute( "delete from courses where course_name like 'test-test-%'")
    c.execute( "delete from engines where name like 'engine %'")

def purge_all_movies():
    """Remove all test data from the database"""
    d = dbfile.DBMySQL(auth.get_dbwriter())
    c = d.cursor()
    for table in ['object_store','objects','movie_frame_trackpoints','movie_frames','movies']:
        print("wiping",table)
        c.execute( f"delete from {table}")


# pylint: disable=too-many-statements
def createdb(*,droot, createdb_name, write_config_fname, schema):
    """Create a database named `createdb_name` where droot is a root connection to the database server.
    Creadentials are stored in cp.
    """
    assert isinstance(createdb_name,str)
    print("createdb_name=",createdb_name)

    print(f"createdb droot={droot} createdb_name={createdb_name} write_config_fname={write_config_fname} schema={schema}")
    dbreader_user = 'dbreader_' + createdb_name
    dbwriter_user = 'dbwriter_' + createdb_name
    dbreader_password = str(uuid.uuid4())
    dbwriter_password = str(uuid.uuid4())
    c = droot.cursor()

    c.execute(f'DROP DATABASE IF EXISTS {createdb_name}') # can't do %s because it gets quoted
    c.execute(f'CREATE DATABASE {createdb_name}')
    c.execute(f'USE {createdb_name}')

    print("creating schema.")
    with open(schema, 'r') as f:
        droot.create_schema(f.read())
    print("done")

    # Now grant on all addresses
    if debug:
        print("Current interfaces and hostnames:")
        print("ifconfig -a:")
        subprocess.call(['ifconfig','-a'])
        print("Hostnames:",hostnames())
    for ipaddr in hostnames() + ['%']:
        print("granting dbreader and dbwriter access from ",ipaddr)
        c.execute( f'DROP   USER IF EXISTS `{dbreader_user}`@`{ipaddr}`')
        c.execute( f'CREATE USER           `{dbreader_user}`@`{ipaddr}` identified by "{dbreader_password}"')
        c.execute( f'GRANT SELECT on {createdb_name}.* to `{dbreader_user}`@`{ipaddr}`')

        c.execute( f'DROP   USER IF EXISTS `{dbwriter_user}`@`{ipaddr}`')
        c.execute( f'CREATE USER           `{dbwriter_user}`@`{ipaddr}` identified by "{dbwriter_password}"')
        c.execute( f'GRANT ALL on {createdb_name}.* to `{dbwriter_user}`@`{ipaddr}`')

    if write_config_fname:
        cp = configparser.ConfigParser()
        if dbreader not in cp:
            cp.add_section(dbreader)
        cp[dbreader][MYSQL_HOST] = LOCALHOST
        cp[dbreader][MYSQL_USER] = dbreader_user
        cp[dbreader][MYSQL_PASSWORD] = dbreader_password
        cp[dbreader][MYSQL_DATABASE] = createdb_name

        if dbwriter not in cp:
            cp.add_section(dbwriter)
        cp[dbwriter][MYSQL_HOST] = LOCALHOST
        cp[dbwriter][MYSQL_USER] = dbwriter_user
        cp[dbwriter][MYSQL_PASSWORD] = dbwriter_password
        cp[dbwriter][MYSQL_DATABASE] = createdb_name

        with open(write_config_fname, 'w') as fp:
            print("writing config to ",write_config_fname)
            cp.write(fp)
    else:
        # Didn't write to
        if sys.stdout.isatty():
            print("Contents for dbauth.ini:")

        def prn(k, v):
            print(f"{k}={v}")

        print("[dbreader]")
        prn(MYSQL_HOST, LOCALHOST)
        prn(MYSQL_USER, dbreader_user)
        prn(MYSQL_PASSWORD, dbreader_password)
        prn(MYSQL_DATABASE, createdb_name)

        print("[dbwriter]")
        prn(MYSQL_HOST, LOCALHOST)
        prn(MYSQL_USER, dbwriter_user)
        prn(MYSQL_PASSWORD, dbwriter_password)
        prn(MYSQL_DATABASE, createdb_name)



def report():
    dbreader = auth.get_dbreader()
    print(dbreader)
    headers = []
    rows = csfr(dbreader,
                """SELECT id,course_name,course_section,course_key,max_enrollment,A.ct as enrolled,B.movie_count from courses
                left join (select primary_course_id,count(*) ct from users group by primary_course_id) A on id=A.primary_course_id
                left join (select count(*) movie_count, course_id from movies group by course_id ) B on courses.id=B.course_id
                order by 1,2""",
                get_column_names=headers)
    print(tabulate(rows,headers=headers))
    print("\n")

    headers = []
    rows = csfr(dbreader,
                               """SELECT id,title,created_at,user_id,course_id,published,deleted,
                                         date_uploaded,fps,width,height,total_frames
                                  FROM movies
                                  ORDER BY id
                               """,get_column_names=headers)
    print(tabulate(rows,headers=headers))

    for demo in (0,1):
        print("\nDemo users:" if demo==1 else "\nRegular Users:")
        rows = csfr(dbreader,
                    """SELECT id,name,email,B.ct as movie_count
                    FROM users LEFT JOIN
                    (SELECT user_id,COUNT(*) AS ct FROM movies GROUP BY user_id) B ON id=B.user_id
                    WHERE demo=%s""",
                    (demo,),
                    get_column_names=headers)
        print(tabulate(rows,headers=headers))

def delete_callback(info):
    print("Deleting:",info)

def freshen(clean):
    dbwriter = auth.get_dbwriter()
    action = 'CLEAN' if clean else 'FRESHEN'
    verb   = 'Deleting movies' if clean else 'Displaying movies'
    print(f"{action} ({dbwriter})")
    print(f"{verb} with no data.")
    for movie in csfr(dbwriter, "SELECT * from movies where movie_data_urn is NULL",(),asDicts=True):
        print("Movie with no data:",movie['id'])
        print(json.dumps(movie,default=str,indent=4))
        if clean:
            db.purge_movie(movie_id=movie['id'], callback=delete_callback)

    print(f"{verb} marked for deletion by author.")
    for movie in csfr(dbwriter, "SELECT * from movies where deleted!=0",(),asDicts=True):
        print("Deleted movie:",movie['id'])
        print(json.dumps(movie,default=str,indent=4))
        if clean:
            db.purge_movie(movie_id=movie['id'], callback=delete_callback)

    print(f"{verb} movies that have no bytes uploaded")
    for movie in csfr(dbwriter, "SELECT * from movies where total_bytes is NULL",(),asDicts=True):
        movie_id = movie['id']
        print(json.dumps(movie,default=str,indent=4))
        try:
            movie_data = db.get_movie_data(movie_id=movie_id)
        except (db.InvalidMovie_Id,ClientError,ParamValidationError):
            print("Cannot get movie data.")
            movie_data = None
        if movie_data is None:
            print("Movie data is not available.")
            if clean:
                print("Purging movie")
                db.purge_movie(movie_id=movie_id)
            else:
                print("Rerun with --clean to purge movie")
            continue
        print("Fixing metadata...")
        movie_metadata = tracker.extract_movie_metadata(movie_data=movie_data)
        print("metadata:",json.dumps(movie_metadata,default=str,indent=4))
        cmd = "UPDATE movies SET " + ",".join([ f"{key}=%s" for key in movie_metadata ]) + " WHERE id=%s"
        args = list( movie_metadata.values()) + [movie_id]
        csfr(dbwriter, cmd, args)

#pylint: disable=too-many-arguments
def create_course(*, course_key, course_name, admin_email,
                  admin_name,max_enrollment=DEFAULT_MAX_ENROLLMENT,demo_email = None):
    db.create_course(course_key = course_key,
                     course_name = course_name,
                     max_enrollment = max_enrollment)
    admin_id = db.register_email(email=admin_email, course_key=course_key, name=admin_name)['user_id']
    db.make_course_admin(email=admin_email, course_key=course_key)
    logging.info("generated course_key=%s  admin_email=%s admin_id=%s",course_key,admin_email,admin_id)

    if demo_email:
        user_dir = db.register_email(email=demo_email, course_key = course_key, name=DEMO_NAME, demo_user=1)
        user_id = user_dir['user_id']
        db.make_new_api_key(email=demo_email)
        ct = 1
        for fn in os.listdir(TEST_DATA_DIR):
            ext = os.path.splitext(fn)[1]
            if ext in ['.mp4','.mov']:
                with open(os.path.join(TEST_DATA_DIR, fn), 'rb') as f:
                    movie_data = f.read()
                    movie_id = db.create_new_movie(user_id=user_id,
                                        title=DEMO_MOVIE_TITLE.format(ct=ct),
                                        description=DEMO_MOVIE_DESCRIPTION)
                    db.set_movie_data(movie_id=movie_id, movie_data = movie_data)
                ct += 1
    return admin_id

def add_admin_to_course(*, admin_email, course_id=None, course_key=None):
    db.make_course_admin(email=admin_email, course_key=course_key, course_id=course_id)

def remove_admin_from_course(*, admin_email, course_id=None, course_key=None, course_name=None):
    db.remove_course_admin(
                        email=admin_email,
                        course_key=course_key,
                        course_id=course_id,
                        course_name=course_name
                    )

################################################################
## database schema management
################################################################

"""
etc/schema.sql --- the current schema.
etc/schema_0.sql --- creates the initial schema and includes a statement
                     set the current schema version number. Currently this is version 10.
etc/schema_{n}.sql --- upgrade from schema (n-1) to (n).
"""


def current_source_schema():
    """Returns the current schema of the app based on the highest number schema file.
    Scan all current schema files."""
    glob_template = SCHEMA_TEMPLATE.format(schema='*')
    pat = re.compile("([0-9]+)[.]sql")
    ver = 0
    for p in glob.glob(glob_template):
        m = pat.search(p)
        ver = max( int(m.group(1)), ver)
    return ver

def schema_upgrade( ath ):
    """Upgrade the schema to the current version.
    NOTE: uses ath to create a new database connection. ath must have ability to modify database schema.

    """
    dbname = ath.database
    logging.info("schema_upgrade(%s)",ath)
    with dbfile.DBMySQL( ath ) as dbcon:
        dbcon.execute(f"USE {dbname}")

        max_version = current_source_schema()

        def current_version():
            cursor = dbcon.cursor()
            cursor.execute("SELECT v from metadata where k=%s",(SCHEMA_VERSION,))
            return int(cursor.fetchone()[0])

        cv = current_version()
        logging.debug("current database version: %s  max version: %s", cv , max_version)

        for upgrade in range(cv+1, max_version+1):
            logging.info("Upgrading from version %s to %s",cv, upgrade)
            with open(SCHEMA_TEMPLATE.format(schema=upgrade),'r') as f:
                dbcon.create_schema(f.read())
            cv += 1
            logging.info("Current version now %s",current_version())
            assert cv == current_version()

def dump(config,dumpdir):
    if os.path.exists(dumpdir):
        raise FileExistsError(f"{dumpdir} exists")
    os.mkdir(dumpdir)
    dbreader = dbfile.DBMySQLAuth.FromConfig(config['dbreader'])
    movies = dbfile.DBMySQL.csfr(dbreader,
                                 """select *,movies.id as movie_id from movies
                                 left join users on movies.user_id=users.id order by movies.id """,asDicts=True)
    for movie in movies:
        movie_id = movie['movie_id']
        movie_data = db.get_movie_data(movie_id=movie_id)
        if movie_data is None:
            print("no data:",movie_id)
            continue
        print("saving ",movie_id)
        with open(os.path.join(dumpdir,f"movie_{movie_id}.json"),"w") as f:
            json.dump(movie, f, default=str)
        with open(os.path.join(dumpdir,f"movie_{movie_id}.mp4"),"wb") as f:
            f.write(movie_data)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Database Maintenance Program. The database to act upon is specified in the ini file specified by the PLANTTRACER_CREDENTIALS environment variable, in the sections for [dbreader] and [dbwriter]",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    required = parser.add_argument_group('required arguments')
    required.add_argument(
        "--rootconfig",
        help='Specify config file with MySQL database root credentials in [client] section. '
        'Format is the same as the mysql --defaults-extra-file= argument')
    parser.add_argument("--sendlink", help="Send link to the given email address, registering it if necessary.")
    parser.add_argument('--planttracer_endpoint',help='https:// endpoint where planttracer app can be found')
    parser.add_argument("--createdb",
                        help='Create a new database and a dbreader and dbwriter user. Database must not exist. '
                        'Requires that the variables MYSQL_DATABASE and MYSQL_HOST are set, and that MYSQL_PASSWORD and MYSQL_USER '
                        'are set with a MySQL username that can issue the "CREATE DATABASE" command.'
                        'Outputs setenv for DBREADER and DBWRITER')
    parser.add_argument("--upgradedb", help='Upgrade a database schema',action='store_true')
    parser.add_argument("--dropdb",  help='Drop an existing database.')
    parser.add_argument("--readconfig",   help="Specify the config.ini file to read")
    parser.add_argument("--writeconfig",  help="Specify the config.ini file to write.")
    parser.add_argument('--purge_test_data', help='Remove the test data from the database', action='store_true')
    parser.add_argument('--purge_all_movies', help='Remove all of the movies from the database', action='store_true')
    parser.add_argument("--purge_movie",help="Remove the movie and all of its associated data from the database",type=int)
    parser.add_argument("--create_client",help="Create a [client] section with a root username and the specified password")
    parser.add_argument("--create_course",help="Create a course and register --admin_email --admin_name as the administrator")
    parser.add_argument('--demo_email',help='If create_course is specified, also create a demo user with this email and upload demo movies ')
    parser.add_argument("--admin_email",help="Specify the email address of the course administrator")
    parser.add_argument("--admin_name",help="Specify the name of the course administrator")
    parser.add_argument("--max_enrollment",help="Max enrollment for course",type=int,default=20)
    parser.add_argument("--report",help="Print a report of the database",action='store_true')
    parser.add_argument("--freshen",help="Non-destructive cleans up the movie metadata for all movies.",action='store_true')
    parser.add_argument("--clean",help="Destructive cleans up the movie metadata for all movies.",action='store_true')
    parser.add_argument("--schema", help="Specify schema file to use", default=SCHEMA_FILE)
    parser.add_argument("--dump", help="Backup all objects as JSON files and movie files to new directory called DUMP.  ")
    parser.add_argument("--add_admin", help="Add --admin_email user as a course admin to the course specified by --course_id, --course_name, or --course_name", action='store_true')
    parser.add_argument("--course_id", help="integer course id", type=int)
    parser.add_argument("--course_key", help="integer course id")
    parser.add_argument("--course_name", help="integer course id")
    parser.add_argument("--remove_admin", help="Remove the --admin_email user as a course admin from the course specified by --course_id, --course_name, or --course_name", action='store_true')

    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    config = configparser.ConfigParser()

    if args.rootconfig:
        config.read(args.rootconfig)
        os.environ[C.PLANTTRACER_CREDENTIALS] = args.rootconfig

    if args.readconfig:
        paths.CREDENTIALS_FILE = paths.AWS_CREDENTIALS_FILE = args.readconfig

    if args.sendlink:
        if not args.planttracer_endpoint:
            raise RuntimeError("Please specify --planttracer_endpoint")
        new_api_key = db.make_new_api_key(email=args.sendlink)
        db.send_links(email=args.sendlink, planttracer_endpoint = args.planttracer_endpoint,
                      new_api_key=new_api_key)
        sys.exit(0)

    ################################################################
    ## Startup stuff

    if args.createdb or args.dropdb:
        cp = configparser.ConfigParser()
        if args.rootconfig is None:
            print("Please specify --rootconfig for --createdb or --dropdb",file=sys.stderr)
            sys.exit(1)

        ath   = dbfile.DBMySQLAuth.FromConfigFile(args.rootconfig, 'client')
        with dbfile.DBMySQL( ath ) as droot:
            if args.createdb:
                createdb(droot=droot, createdb_name = args.createdb,
                         write_config_fname=args.writeconfig, schema=args.schema)
                sys.exit(0)

            if args.dropdb:
                # Delete the database and the users created for the database
                dbreader_user = 'dbreader_' + args.dropdb
                dbwriter_user = 'dbwriter_' + args.dropdb
                c = droot.cursor()
                for ipaddr in hostnames():
                    c.execute(f'DROP USER IF EXISTS `{dbreader_user}`@`{ipaddr}`')
                    c.execute(f'DROP USER IF EXISTS `{dbwriter_user}`@`{ipaddr}`')
                c.execute(f'DROP DATABASE IF EXISTS {args.dropdb}')
        sys.exit(0)

    # These all use existing databases
    cp = configparser.ConfigParser()
    if args.create_client:
        print(f"creating root with password '{args.create_client}'")
        if 'client' not in cp:
            cp.add_section('client')
        cp['client']['user']='root'
        cp['client']['password']=args.create_client
        cp['client']['host'] = 'localhost'
        cp['client']['database'] = 'sys'

    if args.readconfig:
        cp.read(args.readconfig)
        print("config read from",args.readconfig)
        if cp['dbreader']['mysql_database'] != cp['dbwriter']['mysql_database']:
            raise RuntimeError("dbreader and dbwriter do not address the same database")

    if args.writeconfig:
        with open(args.writeconfig, 'w') as fp:
            cp.write(fp)
        print(args.writeconfig,"is written")

    if args.create_course:
        print("creating course...")
        if not args.admin_email:
            print("Must provide --admin_email",file=sys.stderr)
        if not args.admin_name:
            print("Must provide --admin_name",file=sys.stderr)
        if not args.admin_email or not args.admin_name:
            sys.exit(1)
        course_key = str(uuid.uuid4())[9:18]
        create_course(course_key = course_key,
                      course_name = args.create_course,
                      admin_email = args.admin_email,
                      admin_name = args.admin_name,
                      max_enrollment = args.max_enrollment,
                      demo_email = args.demo_email
                      )
        print(f"course_key: {course_key}")
        sys.exit(0)

    if args.upgradedb:
        # the upgrade can be done with dbwriter, as long as dbwriter can update the schema.
        # In our current versions, it can.
        ath   = dbfile.DBMySQLAuth.FromConfigFile(os.environ[C.PLANTTRACER_CREDENTIALS], 'dbwriter')
        schema_upgrade(ath)
        sys.exit(0)

    if args.add_admin:
        print("adding admin to course...")
        if not args.admin_email:
            print("Must provide --admin_email",file=sys.stderr)
            sys.exit(1)
        user = db.lookup_user(email=args.admin_email)
        if not user.get('id'):
            print(f"User {args.admin_email} does not exist")
            sys.exit(1)
        if not args.course_key and not args.course_id and not args.course_name:
            print("Must provide one of --course_key, --course_id, or --course_name",file=sys.stderr)
            sys.exit(1)
        if args.course_id:
            course = db.lookup_course_by_id(course_id=args.course_id)
            if course.get('id'):
                add_admin_to_course(admin_email = args.admin_email, course_id = args.course_id)
                sys.exit(0)
            else:
                print(f"Course with id {args.course_id} does not exist.",file=sys.stderr)
                sys.exit(1)
        elif args.course_key:
            course = db.lookup_course_by_key(course_key=args.course_key)
            if course.get('course_key'):
                add_admin_to_course(admin_email = args.admin_email, course_key = course['course_key'])
                sys.exit(0)
            else:
                print(f"Course with key {args.course_key} does not exist.",file=sys.stderr)
                sys.exit(1)
        elif args.course_name:
            course = db.lookup_course_by_name(course_name = args.course_name)
            if course.get('id'):
                add_admin_to_course(admin_email=args.admin_email, course_id=course['id'])
                sys.exit(0)
            else:
                print(f'Course with name {args.course_name} does not exist.',file=sys.stderr)
                sys.exit(1)

    if args.remove_admin:
        print("removing admin from course...")
        if not args.admin_email:
            print("Must provide --admin_email",file=sys.stderr)
            sys.exit(1)
        user = db.lookup_user(email=args.admin_email)
        if not user.get('id'):
            print(f"User {args.admin_email} does not exist")
            sys.exit(1)
        if not args.course_key and not args.course_id and not args.course_name:
            print("Must provide one of --course_key, --course_id, or --course_name",file=sys.stderr)
            sys.exit(1)
        remove_admin_from_course(
            admin_email = args.admin_email,
            course_id = args.course_id,
            course_key = args.course_key,
            course_name = args.course_name
        )
        sys.exit(0)

    ################################################################
    ## Cleanup

    if args.purge_test_data:
        purge_test_data()

    if args.purge_all_movies:
        purge_all_movies()

    if args.purge_movie:
        db.purge_movie(movie_id=args.purge_movie)

    ################################################################
    ## Maintenance

    if args.report:
        report()
        sys.exit(0)

    if args.freshen:
        freshen(False)
        sys.exit(0)

    if args.clean:
        freshen(True)
        sys.exit(0)

    if args.dump:
        dump(config,args.dump)
        sys.exit()
