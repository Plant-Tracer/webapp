"""Integration contract tests for the planned src/dbbackup.py CLI."""

import io
import json
import os
import subprocess
import sys
import uuid
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest
from boto3.dynamodb.types import TypeDeserializer

import dbbackup
from app import odb, odbmaint
from app.constants import C
from app.odb import (
    API_KEYS,
    COURSE_ID,
    COURSE_NAME,
    COURSE_USERS,
    COURSES,
    CREATED,
    CREATED_AT,
    DATE_UPLOADED,
    DELETED,
    EMAIL,
    ENABLED,
    FRAME_NUMBER,
    FRAMES,
    LAST_FRAME_TRACKED,
    LOGS,
    MOVIE_DATA_URN,
    MOVIE_ID,
    MOVIE_STATE_READY,
    MOVIE_STATUS,
    MOVIE_TRACED_URN,
    MOVIE_ZIPFILE_URN,
    MOVIES,
    NEEDS_RETRACING,
    UNIQUE_EMAILS,
    USER_ID,
    USER_NAME,
    USERS,
    DDBO,
)
from app import odb_movie_data
from app.s3_presigned import s3_client


ROOT_DIR = Path(__file__).resolve().parents[1]
DBBACKUP = ROOT_DIR / "src" / "dbbackup.py"
TYPE_DESERIALIZER = TypeDeserializer()
TABLE_FILES = {
    USERS: "tables/users.jsonl",
    COURSES: "tables/courses.jsonl",
    COURSE_USERS: "tables/course_users.jsonl",
    MOVIES: "tables/movies.jsonl",
    FRAMES: "tables/movie_frames.jsonl",
}
EXCLUDED_TABLE_FILES = {
    API_KEYS: "tables/api_keys.jsonl",
    UNIQUE_EMAILS: "tables/unique_emails.jsonl",
    LOGS: "tables/logs.jsonl",
}


@dataclass(frozen=True)
# pylint: disable=too-many-instance-attributes
class BackupScenario:
    """A compact graph that exercises backup dependency closure."""

    source_prefix: str
    bucket: str
    primary_course_id: str
    movie_course_id: str
    migration_course_id: str
    owner_user_id: str
    owner_email: str
    admin_user_id: str
    admin_email: str
    active_movie_id: str
    deleted_movie_id: str
    active_movie_key: str
    deleted_movie_key: str
    active_movie_bytes: bytes
    deleted_movie_bytes: bytes


@dataclass
class PtbContents:
    """Parsed .ptb test view."""

    names: set[str]
    manifest: dict
    readme: str
    raw_tables: dict[str, list[dict]]
    tables: dict[str, list[dict]]


@pytest.fixture
def prefix_tools(local_ddb, monkeypatch):
    """Create/drop test table prefixes while keeping DDBO's singleton honest."""
    source_prefix = os.environ[C.DYNAMODB_TABLE_PREFIX]
    created_prefixes: list[str] = []

    def set_prefix(prefix: str) -> DDBO:
        DDBO._instance = None  # pylint: disable=protected-access
        monkeypatch.setenv(C.DYNAMODB_TABLE_PREFIX, prefix)
        return DDBO()

    def create_empty_prefix(prefix: str) -> DDBO:
        DDBO._instance = None  # pylint: disable=protected-access
        monkeypatch.setenv(C.DYNAMODB_TABLE_PREFIX, prefix)
        odbmaint.drop_tables(silent_warnings=True)
        odbmaint.create_tables()
        created_prefixes.append(prefix)
        return DDBO()

    yield {
        "source_prefix": source_prefix,
        "set_prefix": set_prefix,
        "create_empty_prefix": create_empty_prefix,
    }

    for prefix in created_prefixes:
        DDBO._instance = None  # pylint: disable=protected-access
        monkeypatch.setenv(C.DYNAMODB_TABLE_PREFIX, prefix)
        odbmaint.drop_tables(silent_warnings=True)
    set_prefix(source_prefix)


def unique_name(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:10]}"


def run_dbbackup(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run dbbackup as an operator-facing CLI command."""
    env = os.environ.copy()
    if "--table-prefix" in args:
        env[C.DYNAMODB_TABLE_PREFIX] = "ignored-env-prefix"
    old_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in ["lambda-resize/src", "src", old_pythonpath] if part
    )
    result = subprocess.run(
        [sys.executable, str(DBBACKUP), *args],
        cwd=ROOT_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"dbbackup exited {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def scan_table(table) -> list[dict]:
    items: list[dict] = []
    scan_kwargs = {}
    while True:
        response = table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))
        last_evaluated_key = response.get("LastEvaluatedKey")
        if last_evaluated_key is None:
            return items
        scan_kwargs["ExclusiveStartKey"] = last_evaluated_key


def snapshot_prefix(prefix_tools, prefix: str) -> dict[str, list[dict]]:
    ddbo = prefix_tools["set_prefix"](prefix)
    return {
        USERS: sorted(scan_table(ddbo.users), key=lambda row: row[USER_ID]),
        UNIQUE_EMAILS: sorted(scan_table(ddbo.unique_emails), key=lambda row: row[EMAIL]),
        API_KEYS: sorted(scan_table(ddbo.api_keys), key=lambda row: row.get("api_key", "")),
        COURSES: sorted(scan_table(ddbo.courses), key=lambda row: row[COURSE_ID]),
        COURSE_USERS: sorted(
            scan_table(ddbo.course_users),
            key=lambda row: (row[COURSE_ID], row[USER_ID]),
        ),
        MOVIES: sorted(scan_table(ddbo.movies), key=lambda row: row[MOVIE_ID]),
        FRAMES: sorted(
            scan_table(ddbo.movie_frames),
            key=lambda row: (row[MOVIE_ID], row[FRAME_NUMBER]),
        ),
        LOGS: sorted(scan_table(ddbo.logs), key=lambda row: row.get("log_id", "")),
    }


def read_ptb(path: Path) -> PtbContents:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        raw_tables = {}
        tables = {}
        for table, member_name in TABLE_FILES.items():
            with archive.open(member_name) as f:
                raw_tables[table] = [
                    json.loads(line)
                    for line in f.read().decode().splitlines()
                ]
                tables[table] = [
                    {
                        key: TYPE_DESERIALIZER.deserialize(value)
                        for key, value in row.items()
                    }
                    for row in raw_tables[table]
                ]
        return PtbContents(
            names=names,
            manifest=json.loads(archive.read("manifest.json")),
            readme=archive.read("README").decode(),
            raw_tables=raw_tables,
            tables=tables,
        )


def row_values(rows: list[dict], key: str) -> set[str]:
    return {row[key] for row in rows}


def s3_object_exists(bucket: str, key: str) -> bool:
    try:
        s3_client().head_object(Bucket=bucket, Key=key)
        return True
    except Exception:  # pylint: disable=broad-exception-caught
        return False


def s3_object_bytes(bucket: str, key: str) -> bytes:
    return s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()


def delete_s3_objects(bucket: str, *keys: str) -> None:
    for key in keys:
        s3_client().delete_object(Bucket=bucket, Key=key)


def normalized_prefix(prefix: str) -> str:
    return (prefix.rstrip("-") + "-") if prefix else ""


def create_partial_users_table(dynamodb, table_name: str) -> None:
    table = dynamodb.create_table(
        **{
            odbmaint.TableName: table_name,
            odbmaint.KeySchema: [
                {odbmaint.AttributeName: USER_ID, odbmaint.KeyType: odbmaint.HASH},
            ],
            odbmaint.AttributeDefinitions: [
                {odbmaint.AttributeName: USER_ID, odbmaint.AttributeType: odbmaint.S},
            ],
            odbmaint.BillingMode: odbmaint.PAY_PER_REQUEST,
        }
    )
    table.wait_until_exists()


def make_course(ddbo: DDBO, course_id: str, *, admins: list[str] | None = None) -> None:
    ddbo.put_course(
        {
            COURSE_ID: course_id,
            COURSE_NAME: f"Course {course_id}",
            "course_key": f"key-{uuid.uuid4().hex[:16]}",
            "admins_for_course": admins or [],
            "max_enrollment": 50,
        }
    )


def make_user(
    ddbo: DDBO,
    *,
    user_id: str,
    email: str,
    name: str,
    primary_course_id: str,
    primary_course_name: str,
    courses: list[str],
    admin_for_courses: list[str] | None = None,
    created: int = 1_800_000_000,
) -> None:
    ddbo.put_user(
        {
            USER_ID: user_id,
            EMAIL: email,
            USER_NAME: name,
            CREATED: created,
            ENABLED: 1,
            "admin_for_courses": admin_for_courses or [],
            "primary_course_id": primary_course_id,
            "primary_course_name": primary_course_name,
            "courses": courses,
        }
    )
    for course_id in courses:
        ddbo.course_users.put_item(Item={COURSE_ID: course_id, USER_ID: user_id})


def create_movie(
    ddbo: DDBO,
    *,
    user_id: str,
    course_id: str,
    title: str,
    movie_bytes: bytes,
    deleted: int = 0,
) -> tuple[str, str]:
    movie_id = odb.create_new_movie(
        user_id=user_id,
        course_id=course_id,
        title=title,
        description=f"{title} description",
        research_use=1,
        credit_by_name=0,
        attribution_name=None,
        fpm="0.5",
    )
    odb_movie_data.set_movie_data(movie_id=movie_id, movie_data=movie_bytes)
    movie = ddbo.get_movie(movie_id)
    movie_key = movie[MOVIE_DATA_URN].split(f"s3://{os.environ[C.PLANTTRACER_S3_BUCKET]}/", 1)[1]
    zip_key = f"{course_id}/{movie_id}_zipfile.mov"
    traced_key = f"{course_id}/{movie_id}_traced.mov"
    original_key = f"{course_id}/{movie_id}-orig.mp4"
    s3_client().put_object(Bucket=os.environ[C.PLANTTRACER_S3_BUCKET], Key=zip_key, Body=b"zip bytes")
    s3_client().put_object(Bucket=os.environ[C.PLANTTRACER_S3_BUCKET], Key=traced_key, Body=b"traced bytes")
    s3_client().put_object(Bucket=os.environ[C.PLANTTRACER_S3_BUCKET], Key=original_key, Body=b"original bytes")
    ddbo.update_table(
        ddbo.movies,
        movie_id,
        {
            MOVIE_STATUS: MOVIE_STATE_READY,
            DELETED: deleted,
            LAST_FRAME_TRACKED: 1,
            NEEDS_RETRACING: 0,
            MOVIE_ZIPFILE_URN: f"s3://{os.environ[C.PLANTTRACER_S3_BUCKET]}/{zip_key}",
            MOVIE_TRACED_URN: f"s3://{os.environ[C.PLANTTRACER_S3_BUCKET]}/{traced_key}",
        },
    )
    ddbo.put_movie_frame(
        {
            MOVIE_ID: movie_id,
            FRAME_NUMBER: 0,
            "trackpoints": [
                {"x": Decimal("10.0"), "y": Decimal("20.0"), "label": "Apex"},
                {"x": Decimal("30.0"), "y": Decimal("40.0"), "label": "Ruler 10mm"},
            ],
        }
    )
    ddbo.put_movie_frame(
        {
            MOVIE_ID: movie_id,
            FRAME_NUMBER: 1,
            "trackpoints": [{"x": Decimal("11.0"), "y": Decimal("21.0"), "label": "Apex"}],
        }
    )
    return movie_id, movie_key


@pytest.fixture
def backup_scenario(prefix_tools, local_s3) -> BackupScenario:
    ddbo = prefix_tools["set_prefix"](prefix_tools["source_prefix"])
    suffix = uuid.uuid4().hex[:8]
    primary_course_id = f"backup-primary-{suffix}"
    movie_course_id = f"backup-movies-{suffix}"
    migration_course_id = f"backup-target-{suffix}"
    owner_user_id = odb.new_user_id()
    admin_user_id = odb.new_user_id()
    owner_email = f"backup-owner-{suffix}@example.com"
    admin_email = f"backup-admin-{suffix}@example.com"

    make_course(ddbo, primary_course_id)
    make_course(ddbo, movie_course_id, admins=[admin_user_id])
    make_course(ddbo, migration_course_id)
    make_user(
        ddbo,
        user_id=owner_user_id,
        email=owner_email,
        name="Backup Owner",
        primary_course_id=primary_course_id,
        primary_course_name=f"Course {primary_course_id}",
        courses=[primary_course_id, movie_course_id],
    )
    make_user(
        ddbo,
        user_id=admin_user_id,
        email=admin_email,
        name="Backup Admin",
        primary_course_id=movie_course_id,
        primary_course_name=f"Course {movie_course_id}",
        courses=[movie_course_id],
        admin_for_courses=[movie_course_id],
    )
    odb.make_new_api_key_for_user_id(user_id=owner_user_id)
    ddbo.logs.put_item(
        Item={
            "log_id": f"log-{suffix}",
            "ipaddr": "127.0.0.1",
            USER_ID: owner_user_id,
            COURSE_ID: movie_course_id,
            "time_t": 1_800_000_001,
        }
    )

    active_movie_bytes = f"analysis mp4 active {suffix}".encode()
    deleted_movie_bytes = f"analysis mp4 deleted {suffix}".encode()
    active_movie_id, active_movie_key = create_movie(
        ddbo,
        user_id=owner_user_id,
        course_id=movie_course_id,
        title="Active backup movie",
        movie_bytes=active_movie_bytes,
    )
    deleted_movie_id, deleted_movie_key = create_movie(
        ddbo,
        user_id=owner_user_id,
        course_id=movie_course_id,
        title="Deleted backup movie",
        movie_bytes=deleted_movie_bytes,
        deleted=1,
    )

    return BackupScenario(
        source_prefix=prefix_tools["source_prefix"],
        bucket=local_s3,
        primary_course_id=primary_course_id,
        movie_course_id=movie_course_id,
        migration_course_id=migration_course_id,
        owner_user_id=owner_user_id,
        owner_email=owner_email,
        admin_user_id=admin_user_id,
        admin_email=admin_email,
        active_movie_id=active_movie_id,
        deleted_movie_id=deleted_movie_id,
        active_movie_key=active_movie_key,
        deleted_movie_key=deleted_movie_key,
        active_movie_bytes=active_movie_bytes,
        deleted_movie_bytes=deleted_movie_bytes,
    )


def assert_standard_ptb_layout(ptb: PtbContents) -> None:
    assert "manifest.json" in ptb.names
    assert "README" in ptb.names
    for member_name in TABLE_FILES.values():
        assert member_name in ptb.names
    for member_name in EXCLUDED_TABLE_FILES.values():
        assert member_name not in ptb.names


def assert_readme_warns_about_student_data(ptb: PtbContents) -> None:
    readme = ptb.readme.lower()
    assert "student" in readme
    assert "movie" in readme
    assert "not password protected" in readme
    assert "sensitive" in readme


def assert_no_excluded_artifacts(ptb: PtbContents) -> None:
    forbidden_fragments = ("zipfile", "_traced", "-orig", ".zip")
    assert all(not any(fragment in name for fragment in forbidden_fragments) for name in ptb.names)


def assert_uses_dynamodb_attribute_json(ptb: PtbContents) -> None:
    movie_rows = ptb.raw_tables[MOVIES]
    assert movie_rows
    assert all(set(row[MOVIE_ID]) == {"S"} for row in movie_rows)
    assert all(set(row[DELETED]) == {"N"} for row in movie_rows)


@pytest.mark.parametrize(
    ("selection_args", "include_deleted", "expect_admin"),
    [
        (("backup",), False, True),
        (("backup", "--course-id", "{movie_course_id}"), False, True),
        (("backup", "--user-email", "{owner_email}"), False, False),
        (("backup", "--movie-id", "{active_movie_id}"), False, False),
        (("backup", "--course-id", "{movie_course_id}", "--include-deleted"), True, True),
    ],
)
def test_backup_selection_matrix(
    tmp_path,
    backup_scenario: BackupScenario,
    selection_args,
    include_deleted,
    expect_admin,
):
    archive_path = tmp_path / "selection.ptb"
    formatted_selection = [
        value.format(**backup_scenario.__dict__) for value in selection_args
    ]

    run_dbbackup(
        formatted_selection[0],
        "--table-prefix",
        backup_scenario.source_prefix,
        "--output",
        str(archive_path),
        *formatted_selection[1:],
    )

    ptb = read_ptb(archive_path)
    assert_standard_ptb_layout(ptb)
    assert_readme_warns_about_student_data(ptb)
    assert_no_excluded_artifacts(ptb)
    assert_uses_dynamodb_attribute_json(ptb)
    assert f"movies/{backup_scenario.active_movie_id}.mp4" in ptb.names
    assert (f"movies/{backup_scenario.deleted_movie_id}.mp4" in ptb.names) is include_deleted

    users = row_values(ptb.tables[USERS], USER_ID)
    courses = row_values(ptb.tables[COURSES], COURSE_ID)
    movies = row_values(ptb.tables[MOVIES], MOVIE_ID)
    assert backup_scenario.owner_user_id in users
    assert (backup_scenario.admin_user_id in users) is expect_admin
    assert backup_scenario.movie_course_id in courses
    assert backup_scenario.active_movie_id in movies
    assert (backup_scenario.deleted_movie_id in movies) is include_deleted

    if len(selection_args) > 1 and selection_args[1] == "--user-email":
        assert backup_scenario.primary_course_id in courses


def test_backup_warns_and_skips_missing_movie_object(
    tmp_path,
    backup_scenario: BackupScenario,
):
    archive_path = tmp_path / "missing-movie.ptb"
    delete_s3_objects(backup_scenario.bucket, backup_scenario.active_movie_key)

    result = run_dbbackup(
        "backup",
        "--table-prefix",
        backup_scenario.source_prefix,
        "--output",
        str(archive_path),
        "--course-id",
        backup_scenario.movie_course_id,
    )

    stderr = result.stderr.lower()
    assert "examining dynamodb tables" in stderr
    assert "preflight checking" in stderr
    assert "creating archive" in stderr
    assert "warning:" in stderr
    assert backup_scenario.active_movie_id in result.stderr
    assert "does not exist" in stderr

    ptb = read_ptb(archive_path)
    assert f"movies/{backup_scenario.active_movie_id}.mp4" not in ptb.names
    assert backup_scenario.active_movie_id not in row_values(ptb.tables[MOVIES], MOVIE_ID)
    assert backup_scenario.active_movie_id not in row_values(ptb.tables[FRAMES], MOVIE_ID)
    assert any(backup_scenario.active_movie_id in warning for warning in ptb.manifest["warnings"])


def test_backup_overwrite_requires_same_prefix_and_reuses_movie_objects(
    tmp_path,
    backup_scenario: BackupScenario,
):
    archive_path = tmp_path / "overwrite.ptb"

    run_dbbackup(
        "backup",
        "--table-prefix",
        backup_scenario.source_prefix,
        "--output",
        str(archive_path),
        "--course-id",
        backup_scenario.movie_course_id,
    )

    denied = run_dbbackup(
        "backup",
        "--table-prefix",
        unique_name("wrong-prefix"),
        "--output",
        str(archive_path),
        check=False,
    )
    assert denied.returncode != 0
    assert "refusing to overwrite" in denied.stderr
    assert normalized_prefix(backup_scenario.source_prefix) == read_ptb(archive_path).manifest[
        "source_table_prefix"
    ]

    delete_s3_objects(backup_scenario.bucket, backup_scenario.active_movie_key)
    result = run_dbbackup(
        "backup",
        "--table-prefix",
        backup_scenario.source_prefix,
        "--output",
        str(archive_path),
        "--course-id",
        backup_scenario.movie_course_id,
    )

    stderr = result.stderr.lower()
    assert "reusing archived movie object" in stderr
    assert "missing in s3" in stderr
    assert not s3_object_exists(backup_scenario.bucket, backup_scenario.active_movie_key)

    ptb = read_ptb(archive_path)
    assert f"movies/{backup_scenario.active_movie_id}.mp4" in ptb.names
    assert backup_scenario.active_movie_id in row_values(ptb.tables[MOVIES], MOVIE_ID)
    with zipfile.ZipFile(archive_path) as archive:
        assert (
            archive.read(f"movies/{backup_scenario.active_movie_id}.mp4")
            == backup_scenario.active_movie_bytes
        )


def test_list_prefixes_reports_complete_prefix_counts(prefix_tools):
    list_prefix = unique_name("list-prefix")
    partial_prefix = unique_name("partial-prefix")
    course_id = unique_name("list-course")
    user_id = odb.new_user_id()
    email = f"list-prefix-{uuid.uuid4().hex[:8]}@example.com"
    ddbo = prefix_tools["create_empty_prefix"](list_prefix)
    make_course(ddbo, course_id)
    ddbo.courses.update_item(
        Key={COURSE_ID: course_id},
        UpdateExpression="SET #created_at = :created_at",
        ExpressionAttributeNames={"#created_at": CREATED_AT},
        ExpressionAttributeValues={":created_at": 1_600_000_000},
    )
    make_user(
        ddbo,
        user_id=user_id,
        email=email,
        name="Prefix List User",
        primary_course_id=course_id,
        primary_course_name=f"Course {course_id}",
        courses=[course_id],
        created=1_700_000_000,
    )
    ddbo.movies.put_item(
        Item={
            MOVIE_ID: unique_name("movie"),
            COURSE_ID: course_id,
            USER_ID: user_id,
            CREATED_AT: Decimal("1900000000"),
            DATE_UPLOADED: Decimal("1950000000"),
        }
    )

    dynamodb = DDBO.resource()
    partial_table_name = normalized_prefix(partial_prefix) + USERS
    create_partial_users_table(dynamodb, partial_table_name)
    try:
        result = run_dbbackup("list-prefixes")
    finally:
        odbmaint.drop_dynamodb_table(
            dynamodb,
            partial_table_name,
            silent_warnings=True,
        )

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines[0].split() == ["prefix", "courses", "users", "movies", "from", "to"]
    rows = {
        parts[0]: parts
        for parts in (line.split() for line in lines[1:])
    }
    assert rows[normalized_prefix(list_prefix)] == [
        normalized_prefix(list_prefix),
        "1",
        "1",
        "1",
        "2020-09-13T12:26:40Z",
        "2031-10-17T10:40:00Z",
    ]
    assert normalized_prefix(partial_prefix) not in rows


def test_list_prefixes_can_run_aws_sso_login_and_retry(monkeypatch, capsys):
    attempts = 0

    def fake_prefix_summaries(_dynamodb):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise dbbackup.TokenRetrievalError(
                provider="sso",
                error_msg="Token has expired and refresh failed",
            )
        return [
            dbbackup.PrefixSummary(
                prefix="demo-",
                courses=2,
                users=3,
                movies=4,
                date_from=1_700_000_000,
                date_to=1_700_000_060,
            )
        ]

    commands = []

    def fake_run(command, check=False):
        commands.append((command, check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(dbbackup, "prefix_summaries", fake_prefix_summaries)
    monkeypatch.setattr(dbbackup.odb.DDBO, "resource", staticmethod(object))
    monkeypatch.setattr(dbbackup.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "stdin", io.StringIO("yes\n"))

    assert dbbackup.command_list_prefixes(object()) == 0

    captured = capsys.readouterr()
    assert commands == [(["aws", "sso", "login"], False)]
    assert "AWS SSO token retrieval failed" in captured.err
    assert "Run `aws sso login` and retry?" in captured.err
    assert captured.out.splitlines() == [
        "prefix  courses  users  movies  from                  to",
        "demo-         2      3       4  2023-11-14T22:13:20Z  2023-11-14T22:14:20Z",
    ]


def test_restore_preflight_commit_and_collision(tmp_path, prefix_tools, backup_scenario: BackupScenario):
    archive_path = tmp_path / "restore.ptb"
    target_prefix = unique_name("restore-target")
    collision_prefix = unique_name("restore-collision")

    run_dbbackup(
        "backup",
        "--table-prefix",
        backup_scenario.source_prefix,
        "--output",
        str(archive_path),
        "--course-id",
        backup_scenario.movie_course_id,
    )
    delete_s3_objects(
        backup_scenario.bucket,
        backup_scenario.active_movie_key,
        backup_scenario.deleted_movie_key,
    )

    prefix_tools["create_empty_prefix"](target_prefix)
    before_preflight = snapshot_prefix(prefix_tools, target_prefix)
    result = run_dbbackup("restore", "--table-prefix", target_prefix, str(archive_path), "--all")
    assert "preflight" in (result.stdout + result.stderr).lower()
    assert snapshot_prefix(prefix_tools, target_prefix) == before_preflight
    assert not s3_object_exists(backup_scenario.bucket, backup_scenario.active_movie_key)

    run_dbbackup("restore", "--table-prefix", target_prefix, str(archive_path), "--all", "--commit")
    target_snapshot = snapshot_prefix(prefix_tools, target_prefix)
    assert backup_scenario.owner_user_id in row_values(target_snapshot[USERS], USER_ID)
    assert backup_scenario.owner_email in row_values(target_snapshot[UNIQUE_EMAILS], EMAIL)
    assert target_snapshot[API_KEYS] == []
    assert backup_scenario.active_movie_id in row_values(target_snapshot[MOVIES], MOVIE_ID)
    assert s3_object_bytes(backup_scenario.bucket, backup_scenario.active_movie_key) == backup_scenario.active_movie_bytes

    collision_ddbo = prefix_tools["create_empty_prefix"](collision_prefix)
    make_course(collision_ddbo, backup_scenario.primary_course_id)
    make_user(
        collision_ddbo,
        user_id=odb.new_user_id(),
        email=backup_scenario.owner_email,
        name="Existing User",
        primary_course_id=backup_scenario.primary_course_id,
        primary_course_name=f"Course {backup_scenario.primary_course_id}",
        courses=[backup_scenario.primary_course_id],
    )
    before_collision = snapshot_prefix(prefix_tools, collision_prefix)
    collision = run_dbbackup(
        "restore",
        "--table-prefix",
        collision_prefix,
        str(archive_path),
        "--all",
        "--commit",
        check=False,
    )
    assert collision.returncode != 0
    assert "email" in collision.stderr.lower()
    assert snapshot_prefix(prefix_tools, collision_prefix) == before_collision


def test_inspect_and_send_restore_links_are_non_destructive_by_default(
    tmp_path,
    prefix_tools,
    backup_scenario: BackupScenario,
):
    archive_path = tmp_path / "inspect.ptb"
    target_prefix = unique_name("links-target")

    run_dbbackup(
        "backup",
        "--table-prefix",
        backup_scenario.source_prefix,
        "--output",
        str(archive_path),
        "--movie-id",
        backup_scenario.active_movie_id,
    )
    inspect_result = run_dbbackup("inspect", str(archive_path))
    inspect_output = inspect_result.stdout + inspect_result.stderr
    assert backup_scenario.source_prefix in inspect_output
    assert "movie_frames: 2" in inspect_output
    assert "movie objects: 1" in inspect_output

    verbose_result = run_dbbackup("inspect", str(archive_path), "--verbose")
    verbose_output = verbose_result.stdout + verbose_result.stderr
    assert backup_scenario.owner_email in verbose_output
    assert backup_scenario.active_movie_id in verbose_output
    assert "total frames: 2" in verbose_output
    assert "frame 0: 2 trackpoints [Apex, Ruler 10mm]" in verbose_output
    assert "frame 1: 1 trackpoint [Apex]" in verbose_output

    prefix_tools["create_empty_prefix"](target_prefix)
    run_dbbackup("restore", "--table-prefix", target_prefix, str(archive_path), "--all", "--commit")
    before_links = snapshot_prefix(prefix_tools, target_prefix)
    link_result = run_dbbackup(
        "send-restore-links",
        "--table-prefix",
        target_prefix,
        str(archive_path),
        "--all",
    )
    assert "dry" in (link_result.stdout + link_result.stderr).lower()
    assert snapshot_prefix(prefix_tools, target_prefix)[API_KEYS] == before_links[API_KEYS] == []


def test_migrate_course_preflight_and_commit(prefix_tools, backup_scenario: BackupScenario):
    before_preflight = snapshot_prefix(prefix_tools, backup_scenario.source_prefix)
    result = run_dbbackup(
        "migrate-course",
        "--table-prefix",
        backup_scenario.source_prefix,
        "--from-course-id",
        backup_scenario.movie_course_id,
        "--to-course-id",
        backup_scenario.migration_course_id,
    )
    assert "preflight" in (result.stdout + result.stderr).lower()
    assert snapshot_prefix(prefix_tools, backup_scenario.source_prefix) == before_preflight

    run_dbbackup(
        "migrate-course",
        "--table-prefix",
        backup_scenario.source_prefix,
        "--from-course-id",
        backup_scenario.movie_course_id,
        "--to-course-id",
        backup_scenario.migration_course_id,
        "--commit",
    )
    ddbo = prefix_tools["set_prefix"](backup_scenario.source_prefix)
    owner = ddbo.get_user(backup_scenario.owner_user_id)
    movie = ddbo.get_movie(backup_scenario.active_movie_id)
    enrollments = scan_table(ddbo.course_users)
    assert backup_scenario.movie_course_id not in owner["courses"]
    assert backup_scenario.migration_course_id in owner["courses"]
    assert movie[COURSE_ID] == backup_scenario.migration_course_id
    assert not movie[MOVIE_DATA_URN].startswith(f"s3://{backup_scenario.bucket}/{backup_scenario.movie_course_id}/")
    assert movie[MOVIE_DATA_URN].startswith(f"s3://{backup_scenario.bucket}/{backup_scenario.migration_course_id}/")
    assert {
        COURSE_ID: backup_scenario.migration_course_id,
        USER_ID: backup_scenario.owner_user_id,
    } in enrollments
    assert {
        COURSE_ID: backup_scenario.movie_course_id,
        USER_ID: backup_scenario.owner_user_id,
    } not in enrollments
    migrated_key = f"{backup_scenario.migration_course_id}/{backup_scenario.active_movie_id}.mov"
    assert s3_object_bytes(backup_scenario.bucket, migrated_key) == backup_scenario.active_movie_bytes
