"""
dbutil.py - CLI for dbmaint module.
"""

import sys
import os
import configparser
import uuid

from deploy.app import clogging
from deploy.app import odbmaint
from deploy.app import db
from deploy.app import mailer
from deploy.app import paths
from deploy.app.constants import C
from deploy.app.odb import DDBO


DESCRIPTION="""
DynamoDB Database Maintenance Program.
"""

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=DESCRIPTION,
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    required = parser.add_argument_group('required arguments')
    parser.add_argument("--sendlink", help="Send link to the given email address, registering it if necessary.")
    parser.add_argument('--planttracer_endpoint',help='https:// endpoint where planttracer app can be found')
    parser.add_argument('--table_prefix', help='Prefix for DynamoDB tables', default='')
    parser.add_argument("--createdb", help='Create a new set of DynamoDB tables.')
    parser.add_argument("--dropdb",  help='Drop an existing database.')
    parser.add_argument("--writeconfig",  help="Specify the config.ini file to write.")
    parser.add_argument('--purge_test_data', help='Remove the test data from the database', action='store_true')
    parser.add_argument('--purge_all_movies', help='Remove all of the movies from the database', action='store_true')
    parser.add_argument("--purge_movie",help="Remove the movie and all of its associated data from the database",type=int)
    parser.add_argument("--create_client",help="Create a [client] section with a root username and the specified password")
    parser.add_argument("--create_course",help="Create a course and register --admin_email --admin_name as the administrator")
    parser.add_argument('--demo_email',help='If create_course is specified, also create a demo user with this email and upload demo movies ')
    parser.add_argument("--admin_email",help="Specify the email address of the course administrator")
    parser.add_argument("--admin_name",help="Specify the name of the course administrator")
    parser.add_argument("--max_enrollment",help="Max enrollment for course",type=int,default=50)
    parser.add_argument("--report",help="Print a report of the database",action='store_true')
    parser.add_argument("--freshen",help="Non-destructive cleans up the movie metadata for all movies.",action='store_true')
    parser.add_argument("--clean",help="Destructive cleans up the movie metadata for all movies.",action='store_true')
    parser.add_argument("--schema", help="Specify schema file to use", default=paths.SCHEMA_FILE)
    parser.add_argument("--dump", help="Backup all objects as JSON files and movie files to new directory called DUMP.  ")
    parser.add_argument("--add_admin", help="Add --admin_email user as a course admin to the course specified by --course_id", action='store_true')
    parser.add_argument("--course_id", help="course id")
    parser.add_argument("--remove_admin", help="Remove the --admin_email user as a course admin from the course specified by --course_id", action='store_true')
    parser.add_argument("--debug", help='Enable debug (mostly for SMTP)', action='store_true')

    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    ddbo = DDBO(table_prefix=args.table_prefix)

    config = configparser.ConfigParser()

    if args.sendlink:
        if not args.planttracer_endpoint:
            raise RuntimeError("Please specify --planttracer_endpoint")
        new_api_key = db.make_new_api_key(email=args.sendlink)
        mailer.send_links(email=args.sendlink, planttracer_endpoint = args.planttracer_endpoint,
                      new_api_key=new_api_key, debug=args.debug)
        sys.exit(0)

    ################################################################
    ## Startup stuff

    if args.createdb:
        odbmaint.create_schema(ddbo)

    if args.dropdb:
        odbmaint.drop_tables(ddbo)

    if args.create_course:
        print("creating course...")
        if not args.admin_email:
            print("Must provide --admin_email",file=sys.stderr)
        if not args.admin_name:
            print("Must provide --admin_name",file=sys.stderr)
        if not args.admin_email or not args.admin_name:
            sys.exit(1)
        course_key = str(uuid.uuid4())[9:18]
        odbmaint.create_course(course_key = course_key,
                               course_name = args.create_course,
                               admin_email = args.admin_email,
                               admin_name = args.admin_name,
                               max_enrollment = args.max_enrollment,
                               demo_email = args.demo_email )
        print(f"course_key: {course_key}")
        sys.exit(0)

    if args.add_admin:
        print("adding admin to course...")
        if not args.admin_email:
            print("Must provide --admin_email",file=sys.stderr)
            sys.exit(1)
        user = ddbo.get_user(email=args.admin_email)
        if not user.get('user_id'):
            print(f"User {args.admin_email} does not exist")
            sys.exit(1)
        if not args.course_id:
            print("Must provide --course_id",file=sys.stderr)
            sys.exit(1)
        if args.course_id:
            course = odb.lookup_course_by_id(course_id=args.course_id)
            if course.get('course_id'):
                dbmaint.add_admin_to_course(admin_email = args.admin_email, course_id = args.course_id)
                sys.exit(0)
            else:
                print(f"Course with id {args.course_id} does not exist.",file=sys.stderr)
                sys.exit(1)

    if args.remove_admin:
        print("removing admin from course...")
        if not args.admin_email:
            print("Must provide --admin_email",file=sys.stderr)
            sys.exit(1)
        user = ddbo.get_user(email=args.admin_email)
        if not user.get('id'):
            print(f"User {args.admin_email} does not exist")
            sys.exit(1)
        if not args.course_id:
            print("Must provide --course_id",file=sys.stderr)
            sys.exit(1)
        odbmaint.remove_admin_from_course( admin_email = args.admin_email, course_id = args.course_id)
        sys.exit(0)

    ################################################################
    ## Cleanup

    if args.purge_test_data:
        odbmaint.purge_test_data()

    if args.purge_all_movies:
        odbmaint.purge_all_movies()

    if args.purge_movie:
        odb.purge_movie(movie_id=args.purge_movie)

    ################################################################
    ## Maintenance

    if args.report:
        odbmaint.report(ddbo)
        sys.exit(0)

    if args.freshen:
        odbmaint.freshen(False)
        sys.exit(0)

    if args.clean:
        odbmaint.freshen(True)
        sys.exit(0)

    if args.dump:
        odbmaint.dump(config,args.dump)
        sys.exit()
