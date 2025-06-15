#!/usr/bin/env python3
"""
Database Management Support
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

from . import db
from . import tracker
from . import auth
from . import dbfile
from .paths import TEMPLATE_DIR, TEST_DATA_DIR, SCHEMA_TEMPLATE
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
    """Dump all objects as JSON files and movie files to new directory called DUMP."""
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

def sqlbackup(config,fname,all_databases=False):
    """Backup to an sqlfile"""
    if os.path.exists(fname):
        raise FileExistsError(f"{fname} exists")
    dbreader = dbfile.DBMySQLAuth.FromConfig(config['dbreader'])
    cmd = ['mysqldump','-h' + dbreader.host,'-u' + dbreader.user, '-p' + dbreader.password, '--single-transaction', '--no-tablespaces']
    if all_databases:
        cmd.append('--all-databases')
    else:
        cmd.append(dbreader.database)
    if fname.startswith('s3://'):
        print("Dumping to ",fname)
        with subprocess.Popen(['aws','s3','cp','-',fname], stdin=subprocess.PIPE) as p_s3:
            subprocess.run(cmd, stdout=p_s3.stdin)
        print("done")
        return
    with open(fname,'w') as outfile:
        subprocess.call(cmd, stdout=outfile)
