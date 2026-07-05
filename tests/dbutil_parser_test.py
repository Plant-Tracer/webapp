import pytest

import dbutil


def parse_args(*args):
    return dbutil.build_parser().parse_args(args)


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


def test_dbutil_has_admin_list_command():
    args = parse_args("admin-list")

    assert args.command == "admin-list"


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


def test_dbutil_rejects_old_flag_style_commands():
    with pytest.raises(SystemExit):
        parse_args("--create_course", "--course_id", "PLANT101")


def test_dbutil_keeps_double_dash_for_options():
    args = parse_args("makelink", "admin@example.com", "--planttracer_endpoint", "http://localhost:8080")

    assert args.command == "makelink"
    assert args.email == "admin@example.com"
    assert args.planttracer_endpoint == "http://localhost:8080"
