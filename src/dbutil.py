"""
dbutil.py - CLI for dbmaint module.
"""

import sys
import configparser
import uuid
import json
import os

from app import clogging
from app import odb
from app import odbmaint
from app import mailer
from app.paths import TEST_DATA_DIR
from app.odb import DDBO, InvalidCourse_Id, USER_ID
from app.odb_movie_data import set_movie_data
from app.constants import C

DEMO_COURSE_ID='demo-course'
DEMO_COURSE_NAME='Demo Course'
DEMO_MOVIE_TITLE = 'Demo Movie {ct}'
DEMO_MOVIE_DESCRIPTION = 'A demo movie'
DEMO_USER_EMAIL = 'demo@planttracer.com'
DEMO_USER_NAME = 'Demo User'
DEFAULT_ADMIN_EMAIL = 'admin@planttracer.com'
DEFAULT_ADMIN_NAME = 'Plant Tracer Admin'

DESCRIPTION="""
Plant Tracer DynamoDB Database Maintenance Program.
"""

def populate_demo_user():
    odbmaint.create_course(course_id  = DEMO_COURSE_ID,
                           course_name = DEMO_COURSE_NAME,
                           course_key = str(uuid.uuid4())[0:8],
                           admin_email = DEFAULT_ADMIN_EMAIL,
                           admin_name  = DEFAULT_ADMIN_NAME,
                           max_enrollment = 2,
                           ok_if_exists = True)

    # Create the demo user to own the demo movies
    odb.register_email(DEMO_USER_EMAIL, DEMO_USER_NAME, course_id=DEMO_COURSE_ID)
    odb.make_new_api_key(email=DEMO_USER_EMAIL, demo_user=True)        # Give the demo user an API key

def populate_demo_movies():
    def is_movie_fn(fn):
        return os.path.splitext(fn)[1] in ['.mp4','.mov']

    if not os.path.isdir(TEST_DATA_DIR):
        return  # e.g. on EC2 when tests/data or demo movies are not present

    # Add the demo movies
    demo_user = odb.get_user_email(DEMO_USER_EMAIL)
    for (ct,fn) in enumerate([fn for fn in os.listdir(TEST_DATA_DIR) if (is_movie_fn(fn) and 'rotated' not in fn)],1):
        with open(os.path.join(TEST_DATA_DIR, fn), 'rb') as f:
            movie_id = odb.create_new_movie(user_id=demo_user[USER_ID],
                                            course_id = DEMO_COURSE_ID,
                                            title=DEMO_MOVIE_TITLE.format(ct=ct),
                                            description=DEMO_MOVIE_DESCRIPTION)
            set_movie_data(movie_id=movie_id, movie_data = f.read())



def dump_movie(movie_id):
    print(f"Movie {movie_id}" )
    ddbo = DDBO()
    movie = ddbo.get_movie(movie_id)
    print(json.dumps(movie,indent=4,default=str))
    trackpoints = odb.get_movie_trackpoints(movie_id=movie_id)
    print(json.dumps(trackpoints,indent=4,default=str))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=DESCRIPTION,
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    required = parser.add_argument_group('required arguments')
    parser.add_argument("--sendlink", help="Send link to the given email address, registering it if necessary.")
    parser.add_argument("--makelink", help="Make a link for the given email, registering it if necessary.")
    parser.add_argument('--planttracer_endpoint',help='https:// endpoint where planttracer app can be found')
    parser.add_argument("--create_demos", help="Create the demo user and movies", action='store_true')
    parser.add_argument("--createdb", help='Create a new set of DynamoDB tables and install the demo user and movies.',action='store_true')
    parser.add_argument("--dropdb",  help='Drop an existing database.',action='store_true')
    parser.add_argument("--create_course",help="Create a course with --course_name, --course_id, "
                        "and optional --max_enrollment, and register --admin_email --admin_name as the administrator",action='store_true')
    parser.add_argument("--send-email",help="With --create_course: after ensuring course exists, send verification email to admin with magic link",action='store_true')
    parser.add_argument("--delete_course",help="Delete the course specified by --course_id", action='store_true')
    parser.add_argument("--admin_email",help="Specify the email address of the course administrator")
    parser.add_argument("--admin_name",help="Specify the name of the course administrator")
    parser.add_argument("--max_enrollment",help="Max enrollment for course",type=int,default=50)
    parser.add_argument("--report",help="Print a report of the database",action='store_true')
    parser.add_argument("--add_admin", help="Add --admin_email user as a course admin to the course specified by --course_id", action='store_true')
    parser.add_argument("--remove_admin", help="Remove the --admin_email user as a course admin from the course specified by --course_id", action='store_true')
    parser.add_argument("--course_id", help="course id")
    parser.add_argument("--course_key", help="course key")
    parser.add_argument("--course_name", help="course name")
    parser.add_argument("--debug", help='Enable debug (mostly for SMTP)', action='store_true')
    parser.add_argument('--purge_all_movies', help='Remove all of the movies from the database and S3. Requires --course_id', action='store_true')
    parser.add_argument("--dump_movie", help="provides information about a movie")

    # These need to be re-implemented
    # parser.add_argument("--purge_movie",help="Remove the movie and all of its associated data from the database",type=int)
    # parser.add_argument("--freshen",help="Non-destructive cleans up the movie metadata for all movies.",action='store_true')
    # parser.add_argument("--clean",help="Destructive cleans up the movie metadata for all movies.",action='store_true')
    # parser.add_argument("--dump", help="Dump all objects as JSON files and movie files to new directory called DUMP.")

    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    config = configparser.ConfigParser()

    if C.DYNAMODB_TABLE_PREFIX not in os.environ:
        print(f"ERROR: Environment variable {C.DYNAMODB_TABLE_PREFIX} is not set",file=sys.stderr)
        sys.exit(1)

    if args.sendlink or args.makelink:
        if not args.planttracer_endpoint:
            parser.error("Please specify --planttracer_endpoint")
        if args.sendlink:
            mailer.send_links(email=args.sendlink,
                              planttracer_endpoint = args.planttracer_endpoint,
                              new_api_key=odb.make_new_api_key(email=args.sendlink),
                              debug=args.debug)
        if args.makelink:
            new_api_key = odb.make_new_api_key(email=args.makelink)
            delim = '' if args.planttracer_endpoint.endswith('/') else '/'
            print(f"\n*****\n***** Login with {args.planttracer_endpoint}{delim}list?api_key={new_api_key}\n*****")
        sys.exit(0)


    ################################################################
    ## Startup stuff

    if args.createdb:
        odbmaint.create_tables()

    if args.createdb or args.create_demos:
        populate_demo_user()
        populate_demo_movies()

    if args.dropdb:
        odbmaint.drop_tables()

    if args.create_course:
        missing = [name for name in ['course_id','course_name','admin_email','admin_name'] if getattr(args, name) is None]
        if missing:
            parser.error(f"--create_course requires --course_name, --course_id, --admin_email and --admin_name. Missing: {','.join('--' + m for m in missing)}")
        course_id = args.course_id
        try:
            odb.lookup_course_by_id(course_id=course_id)
            print(f"course {course_id} already exists")
        except InvalidCourse_Id:
            print("creating course...")
            course_key = str(uuid.uuid4())[9:18]
            odbmaint.create_course(course_id=course_id,
                                   course_key=course_key,
                                   course_name=args.course_name,
                                   admin_email=args.admin_email,
                                   admin_name=args.admin_name,
                                   max_enrollment=args.max_enrollment,
                                   ok_if_exists=False)
            print(f"created {course_id}")
        print(json.dumps(odb.lookup_course_by_id(course_id=course_id), indent=4, default=str))

        if args.send_email:
            for var in ('HOSTNAME', 'DOMAIN'):
                if not os.environ.get(var):
                    parser.error(f"--send-email requires {var} in environment (e.g. from /etc/environment.d/10-planttracer.conf)")
            planttracer_endpoint = f"https://{os.environ['HOSTNAME']}.{os.environ['DOMAIN']}"
            course = odb.lookup_course_by_id(course_id=course_id)
            admin = odb.get_user_email(args.admin_email)
            api_key = odb.get_first_api_key_for_user(admin[USER_ID])
            if api_key is None:
                api_key = odb.make_new_api_key(email=args.admin_email)
            mailer.send_course_created_email(
                to_addr=args.admin_email,
                course_name=course.get('course_name', course_id),
                course_id=course_id,
                planttracer_endpoint=planttracer_endpoint,
                api_key=api_key,
            )
            print(f"verification email sent to {args.admin_email}")

    if args.delete_course:
        if not args.course_id:
            parser.error("--delete_course requires --course_id")
        odbmaint.delete_course(course_id=args.course_id)
        sys.exit(0)

    if args.add_admin:
        print("adding admin to course...")
        if not args.admin_email:
            parser.error("Must provide --admin_email")
        user = DDBO().get_user_email(args.admin_email)
        if not user.get('user_id'):
            parser.error(f"User {args.admin_email} does not exist")
        if not args.course_id:
            parser.error("Must provide --course_id")
        if args.course_id:
            try:
                course = odb.lookup_course_by_id(course_id=args.course_id)
                admin_id = odb.get_user_email(args.admin_email)[ USER_ID ]
                odb.add_course_admin(admin_id = admin_id, course_id = args.course_id)
                sys.exit(0)
            except InvalidCourse_Id:
                print(f"Course with id {args.course_id} does not exist.",file=sys.stderr)
                sys.exit(1)

    if args.remove_admin:
        if not args.admin_email:
            parser.error("Must provide --admin_email")
        if not args.course_id:
            parser.error("Must provide --course_id")
        admin_id = odb.get_user_email(args.admin_email)['user_id']
        odb.remove_course_admin( admin_id = admin_id, course_id = args.course_id)
        sys.exit(0)

    if args.dump_movie:
        dump_movie(args.dump_movie)

    ################################################################
    ## Cleanup

    if args.purge_all_movies:
        if not args.course_id:
            parser.error("Must provide --course_id")
        odbmaint.purge_all_movies(DDBO())

    ################################################################
    ## Maintenance

    if args.report:
        odbmaint.report(DDBO())
        sys.exit(0)
