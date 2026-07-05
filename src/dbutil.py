"""
dbutil.py - CLI for dbmaint module.
"""

import argparse
import sys
import json
import os
import csv
from email.message import EmailMessage

from tabulate import tabulate

from app import clogging
from app import odb
from app import odbmaint
from app import apikey
from app import course_management
from app import mailer
from app.paths import TEST_DATA_DIR
from app.odb import (
    COURSE_ID, COURSE_KEY, COURSE_NAME, EMAIL, USER_ID, USER_NAME,
    DDBO, InvalidCourse_Id, MOVIE_STATUS, MOVIE_STATE_READY, TITLE,
)
from app.odb_movie_data import set_movie_data
from app.constants import C, env_value

DEMO_COURSE_ID='demo-course'
DEMO_COURSE_NAME='Demo Course'
DEMO_MOVIE_TITLE = 'Demo Movie {ct}'
DEMO_MOVIE_DESCRIPTION = 'A demo movie'
DEMO_USER_EMAIL = 'demouser@planttracer.com'
DEMO_USER_NAME = 'Demo User'
DEFAULT_ADMIN_EMAIL = 'plantadmin@planttracer.com'
DEFAULT_ADMIN_NAME = 'Plant Tracer Demo Admin'

NO_COURSES_MESSAGE = "No courses are available for this administrator."
CREATE_COURSE_REQUIRED_FLAGS = ["--course_id", "--course_name", "--admin_email", "--admin_name"]

DESCRIPTION="""
Plant Tracer DynamoDB Database Maintenance Program.
"""

def populate_demo_user():
    # Use env admin when set (e.g. on EC2 bootstrap) so the demo course reuses the existing admin.
    admin_email = os.environ.get('ADMIN_EMAIL') or DEFAULT_ADMIN_EMAIL
    admin_name = os.environ.get('ADMIN_NAME') or DEFAULT_ADMIN_NAME
    return course_management.ensure_demo_course(
        course_id=DEMO_COURSE_ID,
        course_name=DEMO_COURSE_NAME,
        admin_email=admin_email,
        admin_name=admin_name,
        demo_user_email=DEMO_USER_EMAIL,
        demo_user_name=DEMO_USER_NAME,
        max_enrollment=2,
    )


def populate_demo_movies():
    # TODO - Just use the tracer to trace.
    def is_movie_fn(fn):
        return os.path.splitext(fn)[1] in ['.mp4','.mov']

    if not os.path.isdir(TEST_DATA_DIR):
        return 0, 0  # e.g. on EC2 when tests/data or demo movies are not present

    # Add the demo movies
    demo_user = odb.get_user_email(DEMO_USER_EMAIL)
    demo_user_id = demo_user[USER_ID]
    ddbo = DDBO()
    existing_titles = {
        movie.get(TITLE)
        for movie in ddbo.get_movies_for_course_id(DEMO_COURSE_ID)
    }
    seeded = 0
    skipped = 0
    demo_movie_files = sorted(
        fn for fn in os.listdir(TEST_DATA_DIR)
        if is_movie_fn(fn) and 'rotated' not in fn
    )
    for (ct, fn) in enumerate(demo_movie_files, 1):
        title = DEMO_MOVIE_TITLE.format(ct=ct)
        if title in existing_titles:
            skipped += 1
            continue
        with open(os.path.join(TEST_DATA_DIR, fn), 'rb') as f:
            movie_id = odb.create_new_movie(user_id=demo_user_id,
                                            course_id=DEMO_COURSE_ID,
                                            title=title,
                                            description=DEMO_MOVIE_DESCRIPTION)
            set_movie_data(movie_id=movie_id, movie_data=f.read())
            ddbo.update_table(ddbo.movies, movie_id, {MOVIE_STATUS: MOVIE_STATE_READY})
            existing_titles.add(title)
            seeded += 1
        # If a trackpoints JSON exists next to the movie (e.g. foo.mov -> foo_trackpoints.json), apply it.
        base, _ = os.path.splitext(fn)
        _trackpoints_path = os.path.join(TEST_DATA_DIR, base + '_trackpoints.json')
        # Juse the API
    return seeded, skipped



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


def format_admin_course(course):
    """Return an operator-readable course label."""
    if course.course_name:
        return f"{course.course_name} ({course.course_id})"
    return course.course_id


def admin_list():
    """Print all course administrators and their administered courses."""
    admins = odb.list_admins()
    if not admins:
        print("No course administrators found.")
        return
    rows = [
        [
            admin.user_name,
            admin.email,
            admin.user_id,
            "\n".join(format_admin_course(course) for course in admin.courses),
        ]
        for admin in admins
    ]
    print(tabulate(rows, headers=["name", "email", "user ID", "admin courses"]))


def course_sort_key(course):
    return (str(course.get(COURSE_NAME) or "").casefold(), str(course.get(COURSE_ID) or "").casefold())


def courses_available_for_admin(admin_user=None):
    """Return courses where admin_user is not already a course administrator."""
    admin_id = admin_user.get(USER_ID) if admin_user else None
    courses = sorted(scan_all(DDBO().courses), key=course_sort_key)
    if admin_id is None:
        return courses
    return [
        course
        for course in courses
        if admin_id not in course.get(odb.ADMINS_FOR_COURSE, [])
    ]


def course_label(course):
    return f"{course.get(COURSE_NAME, '')} ({course[COURSE_ID]})"


def course_model_label(course):
    return f"{course.course_name} ({course.course_id})"


def parse_course_selection(selection, available_courses):
    """Parse comma-separated course ids or 1-based row numbers."""
    by_id = {course[COURSE_ID]: course for course in available_courses}
    selected = []
    seen_course_ids = set()
    for raw_token in selection.split(","):
        token = raw_token.strip()
        if not token:
            continue
        if token.isdigit():
            index = int(token) - 1
            if index < 0 or index >= len(available_courses):
                raise ValueError(f"course selection {token} is out of range")
            course = available_courses[index]
        else:
            course = by_id.get(token)
            if course is None:
                raise ValueError(f"unknown course_id {token}")
        course_id = course[COURSE_ID]
        if course_id not in seen_course_ids:
            selected.append(course)
            seen_course_ids.add(course_id)
    if not selected:
        raise ValueError("no courses selected")
    return selected


def prompt_admin_create(args):
    """Fill missing admin-create arguments from an interactive terminal."""
    if args.admin_email is None:
        args.admin_email = input("Course administrator email: ").strip()
    if args.admin_name is None:
        args.admin_name = input("Course administrator name: ").strip()

    try:
        admin_user = DDBO().get_user_email(args.admin_email)
    except odb.InvalidUser_Email:
        admin_user = None
    available_courses = courses_available_for_admin(admin_user)
    if not available_courses:
        raise ValueError(NO_COURSES_MESSAGE)
    if not args.course_id:
        rows = [
            [index, course.get(COURSE_NAME, ""), course[COURSE_ID]]
            for index, course in enumerate(available_courses, 1)
        ]
        print(tabulate(rows, headers=["#", "course name", "course ID"]))
        selection = input("Course(s) to add, by number or course_id (comma-separated): ").strip()
        args.course_id = [course[COURSE_ID] for course in parse_course_selection(selection, available_courses)]
    if not args.no_send_email and getattr(args, "planttracer_endpoint", None) is None:
        try:
            endpoint_from_args(args)
        except RuntimeError:
            args.planttracer_endpoint = input("Plant Tracer endpoint for login links: ").strip()


def admin_create(args, parser):
    if sys.stdin.isatty():
        prompt_admin_create(args)
    missing = [
        name
        for name in ["admin_email", "admin_name"]
        if getattr(args, name) is None
    ]
    if missing:
        parser.error("admin-create requires " + ", ".join("--" + name for name in missing))
    if not args.course_id:
        parser.error("admin-create requires --course_id, or an interactive terminal to select courses")
    try:
        admin_user = DDBO().get_user_email(args.admin_email)
    except odb.InvalidUser_Email:
        admin_user = None
    available_course_ids = {course[COURSE_ID] for course in courses_available_for_admin(admin_user)}
    unavailable = [course_id for course_id in args.course_id if course_id not in available_course_ids]
    if unavailable:
        parser.error("course(s) unavailable for this administrator: " + ", ".join(unavailable))

    send_email = not args.no_send_email
    result = course_management.admin_create_for_courses(
        admin_email=args.admin_email,
        admin_name=args.admin_name,
        course_ids=args.course_id,
        planttracer_endpoint=endpoint_from_args(args) if send_email else None,
        send_email=send_email,
    )
    print(f"administrator {result.admin_user.user_name} <{result.admin_user.email}>")
    print("added courses:")
    for course in result.added_courses:
        print(f"  {course_model_label(course)}")
        if send_email:
            print(f"  admin email sent to {result.admin_user.email} for {course.course_id}")


def prompt_existing_admin():
    """Prompt for an existing admin; return None when operator wants a new admin."""
    admins = odb.list_admins()
    if not admins:
        return None
    rows = [
        [
            index,
            admin.user_name,
            admin.email,
            "\n".join(format_admin_course(course) for course in admin.courses),
        ]
        for index, admin in enumerate(admins, 1)
    ]
    print(tabulate(rows, headers=["#", "name", "email", "admin courses"]))
    raw_selection = input("Existing admin #, or blank to create a new admin: ").strip()
    if not raw_selection:
        return None
    if not raw_selection.isdigit():
        raise ValueError("existing admin selection must be a number")
    index = int(raw_selection) - 1
    if index < 0 or index >= len(admins):
        raise ValueError(f"existing admin selection {raw_selection} is out of range")
    return admins[index]


def prompt_create_course(args):
    """Fill missing create-course arguments from an interactive terminal."""
    if args.course_id is None:
        args.course_id = input("Course ID/number: ").strip()
    if args.course_name is None:
        args.course_name = input("Course name: ").strip()
    if args.admin_email is None or args.admin_name is None:
        selected_admin = prompt_existing_admin()
        if selected_admin is not None:
            args.admin_email = selected_admin.email
            args.admin_name = selected_admin.user_name
        else:
            if args.admin_email is None:
                args.admin_email = input("Course administrator email: ").strip()
            if args.admin_name is None:
                args.admin_name = input("Course administrator name: ").strip()
    if args.send_email and getattr(args, "planttracer_endpoint", None) is None:
        try:
            endpoint_from_args(args)
        except RuntimeError:
            args.planttracer_endpoint = input("Plant Tracer endpoint for login links: ").strip()


def create_course_usage_text(missing):
    missing_flags = [flag for flag in CREATE_COURSE_REQUIRED_FLAGS if flag[2:] in missing]
    lines = [
        "create-course needs these flags when not running interactively:",
        "  --course_id       Course id/number, for example BIO101",
        "  --course_name     Course name, for example 'Plant Biology 101'",
        "  --admin_email     Course administrator email address",
        "  --admin_name      Course administrator display name",
    ]
    if missing_flags:
        lines.append("Missing: " + ", ".join(missing_flags))
    lines.extend([
        "",
        "Example:",
        "  dbutil create-course --course_id BIO101 --course_name 'Plant Biology 101' "
        "--admin_email teacher@example.edu --admin_name 'Teacher Name'",
    ])
    return "\n".join(lines)


def create_db():
    odbmaint.create_tables()


def drop_db():
    odbmaint.drop_tables()


def create_demo_course():
    result = populate_demo_user()
    verb = "created" if result.created else "already exists"
    print(f"demo course {result.course.course_id} {verb}")
    print(f"administrator {result.admin_user.user_name} <{result.admin_user.email}>")
    print(f"demo user {result.demo_user.user_name} <{result.demo_user.email}>")
    print(f"demo api_key {result.demo_api_key}")


def seed_demo_movies():
    seeded, skipped = populate_demo_movies()
    print(f"demo movies seeded={seeded} skipped={skipped}")


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
    if sys.stdin.isatty():
        prompt_create_course(args)
    missing = [
        name
        for name in ["course_id", "course_name", "admin_email", "admin_name"]
        if getattr(args, name) is None
    ]
    if missing:
        print(create_course_usage_text(missing), file=sys.stderr)
        parser.exit(2)
    result = course_management.create_course_with_admin(
        course_id=args.course_id,
        course_name=args.course_name,
        admin_email=args.admin_email,
        admin_name=args.admin_name,
        max_enrollment=args.max_enrollment,
        planttracer_endpoint=endpoint_from_args(args) if args.send_email else None,
        send_email=args.send_email,
    )
    if result.created:
        print(f"created {result.course.course_id}")
    else:
        print(f"course {result.course.course_id} already exists")
    print(json.dumps(result.course.model_dump(), indent=4, default=str))
    print(f"administrator {result.admin_user.user_name} <{result.admin_user.email}>")
    if args.send_email:
        print(f"admin email sent to {result.admin_user.email} for {result.course.course_id}")


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
    from_header = mailer.get_server_from_header()
    branch = apikey.git_branch().strip()
    commit = apikey.git_last_commit().strip()
    msg = EmailMessage()
    msg["Subject"] = "Plant Tracer test email"
    msg["From"] = from_header
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
    print(f"test email sent to {email} from {from_header}")


def build_parser():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    clogging.add_argument(parser, loglevel_default="WARNING")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("report", help="Print database tables, courses, and students")
    subparsers.add_parser(
        "admin-list",
        aliases=["admin_list"],
        help="List course administrators and their administered courses",
    )
    admin_create_parser = subparsers.add_parser(
        "admin-create",
        aliases=["admin_create"],
        help="Create/register a course administrator, add courses, and send login email",
    )
    admin_create_parser.add_argument("--admin_email", help="course administrator email")
    admin_create_parser.add_argument("--admin_name", help="course administrator name")
    admin_create_parser.add_argument(
        "--course_id",
        action="append",
        help="course id to administer; repeat for multiple courses",
    )
    admin_create_parser.add_argument(
        "--planttracer_endpoint",
        help="Plant Tracer https:// endpoint for email links; defaults to HOSTNAME.DOMAIN",
    )
    admin_create_parser.add_argument(
        "--no-send-email",
        action="store_true",
        help="Add the administrator without sending email",
    )
    subparsers.add_parser(
        "createdb",
        help="Create tables from etc/dynamodb_tables.json",
    )
    subparsers.add_parser("dropdb", help="Drop all configured DynamoDB tables")
    subparsers.add_parser(
        "create-demo-course",
        aliases=["create_demo_course"],
        help="Ensure the demo course, demo admin, demo user, and demo API key exist",
    )
    subparsers.add_parser(
        "seed-demo-movies",
        aliases=["seed_demo_movies"],
        help="Seed local demo movies after the demo course exists",
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
        dest="send_email",
        help="Send verification email to admin with magic link after ensuring course exists",
        action="store_true",
    )
    create_course_parser.add_argument(
        "--no-send-email",
        dest="send_email",
        help="Do not send course setup email",
        action="store_false",
    )
    create_course_parser.set_defaults(send_email=False)
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
    if args.command in ("admin-list", "admin_list"):
        admin_list()
        return 0
    if args.command in ("admin-create", "admin_create"):
        admin_create(args, parser)
        return 0
    if args.command == "createdb":
        create_db()
        return 0
    if args.command == "dropdb":
        drop_db()
        return 0
    if args.command in ("create-demo-course", "create_demo_course"):
        create_demo_course()
        return 0
    if args.command in ("seed-demo-movies", "seed_demo_movies"):
        seed_demo_movies()
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
