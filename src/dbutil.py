"""
dbutil.py - CLI for dbmaint module.
"""

import sys
import uuid
import json
import os
from email.message import EmailMessage

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
from app.constants import C
from tabulate import tabulate

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
    odb.register_email(DEMO_USER_EMAIL, DEMO_USER_NAME, course_id=DEMO_COURSE_ID)
    odb.make_new_api_key(email=DEMO_USER_EMAIL, demo_user=True)        # Give the demo user an API key


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


def env_value(name):
    return os.environ[name].strip().strip(chr(34) + chr(39))


def planttracer_endpoint():
    missing = [name for name in ("HOSTNAME", "DOMAIN") if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing environment variable(s): " + ", ".join(missing))
    return "https://{}.{}".format(env_value("HOSTNAME"), env_value("DOMAIN"))


def print_report():
    ddbo = DDBO()
    odbmaint.report(ddbo)
    print_course_report(ddbo)


def register_student(args):
    user = odb.register_email(
        args.student_email,
        args.student_name,
        course_key=args.course_key,
    )
    api_key = odb.make_new_api_key_for_user_id(user_id=user[USER_ID])
    endpoint = planttracer_endpoint()
    mailer.send_links(
        email=args.student_email,
        planttracer_endpoint=endpoint,
        new_api_key=api_key,
        debug=args.debug,
    )
    delim = "" if endpoint.endswith("/") else "/"
    print(f"registered {args.student_email} for course key {args.course_key}")
    print(f"login link: {endpoint}{delim}list?api_key={api_key}")


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
    import argparse
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    clogging.add_argument(parser, loglevel_default="WARNING")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("report", help="Print database tables, courses, and students")

    register = subparsers.add_parser("register", help="Register a student and send a login link")
    register.add_argument("--course_key", required=True, help="Course registration key")
    register.add_argument("--student_name", required=True, help="Student name")
    register.add_argument("--student_email", required=True, help="Student email address")
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
