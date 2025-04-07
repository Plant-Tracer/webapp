import sys
import os
import configparser

from deploy.app import clogging
from deploy.app import dbmaint
from deploy.app import db
from deploy.app import dbfile
from deploy.app import paths


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
    parser.add_argument("--schema", help="Specify schema file to use", default=paths.SCHEMA_FILE)
    parser.add_argument("--dump", help="Backup all objects as JSON files and movie files to new directory called DUMP.  ")
    parser.add_argument("--add_admin", help="Add --admin_email user as a course admin to the course specified by --course_id, --course_name, or --course_name", action='store_true')
    parser.add_argument("--course_id", help="integer course id", type=int)
    parser.add_argument("--course_key", help="integer course id")
    parser.add_argument("--course_name", help="integer course id")
    parser.add_argument("--remove_admin", help="Remove the --admin_email user as a course admin from the course specified by --course_id, --course_name, or --course_name", action='store_true')
    parser.add_argument("--debug", help='Enable debug (mostly for SMTP)', action='store_true')

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
                      new_api_key=new_api_key, debug=args.debug)
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
        dbmaint.create_course(course_key = course_key,
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
        dbmaint.schema_upgrade(ath)
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
                dbmaint.add_admin_to_course(admin_email = args.admin_email, course_id = args.course_id)
                sys.exit(0)
            else:
                print(f"Course with id {args.course_id} does not exist.",file=sys.stderr)
                sys.exit(1)
        elif args.course_key:
            course = db.lookup_course_by_key(course_key=args.course_key)
            if course.get('course_key'):
                dbmaint.add_admin_to_course(admin_email = args.admin_email, course_key = course['course_key'])
                sys.exit(0)
            else:
                print(f"Course with key {args.course_key} does not exist.",file=sys.stderr)
                sys.exit(1)
        elif args.course_name:
            course = db.lookup_course_by_name(course_name = args.course_name)
            if course.get('id'):
                dbmaint.add_admin_to_course(admin_email=args.admin_email, course_id=course['id'])
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
        dbmaint.remove_admin_from_course(
            admin_email = args.admin_email,
            course_id = args.course_id,
            course_key = args.course_key,
            course_name = args.course_name
        )
        sys.exit(0)

    ################################################################
    ## Cleanup

    if args.purge_test_data:
        dbmaint.purge_test_data()

    if args.purge_all_movies:
        dbmaint.purge_all_movies()

    if args.purge_movie:
        db.purge_movie(movie_id=args.purge_movie)

    ################################################################
    ## Maintenance

    if args.report:
        dbmaint.report()
        sys.exit(0)

    if args.freshen:
        dbmaint.freshen(False)
        sys.exit(0)

    if args.clean:
        dbmaint.freshen(True)
        sys.exit(0)

    if args.dump:
        dbmaint.dump(config,args.dump)
        sys.exit()
