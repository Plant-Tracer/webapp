"""
dbutil.py - CLI for dbmaint module.
"""

import argparse
import sys
import uuid
import json
import os
import csv
from email.message import EmailMessage

from tabulate import tabulate

from app import clogging
from app import odb
from app import odbmaint
from app import apikey
from app import mailer
from app.paths import TEST_DATA_DIR
from app.odb import (
    COURSE_ID, COURSE_KEY, COURSE_NAME, EMAIL, USER_ID, USER_NAME,
    DDBO, InvalidCourse_Id,
)
from app.odb_movie_data import set_movie_data
from app.constants import C, env_value

DEMO_COURSE_ID='demo-course'
DEMO_COURSE_NAME='Demo Course'
DEMO_MOVIE_TITLE = 'Demo Movie {ct}'
DEMO_MOVIE_DESCRIPTION = 'A demo movie'
DEMO_USER_EMAIL = 'demouser@planttracer.com'
DEMO_USER_NAME = 'Demo User'
DEFAULT_ADMIN_EMAIL = 'admin@planttracer.com'
DEFAULT_ADMIN_NAME = 'Plant Tracer Admin'

DESCRIPTION="""
Plant Tracer DynamoDB Database Maintenance Program.
"""

def populate_demo_user():
    # Use env admin when set (e.g. on EC2 bootstrap) so the demo course reuses the existing admin.
    admin_email = os.environ.get('ADMIN_EMAIL') or DEFAULT_ADMIN_EMAIL
    admin_name = os.environ.get('ADMIN_NAME') or DEFAULT_ADMIN_NAME
    odbmaint.create_course(course_id  = DEMO_COURSE_ID,
                           course_name = DEMO_COURSE_NAME,
                           course_key = str(uuid.uuid4())[0:8],
                           admin_email = admin_email,
                           admin_name  = admin_name,
                           max_enrollment = 2,
                           ok_if_exists = True)

    # Create the demo user to own the demo movies
    user = odb.register_email(DEMO_USER_EMAIL, DEMO_USER_NAME, course_id=DEMO_COURSE_ID)
    odb.make_new_api_key_for_user_id(user_id=user[USER_ID], demo_user=True)


def populate_demo_movies():
    # TODO - Just use the tracker to track!
    def is_movie_fn(fn):
        return os.path.splitext(fn)[1] in ['.mp4','.mov']

    if not os.path.isdir(TEST_DATA_DIR):
        return  # e.g. on EC2 when tests/data or demo movies are not present

    # Add the demo movies
    demo_user = odb.get_user_email(DEMO_USER_EMAIL)
    demo_user_id = demo_user[USER_ID]
    for (ct, fn) in enumerate([fn for fn in os.listdir(TEST_DATA_DIR) if (is_movie_fn(fn) and 'rotated' not in fn)], 1):
        with open(os.path.join(TEST_DATA_DIR, fn), 'rb') as f:
            movie_id = odb.create_new_movie(user_id=demo_user_id,
                                            course_id=DEMO_COURSE_ID,
                                            title=DEMO_MOVIE_TITLE.format(ct=ct),
                                            description=DEMO_MOVIE_DESCRIPTION)
            set_movie_data(movie_id=movie_id, movie_data=f.read())
        # If a trackpoints JSON exists next to the movie (e.g. foo.mov -> foo_trackpoints.json), apply it.
        base, _ = os.path.splitext(fn)
        _trackpoints_path = os.path.join(TEST_DATA_DIR, base + '_trackpoints.json')
        # Juse the API



def dump_movie(movie_id):
    print(f"Movie {movie_id}" )
    ddbo = DDBO()
    movie = ddbo.get_movie(movie_id)
    print(json.dumps(movie,indent=4,default=str))
    trackpoints = odb.get_movie_trackpoints(movie_id=movie_id)
    print(json.dumps(trackpoints,indent=4,default=str))


def scan_all(table):
    items = []
    scan_kwargs = {}
    while True:
        response = table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))
        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            return items
        scan_kwargs["ExclusiveStartKey"] = last_evaluated_key


def print_course_report(ddbo):
    courses = sorted(scan_all(ddbo.courses), key=lambda c: c.get(COURSE_NAME, ""))
    users_by_id = {user[USER_ID]: user for user in scan_all(ddbo.users)}

    course_rows = []
    course_students = []
    for course in courses:
        course_id = course[COURSE_ID]
        movie_count = len(ddbo.get_movies_for_course_id(course_id))
        student_ids = odb.course_enrollments(course_id)
        students = [users_by_id.get(user_id, {USER_ID: user_id}) for user_id in student_ids]
        students.sort(key=lambda user: (user.get(USER_NAME, ""), user.get(EMAIL, ""), user.get(USER_ID, "")))
        course_students.append((course, students))
        course_rows.append([
            course.get(COURSE_NAME, ""),
            course.get(COURSE_KEY, ""),
            course_id,
            movie_count,
            len(students),
        ])

    print("\nCourses")
    print(tabulate(
        course_rows,
        headers=["course name", "course key", "course ID", "movies", "students"],
    ))

    for course, students in course_students:
        print(f"\nStudents for {course.get(COURSE_NAME, course[COURSE_ID])} ({course[COURSE_ID]})")
        student_rows = [
            [
                student.get(USER_NAME, ""),
                student.get(EMAIL, ""),
                student.get(USER_ID, ""),
            ]
            for student in students
        ]
        print(tabulate(student_rows, headers=["student name", "email", "user ID"]))


def planttracer_endpoint():
    missing = [name for name in ("HOSTNAME", "DOMAIN") if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing environment variable(s): " + ", ".join(missing))
    return f"https://{env_value('HOSTNAME')}.{env_value('DOMAIN')}"


def endpoint_from_args(args):
    if getattr(args, "planttracer_endpoint", None):
        return args.planttracer_endpoint
    return planttracer_endpoint()


def print_report():
    ddbo = DDBO()
    odbmaint.report(ddbo)
    print_course_report(ddbo)


def create_db():
    odbmaint.create_tables()
    populate_demo_user()
    populate_demo_movies()


def drop_db():
    odbmaint.drop_tables()


def create_demo():
    odbmaint.create_tables(ignore_table_exists=True)
    populate_demo_user()
    populate_demo_movies()


def make_link(email, planttracer_endpoint):
    new_api_key = odb.make_new_api_key(email=email)
    delim = "" if planttracer_endpoint.endswith("/") else "/"
    print(f"\n*****\n***** Login with {planttracer_endpoint}{delim}list?api_key={new_api_key}\n*****")
    return new_api_key


def send_link(email, planttracer_endpoint, *, debug=False):
    mailer.send_links(
        email=email,
        planttracer_endpoint=planttracer_endpoint,
        new_api_key=odb.make_new_api_key(email=email),
        debug=debug,
    )


def create_course(args, parser):
    missing = [
        name
        for name in ["course_id", "course_name", "admin_email", "admin_name"]
        if getattr(args, name) is None
    ]
    if missing:
        parser.error(
            "create-course requires --course_name, --course_id, --admin_email and "
            f"--admin_name. Missing: {','.join('--' + m for m in missing)}"
        )
    try:
        odb.lookup_course_by_id(course_id=args.course_id)
        print(f"course {args.course_id} already exists")
    except InvalidCourse_Id:
        print("creating course...")
        course_key = str(uuid.uuid4())[9:18]
        odbmaint.create_course(
            course_id=args.course_id,
            course_key=course_key,
            course_name=args.course_name,
            admin_email=args.admin_email,
            admin_name=args.admin_name,
            max_enrollment=args.max_enrollment,
            ok_if_exists=False,
        )
        print(f"created {args.course_id}")
    course = odb.lookup_course_by_id(course_id=args.course_id)
    print(json.dumps(course, indent=4, default=str))

    if args.send_email:
        admin = odb.get_user_email(args.admin_email)
        api_key = odb.get_first_api_key_for_user(admin[USER_ID])
        if api_key is None:
            api_key = odb.make_new_api_key(email=args.admin_email)
        mailer.send_course_created_email(
            to_addr=args.admin_email,
            course_name=course.get(COURSE_NAME, args.course_id),
            course_id=args.course_id,
            planttracer_endpoint=endpoint_from_args(args),
            api_key=api_key,
        )
        print(f"verification email sent to {args.admin_email}")


def delete_course(args, parser):
    if not args.course_id:
        parser.error("delete-course requires --course_id")
    odbmaint.delete_course(course_id=args.course_id)


def add_admin(args, parser):
    if not args.admin_email:
        parser.error("add-admin requires --admin_email")
    if not args.course_id:
        parser.error("add-admin requires --course_id")
    print("adding admin to course...")
    try:
        user = DDBO().get_user_email(args.admin_email)
        if not user.get(USER_ID):
            parser.error(f"User {args.admin_email} does not exist")
        odb.lookup_course_by_id(course_id=args.course_id)
        admin_id = odb.get_user_email(args.admin_email)[USER_ID]
        odb.add_course_admin(admin_id=admin_id, course_id=args.course_id)
    except InvalidCourse_Id:
        print(f"Course with id {args.course_id} does not exist.", file=sys.stderr)
        return 1
    return 0


def remove_admin(args, parser):
    if not args.admin_email:
        parser.error("remove-admin requires --admin_email")
    if not args.course_id:
        parser.error("remove-admin requires --course_id")
    admin_id = odb.get_user_email(args.admin_email)[USER_ID]
    odb.remove_course_admin(admin_id=admin_id, course_id=args.course_id)


def purge_all_movies(args, parser):
    if not args.course_id:
        parser.error("purge-all-movies requires --course_id")
    odbmaint.purge_all_movies(DDBO())


def register_one_student(*, course_key, student_name, student_email, planttracer_endpoint, debug=False):
    user = odb.register_email(
        student_email,
        student_name,
        course_key=course_key,
    )
    api_key = odb.make_new_api_key_for_user_id(user_id=user[USER_ID])
    endpoint = planttracer_endpoint
    mailer.send_links(
        email=student_email,
        planttracer_endpoint=endpoint,
        new_api_key=api_key,
        debug=debug,
    )
    delim = "" if endpoint.endswith("/") else "/"
    print(f"registered {student_email} for course key {course_key}")
    print(f"login link: {endpoint}{delim}list?api_key={api_key}")


def csv_has_header(row):
    if len(row) < 2:
        return False
    return row[0].strip().lower() == "name" and row[1].strip().lower() == "email"


def register_csv(args):
    count = 0
    endpoint = endpoint_from_args(args)
    with open(args.csv_file, newline="", encoding="utf-8") as f:
        rows = csv.reader(f)
        for row_number, row in enumerate(rows, 1):
            if row_number == 1 and csv_has_header(row):
                continue
            if not row or not any(field.strip() for field in row):
                continue
            if len(row) != 2:
                raise ValueError(f"{args.csv_file}:{row_number}: expected name,email")
            student_name, student_email = (field.strip() for field in row)
            register_one_student(
                course_key=args.course_key,
                student_name=student_name,
                student_email=student_email,
                planttracer_endpoint=endpoint,
                debug=args.debug,
            )
            count += 1
    print(f"total students registered: {count}")


def register_student(args):
    if args.csv_file:
        register_csv(args)
        return
    if not args.student_name or not args.student_email:
        raise ValueError("register requires --student_name and --student_email, or --csv")
    register_one_student(
        course_key=args.course_key,
        student_name=args.student_name,
        student_email=args.student_email,
        planttracer_endpoint=endpoint_from_args(args),
        debug=args.debug,
    )
    print("total students registered: 1")


def send_test_mail(email, *, debug=False):
    from_addr = mailer.get_server_email()
    branch = apikey.git_branch().strip()
    commit = apikey.git_last_commit().strip()
    msg = EmailMessage()
    msg["Subject"] = "Plant Tracer test email"
    msg["From"] = from_addr
    msg["To"] = email
    msg.set_content(
        "This is a Plant Tracer test email.\n"
        f"Git branch: {branch}\n"
        f"Git commit: {commit}\n"
    )
    mailer.send_message(
        from_addr=from_addr,
        to_addrs=[email],
        msg=msg.as_string(),
        smtp_config=mailer.get_smtp_config(),
        debug=debug,
    )
    print(f"test email sent to {email} from {from_addr}")


def build_parser():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    clogging.add_argument(parser, loglevel_default="WARNING")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("report", help="Print database tables, courses, and students")
    subparsers.add_parser("createdb", help="Create tables and populate the demo course")
    subparsers.add_parser("dropdb", help="Drop all configured DynamoDB tables")
    subparsers.add_parser(
        "create-demo",
        aliases=["create_demos"],
        help="Create local tables if needed and populate the demo course",
    )

    makelink = subparsers.add_parser("makelink", help="Make a login link for an existing email address")
    makelink.add_argument("email", help="Email address")
    makelink.add_argument("--planttracer_endpoint", required=True, help="Plant Tracer https:// endpoint")

    sendlink = subparsers.add_parser("sendlink", help="Send a login link to an existing email address")
    sendlink.add_argument("email", help="Email address")
    sendlink.add_argument("--planttracer_endpoint", required=True, help="Plant Tracer https:// endpoint")
    sendlink.add_argument("--debug", help="Enable debug output for email sending", action="store_true")

    create_course_parser = subparsers.add_parser(
        "create-course",
        aliases=["create_course"],
        help="Create a course and register its first administrator",
    )
    create_course_parser.add_argument("--course_id", help="course id")
    create_course_parser.add_argument("--course_name", help="course name")
    create_course_parser.add_argument("--admin_email", help="course administrator email")
    create_course_parser.add_argument("--admin_name", help="course administrator name")
    create_course_parser.add_argument("--max_enrollment", help="Max enrollment for course", type=int, default=50)
    create_course_parser.add_argument(
        "--send-email",
        help="Send verification email to admin with magic link after ensuring course exists",
        action="store_true",
    )
    create_course_parser.add_argument(
        "--planttracer_endpoint",
        help="Plant Tracer https:// endpoint for --send-email; defaults to HOSTNAME.DOMAIN",
    )

    delete_course_parser = subparsers.add_parser(
        "delete-course",
        aliases=["delete_course"],
        help="Delete a course",
    )
    delete_course_parser.add_argument("--course_id", help="course id")

    add_admin_parser = subparsers.add_parser(
        "add-admin",
        aliases=["add_admin"],
        help="Add an existing user as a course administrator",
    )
    add_admin_parser.add_argument("--admin_email", help="course administrator email")
    add_admin_parser.add_argument("--course_id", help="course id")

    remove_admin_parser = subparsers.add_parser(
        "remove-admin",
        aliases=["remove_admin"],
        help="Remove a course administrator",
    )
    remove_admin_parser.add_argument("--admin_email", help="course administrator email")
    remove_admin_parser.add_argument("--course_id", help="course id")

    dump_movie_parser = subparsers.add_parser(
        "dump-movie",
        aliases=["dump_movie"],
        help="Dump movie metadata and trackpoints as JSON",
    )
    dump_movie_parser.add_argument("movie_id", help="movie id")

    purge_movies_parser = subparsers.add_parser(
        "purge-all-movies",
        aliases=["purge_all_movies"],
        help="Remove all movie rows from the database. Requires --course_id.",
    )
    purge_movies_parser.add_argument("--course_id", help="course id")

    register = subparsers.add_parser("register", help="Register a student and send a login link")
    register.add_argument("--course_key", required=True, help="Course registration key")
    register.add_argument("--student_name", help="Student name")
    register.add_argument("--student_email", help="Student email address")
    register.add_argument("--csv", dest="csv_file", help="CSV file with name,email rows")
    register.add_argument("--planttracer_endpoint", help="Plant Tracer https:// endpoint; defaults to HOSTNAME.DOMAIN")
    register.add_argument("--debug", help="Enable debug output for email sending", action="store_true")

    test_mail = subparsers.add_parser("test-mail", help="Send a simple test email")
    test_mail.add_argument("email", help="Destination email address")
    test_mail.add_argument("--debug", action="store_true", help="Print SES parameters and raw MIME message")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if C.DYNAMODB_TABLE_PREFIX not in os.environ:
        print(f"ERROR: Environment variable {C.DYNAMODB_TABLE_PREFIX} is not set", file=sys.stderr)
        return 1

    if args.command == "report":
        print_report()
        return 0
    if args.command == "createdb":
        create_db()
        return 0
    if args.command == "dropdb":
        drop_db()
        return 0
    if args.command in ("create-demo", "create_demos"):
        create_demo()
        return 0
    if args.command == "makelink":
        make_link(args.email, args.planttracer_endpoint)
        return 0
    if args.command == "sendlink":
        send_link(args.email, args.planttracer_endpoint, debug=args.debug)
        return 0
    if args.command in ("create-course", "create_course"):
        create_course(args, parser)
        return 0
    if args.command in ("delete-course", "delete_course"):
        delete_course(args, parser)
        return 0
    if args.command in ("add-admin", "add_admin"):
        return add_admin(args, parser)
    if args.command in ("remove-admin", "remove_admin"):
        remove_admin(args, parser)
        return 0
    if args.command in ("dump-movie", "dump_movie"):
        dump_movie(args.movie_id)
        return 0
    if args.command in ("purge-all-movies", "purge_all_movies"):
        purge_all_movies(args, parser)
        return 0
    if args.command == "register":
        register_student(args)
        return 0
    if args.command == "test-mail":
        send_test_mail(args.email, debug=args.debug)
        return 0
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
