import sys
import uuid
from types import SimpleNamespace

import pytest

from app import odb
from app.dynamodb_prefixes import PrefixSummary
from app import odb_movie_data
from app.odb import MOVIE_ID
from app.schema import AdminCourse

import dbutil

from .constants import ADMIN_EMAIL, USER_EMAIL


HOSTNAME_ENV = "HOSTNAME"
DOMAIN_ENV = "DOMAIN"


def parse_args(*args):
    return dbutil.build_parser().parse_args(args)


def fake_dynamodb_resource():
    return object()


def test_dbutil_commands_do_not_use_option_prefix():
    args = parse_args(
        "create-course",
        "--course_id",
        "PLANT101",
        "--course_name",
        "Plant Movement",
        "--admin_email",
        "admin@example.com",
        "--admin_name",
        "Course Admin",
    )

    assert args.command == "create-course"
    assert args.course_id == "PLANT101"
    assert args.admin_email == "admin@example.com"


def test_dbutil_create_course_can_disable_email():
    args = parse_args(
        "create-course",
        "--course_id",
        "PLANT101",
        "--course_name",
        "Plant Movement",
        "--admin_email",
        "admin@example.com",
        "--admin_name",
        "Course Admin",
        "--send-email",
        "--no-send-email",
    )

    assert args.command == "create-course"
    assert args.send_email is False


def test_create_course_missing_flags_usage_is_brief():
    usage = dbutil.create_course_usage_text(["course_id", "admin_email"])

    assert "create-course needs these flags" in usage
    assert "--course_id" in usage
    assert "--course_name" in usage
    assert "Missing: --course_id, --admin_email" in usage
    assert "usage:" not in usage.lower()


def test_course_sort_key_handles_missing_or_null_names():
    assert dbutil.course_sort_key({}) == ("", "")
    assert dbutil.course_sort_key({"course_name": None, "course_id": None}) == ("", "")
    assert dbutil.course_sort_key({"course_name": "Botany", "course_id": "BIO101"}) == ("botany", "bio101")


def test_course_label_helpers_format_dicts_and_models():
    named_course = AdminCourse(course_id="BIO101", course_name="Plant Biology")
    unnamed_course = AdminCourse(course_id="BIO102", course_name="")

    assert dbutil.course_label({dbutil.COURSE_ID: "BIO103", dbutil.COURSE_NAME: "Shoots"}) == "Shoots (BIO103)"
    assert dbutil.course_label({dbutil.COURSE_ID: "BIO104"}) == " (BIO104)"
    assert dbutil.course_model_label(named_course) == "Plant Biology (BIO101)"
    assert dbutil.format_admin_course(named_course) == "Plant Biology (BIO101)"
    assert dbutil.format_admin_course(unnamed_course) == "BIO102"


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ([], False),
        (["name"], False),
        (["Name", " Email "], True),
        (["student", "email"], False),
    ],
)
def test_csv_has_header(row, expected):
    assert dbutil.csv_has_header(row) is expected


def test_parse_course_selection_accepts_numbers_and_ids_once():
    available_courses = [
        {dbutil.COURSE_ID: "BIO101", dbutil.COURSE_NAME: "Plant Biology"},
        {dbutil.COURSE_ID: "BIO102", dbutil.COURSE_NAME: "Roots"},
        {dbutil.COURSE_ID: "BIO103", dbutil.COURSE_NAME: "Shoots"},
    ]

    selected = dbutil.parse_course_selection(" 2, BIO103, , 1, BIO102 ", available_courses)

    assert [course[dbutil.COURSE_ID] for course in selected] == ["BIO102", "BIO103", "BIO101"]


@pytest.mark.parametrize(
    ("selection", "message"),
    [
        ("0", "out of range"),
        ("4", "out of range"),
        ("BIO999", "unknown course_id"),
        (" , ", "no courses selected"),
    ],
)
def test_parse_course_selection_rejects_invalid_tokens(selection, message):
    available_courses = [
        {dbutil.COURSE_ID: "BIO101", dbutil.COURSE_NAME: "Plant Biology"},
        {dbutil.COURSE_ID: "BIO102", dbutil.COURSE_NAME: "Roots"},
        {dbutil.COURSE_ID: "BIO103", dbutil.COURSE_NAME: "Shoots"},
    ]

    with pytest.raises(ValueError, match=message):
        dbutil.parse_course_selection(selection, available_courses)


def test_planttracer_endpoint_uses_hostname_and_domain(monkeypatch):
    monkeypatch.setenv(HOSTNAME_ENV, "stack-name")
    monkeypatch.setenv(DOMAIN_ENV, "planttracer.com")

    assert dbutil.planttracer_endpoint() == "https://stack-name.planttracer.com"


def test_planttracer_endpoint_requires_hostname_and_domain(monkeypatch):
    monkeypatch.delenv(HOSTNAME_ENV, raising=False)
    monkeypatch.delenv(DOMAIN_ENV, raising=False)

    with pytest.raises(RuntimeError, match="HOSTNAME, DOMAIN"):
        dbutil.planttracer_endpoint()


def test_courses_available_for_admin_filters_current_admin_courses(new_course):
    available_course_id = "Available " + uuid.uuid4().hex[:8]
    dbutil.odb.create_course(
        course_id=available_course_id,
        course_name="Available Course",
        course_key="available-" + uuid.uuid4().hex[:8],
    )

    try:
        all_course_ids = {course[dbutil.COURSE_ID] for course in dbutil.courses_available_for_admin()}
        admin_user = dbutil.DDBO().get_user_email(new_course[ADMIN_EMAIL])
        available_course_ids = {
            course[dbutil.COURSE_ID]
            for course in dbutil.courses_available_for_admin(admin_user)
        }

        assert new_course[dbutil.COURSE_ID] in all_course_ids
        assert available_course_id in all_course_ids
        assert new_course[dbutil.COURSE_ID] not in available_course_ids
        assert available_course_id in available_course_ids
    finally:
        dbutil.odb.delete_course(course_id=available_course_id)


def test_print_report_with_course_does_not_crash(new_course, capsys):
    dbutil.print_report()

    output = capsys.readouterr().out
    assert "Courses" in output
    assert new_course[dbutil.COURSE_ID] in output


def test_dump_movie_with_movie_does_not_crash(new_movie, capsys):
    dbutil.dump_movie(new_movie[MOVIE_ID])

    output = capsys.readouterr().out
    assert new_movie[MOVIE_ID] in output


def test_admin_list_prints_course_admin(new_course, capsys):
    dbutil.admin_list()

    output = capsys.readouterr().out
    assert new_course[ADMIN_EMAIL] in output
    assert new_course[dbutil.COURSE_ID] in output


def test_user_list_prints_all_users(new_course, capsys):
    dbutil.user_list()

    output = capsys.readouterr().out
    assert new_course[ADMIN_EMAIL] in output
    assert new_course[USER_EMAIL] in output
    assert new_course[dbutil.COURSE_ID] in output


def test_superadmin_list_prints_test_created_superadmin(new_course, capsys):
    change = dbutil.set_super_role_by_email(new_course[USER_EMAIL], odb.SUPER_ROLE_SUPERADMIN)
    assert change.old_super_role == odb.SUPER_ROLE_NONE
    assert change.new_super_role == odb.SUPER_ROLE_SUPERADMIN

    dbutil.superadmin_list(SimpleNamespace(role="all"))

    output = capsys.readouterr().out
    assert new_course[USER_EMAIL] in output
    assert odb.SUPER_ROLE_SUPERADMIN in output


def test_set_super_role_blocks_removing_last_superadmin(new_course):
    dbutil.set_super_role_by_email(new_course[USER_EMAIL], odb.SUPER_ROLE_SUPERADMIN)

    with pytest.raises(ValueError, match="last superadmin"):
        dbutil.set_super_role_by_email(new_course[USER_EMAIL], odb.SUPER_ROLE_NONE)


def test_set_super_role_can_remove_superadmin_when_another_exists(new_course):
    dbutil.set_super_role_by_email(new_course[USER_EMAIL], odb.SUPER_ROLE_SUPERADMIN)
    dbutil.set_super_role_by_email(new_course[ADMIN_EMAIL], odb.SUPER_ROLE_SUPERADMIN)

    change = dbutil.set_super_role_by_email(new_course[USER_EMAIL], odb.SUPER_ROLE_NONE)

    assert change.old_super_role == odb.SUPER_ROLE_SUPERADMIN
    assert change.new_super_role == odb.SUPER_ROLE_NONE


def test_stale_super_role_transaction_cannot_remove_final_superadmin(new_course):
    dbutil.set_super_role_by_email(new_course[USER_EMAIL], odb.SUPER_ROLE_SUPERADMIN)
    dbutil.set_super_role_by_email(new_course[ADMIN_EMAIL], odb.SUPER_ROLE_SUPERADMIN)
    ddbo = new_course["ddbo"]
    stale_state = dbutil.reconcile_super_role_state(ddbo)
    user = ddbo.get_user_email(new_course[USER_EMAIL])
    admin = ddbo.get_user_email(new_course[ADMIN_EMAIL])

    dbutil.transact_super_role_change(ddbo, user, stale_state, odb.SUPER_ROLE_NONE)
    with pytest.raises(dbutil.ConcurrentSuperRoleChange, match="concurrently"):
        dbutil.transact_super_role_change(ddbo, admin, stale_state, odb.SUPER_ROLE_NONE)
    with pytest.raises(ValueError, match="last superadmin"):
        dbutil.set_super_role_by_email(new_course[ADMIN_EMAIL], odb.SUPER_ROLE_NONE)

    assert odb.normalize_super_role(ddbo.get_user(user[dbutil.USER_ID])) == odb.SUPER_ROLE_NONE
    assert odb.normalize_super_role(ddbo.get_user(admin[dbutil.USER_ID])) == odb.SUPER_ROLE_SUPERADMIN


def test_demo_movie_seeding_is_idempotent(local_ddb, capsys):
    del local_ddb

    dbutil.create_demo_course()
    course_output = capsys.readouterr().out
    assert dbutil.DEMO_COURSE_ID in course_output
    assert dbutil.DEFAULT_ADMIN_EMAIL in course_output

    seeded, skipped = dbutil.populate_demo_movies()
    try:
        assert seeded > 0
        assert skipped == 0

        dbutil.seed_demo_movies()
        seed_output = capsys.readouterr().out
        assert f"demo movies seeded=0 skipped={seeded}" in seed_output
    finally:
        for movie in dbutil.DDBO().get_movies_for_course_id(dbutil.DEMO_COURSE_ID):
            odb_movie_data.purge_movie(movie_id=movie[MOVIE_ID])
            odb_movie_data.delete_movie(movie_id=movie[MOVIE_ID])


def test_dbutil_has_admin_list_command():
    args = parse_args("admin-list")

    assert args.command == "admin-list"


def test_dbutil_has_user_list_command():
    args = parse_args("user-list")

    assert args.command == "user-list"


def test_dbutil_has_list_prefixes_command():
    args = parse_args("list-prefixes")

    assert args.command == "list-prefixes"


def test_dbutil_does_not_have_table_list_command():
    with pytest.raises(SystemExit):
        parse_args("table-list")


def test_dbutil_missing_prefix_prints_available_prefixes(monkeypatch, capsys):
    monkeypatch.delenv(dbutil.C.DYNAMODB_TABLE_PREFIX, raising=False)
    monkeypatch.setenv(dbutil.C.AWS_REGION, "us-east-1")
    monkeypatch.setattr(sys, "argv", ["dbutil", "report"])
    monkeypatch.setattr(dbutil, "dynamodb_resource_for_prefix_listing", fake_dynamodb_resource)
    monkeypatch.setattr(
        dbutil,
        "prefix_summaries",
        lambda _dynamodb: [
            PrefixSummary(
                prefix="demo-",
                courses=1,
                users=2,
                movies=3,
                date_from=1_700_000_000,
                date_to=1_700_000_060,
            )
        ],
    )

    assert dbutil.main() == 1

    captured = capsys.readouterr()
    assert captured.err.splitlines()[0] == "AWS_REGION=us-east-1"
    assert "ERROR: Environment variable DYNAMODB_TABLE_PREFIX is not set" in captured.err
    assert "Available DYNAMODB_TABLE_PREFIX values:" in captured.err
    assert "demo-" in captured.err
    assert "Set DYNAMODB_TABLE_PREFIX to one of the listed prefixes and retry." in captured.err


def test_dbutil_list_prefixes_runs_without_selected_prefix(monkeypatch, capsys):
    monkeypatch.delenv(dbutil.C.DYNAMODB_TABLE_PREFIX, raising=False)
    monkeypatch.setattr(sys, "argv", ["dbutil", "list-prefixes"])
    monkeypatch.setattr(dbutil, "dynamodb_resource_for_prefix_listing", fake_dynamodb_resource)
    monkeypatch.setattr(
        dbutil,
        "prefix_summaries",
        lambda _dynamodb: [
            PrefixSummary(
                prefix="demo-",
                courses=1,
                users=2,
                movies=3,
                date_from=1_700_000_000,
                date_to=1_700_000_060,
            )
        ],
    )

    assert dbutil.main() == 0

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "prefix  courses  users  movies  from                  to",
        "demo-         1      2       3  2023-11-14T22:13:20Z  2023-11-14T22:14:20Z",
    ]
    assert captured.err == ""


def test_dbutil_has_superadmin_list_command():
    args = parse_args("superadmin-list", "--role", "superadmin")

    assert args.command == "superadmin-list"
    assert args.role == odb.SUPER_ROLE_SUPERADMIN


def test_dbutil_has_super_role_mutation_commands():
    args = parse_args(
        "set-super-role",
        "--email",
        "teacher@example.com",
        "--role",
        "superauditor",
    )
    add_args = parse_args("add-superadmin", "--email", "teacher@example.com")
    remove_args = parse_args("remove-superadmin", "--email", "teacher@example.com")

    assert args.command == "set-super-role"
    assert args.email == "teacher@example.com"
    assert args.role == odb.SUPER_ROLE_SUPERAUDITOR
    assert add_args.command == "add-superadmin"
    assert remove_args.command == "remove-superadmin"


def test_dbutil_course_admin_commands_accept_email_alias():
    add_args = parse_args("add-admin", "--email", "teacher@example.com", "--course_id", "BIO101")
    remove_args = parse_args("remove-admin", "--email", "teacher@example.com", "--course_id", "BIO101")

    assert add_args.admin_email == "teacher@example.com"
    assert remove_args.admin_email == "teacher@example.com"


def test_dbutil_has_admin_create_command():
    args = parse_args(
        "admin-create",
        "--admin_email",
        "teacher@example.com",
        "--admin_name",
        "Course Teacher",
        "--course_id",
        "BIO101",
        "--course_id",
        "BIO102",
        "--no-send-email",
    )

    assert args.command == "admin-create"
    assert args.admin_email == "teacher@example.com"
    assert args.admin_name == "Course Teacher"
    assert args.course_id == ["BIO101", "BIO102"]
    assert args.no_send_email is True


def test_dbutil_has_create_demo_course_command():
    args = parse_args("create-demo-course")

    assert args.command == "create-demo-course"


def test_dbutil_has_seed_demo_movies_command():
    args = parse_args("seed-demo-movies")

    assert args.command == "seed-demo-movies"


def test_dbutil_no_longer_has_create_demo_command():
    with pytest.raises(SystemExit):
        parse_args("create-demo")


def test_dbutil_rejects_old_flag_style_commands():
    with pytest.raises(SystemExit):
        parse_args("--create_course", "--course_id", "PLANT101")


def test_dbutil_keeps_double_dash_for_options():
    args = parse_args("makelink", "admin@example.com", "--planttracer_endpoint", "http://localhost:8080")

    assert args.command == "makelink"
    assert args.email == "admin@example.com"
    assert args.planttracer_endpoint == "http://localhost:8080"
