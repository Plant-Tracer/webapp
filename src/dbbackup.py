#!/usr/bin/env python3
"""
Selective backup, restore, inspection, and migration for Plant Tracer data.
"""

# pylint: disable=too-many-lines,too-many-locals,too-many-branches,too-many-statements

import argparse
import base64
import contextlib
import copy
import getpass
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError, TokenRetrievalError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app import clogging
from app import mailer
from app import odb
from app import odbmaint
from app.constants import C, __version__
from app.odb import (
    ADMIN_FOR_COURSES,
    ADMINS_FOR_COURSE,
    COURSE_ID,
    COURSE_NAME,
    COURSE_USERS,
    COURSES,
    CREATED,
    CREATED_AT,
    DATE_UPLOADED,
    DELETED,
    EMAIL,
    FRAME_NUMBER,
    FRAME_URN,
    FRAMES,
    MOVIE_DATA_URN,
    MOVIE_ID,
    MOVIE_STATE_UPDATED_AT,
    MOVIE_TRACED_URN,
    MOVIE_ZIPFILE_URN,
    MOVIES,
    PRIMARY_COURSE_ID,
    PRIMARY_COURSE_NAME,
    TITLE,
    UNIQUE_EMAILS,
    USER_ID,
    USERS,
    USER_NAME,
)
from app.s3_presigned import parse_s3_urn, s3_client


FORMAT_VERSION = 1
MEMBER_MANIFEST = "manifest.json"
MEMBER_README = "README"
MOVIE_MEMBER_PREFIX = "movies/"
TYPE_DESERIALIZER = TypeDeserializer()
TYPE_SERIALIZER = TypeSerializer()

TABLE_MEMBER_PAIRS = (
    (USERS, "tables/users.jsonl"),
    (COURSES, "tables/courses.jsonl"),
    (COURSE_USERS, "tables/course_users.jsonl"),
    (MOVIES, "tables/movies.jsonl"),
    (FRAMES, "tables/movie_frames.jsonl"),
)
TABLE_MEMBER_BY_NAME = dict(TABLE_MEMBER_PAIRS)
TABLES_IN_RESTORE_ORDER = (COURSES, USERS, COURSE_USERS, MOVIES, FRAMES)
ROW_SORT_KEYS = {
    USERS: (USER_ID,),
    COURSES: (COURSE_ID,),
    COURSE_USERS: (COURSE_ID, USER_ID),
    MOVIES: (MOVIE_ID,),
    FRAMES: (MOVIE_ID, FRAME_NUMBER),
}
MOVIE_S3_URN_FIELDS = (MOVIE_DATA_URN, MOVIE_ZIPFILE_URN, MOVIE_TRACED_URN)
USER_DATE_FIELDS = (CREATED,)
COURSE_DATE_FIELDS = (CREATED, CREATED_AT)
MOVIE_DATE_FIELDS = (CREATED_AT, DATE_UPLOADED, MOVIE_STATE_UPDATED_AT)
LIST_PREFIX_HEADERS = ("prefix", "courses", "users", "movies", "from", "to")
LIST_PREFIX_RIGHT_ALIGNED = (False, True, True, True, False, False)
TRACKPOINTS = "trackpoints"
TRACKPOINT_LABEL = "label"
REQUIRED_PREFIX_TABLES = tuple(
    table_config[odbmaint.TableName]
    for table_config in odbmaint.TABLE_CONFIGURATIONS
)


class DbBackupError(RuntimeError):
    """Expected operator-facing failure."""


class Selection(BaseModel):
    """A backup or restore selector."""

    all_items: bool = Field(default=False, alias="all")
    course_id: str | None = None
    user_email: str | None = None
    movie_id: str | None = None

    @model_validator(mode="after")
    def validate_one_selector(self):
        selected = [
            self.all_items,
            self.course_id is not None,
            self.user_email is not None,
            self.movie_id is not None,
        ]
        if sum(1 for value in selected if value) != 1:
            raise ValueError("exactly one selection option is required")
        return self

    @property
    def label(self) -> str:
        if self.all_items:
            return "all"
        if self.course_id is not None:
            return f"course_id={self.course_id}"
        if self.user_email is not None:
            return f"user_email={self.user_email}"
        return f"movie_id={self.movie_id}"


class BackupOptions(BaseModel):
    """Backup options recorded in the manifest."""

    include_deleted: bool = False
    include_originals: bool = False


class MovieObject(BaseModel):
    """One movie object stored in a .ptb archive."""

    movie_id: str
    member_name: str
    urn: str
    bucket: str
    key: str
    size: int
    sha256: str


class MovieObjectCandidate(BaseModel):
    """A movie object that passed backup preflight."""

    movie_id: str
    urn: str
    bucket: str
    key: str
    size: int | None = None
    existing_movie_object: MovieObject | None = None
    warning: str | None = None


class BackupPreflight(BaseModel):
    """Backup preflight result."""

    movie_objects: list[MovieObjectCandidate]
    skipped_movie_ids: set[str]
    warnings: list[str]


class Manifest(BaseModel):
    """The .ptb archive manifest."""

    model_config = ConfigDict(populate_by_name=True)

    format_version: int
    app_version: str
    created_at: str
    operator: str | None = None
    source_host: str | None = None
    aws_region: str | None = None
    source_table_prefix: str
    source_s3_bucket: str | None = None
    selection: Selection
    options: BackupOptions
    table_counts: dict[str, int]
    movies: list[MovieObject]
    warnings: list[str] = Field(default_factory=list)


class ArchiveData(BaseModel):
    """A parsed .ptb archive."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    manifest: Manifest
    tables: dict[str, list[dict[str, Any]]]


class ExistingBackup(BaseModel):
    """A reusable existing backup archive."""

    path: Path
    manifest: Manifest


class BackupDataset(BaseModel):
    """Selected DynamoDB rows before writing an archive."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    users: list[dict[str, Any]] = Field(default_factory=list)
    courses: list[dict[str, Any]] = Field(default_factory=list)
    course_users: list[dict[str, Any]] = Field(default_factory=list)
    movies: list[dict[str, Any]] = Field(default_factory=list)
    frames: list[dict[str, Any]] = Field(default_factory=list)

    def table_rows(self) -> dict[str, list[dict[str, Any]]]:
        return {
            USERS: self.users,
            COURSES: self.courses,
            COURSE_USERS: self.course_users,
            MOVIES: self.movies,
            FRAMES: self.frames,
        }


class PrefixSummary(BaseModel):
    """One complete DynamoDB table-prefix summary."""

    prefix: str
    courses: int
    users: int
    movies: int
    date_from: int | None = None
    date_to: int | None = None


class TimestampRange(BaseModel):
    """A compact inclusive range of Unix epoch seconds."""

    date_from: int | None = None
    date_to: int | None = None

    def include(self, value: Any) -> None:
        epoch = epoch_seconds(value)
        if epoch is None:
            return
        if self.date_from is None or epoch < self.date_from:
            self.date_from = epoch
        if self.date_to is None or epoch > self.date_to:
            self.date_to = epoch

    def include_range(self, other: "TimestampRange") -> None:
        self.include(other.date_from)
        self.include(other.date_to)


class TableDateSummary(BaseModel):
    """Count and timestamp range for a table scan."""

    count: int = 0
    date_range: TimestampRange


def encode_attribute_value(attribute_value: dict[str, Any]) -> dict[str, Any]:
    """Make a DynamoDB AttributeValue JSON-serializable."""
    if "B" in attribute_value:
        return {"B": base64.b64encode(attribute_value["B"]).decode("ascii")}
    if "BS" in attribute_value:
        return {
            "BS": [
                base64.b64encode(value).decode("ascii")
                for value in attribute_value["BS"]
            ]
        }
    if "L" in attribute_value:
        return {"L": [encode_attribute_value(value) for value in attribute_value["L"]]}
    if "M" in attribute_value:
        return {
            "M": {
                key: encode_attribute_value(value)
                for key, value in attribute_value["M"].items()
            }
        }
    return attribute_value


def decode_attribute_value(attribute_value: dict[str, Any]) -> dict[str, Any]:
    """Convert archived DynamoDB AttributeValue JSON back for boto3."""
    if "B" in attribute_value:
        return {"B": base64.b64decode(attribute_value["B"])}
    if "BS" in attribute_value:
        return {
            "BS": [
                base64.b64decode(value)
                for value in attribute_value["BS"]
            ]
        }
    if "L" in attribute_value:
        return {"L": [decode_attribute_value(value) for value in attribute_value["L"]]}
    if "M" in attribute_value:
        return {
            "M": {
                key: decode_attribute_value(value)
                for key, value in attribute_value["M"].items()
            }
        }
    return attribute_value


def encode_item(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a DynamoDB item to DynamoDB AttributeValue JSON."""
    return {
        key: encode_attribute_value(TYPE_SERIALIZER.serialize(value))
        for key, value in row.items()
    }


def decode_item(row: dict[str, Any]) -> dict[str, Any]:
    """Convert DynamoDB AttributeValue JSON to a boto3 resource item."""
    return {
        key: TYPE_DESERIALIZER.deserialize(decode_attribute_value(value))
        for key, value in row.items()
    }


def json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def normalized_table_prefix(table_prefix: str | None) -> str:
    return (table_prefix.rstrip("-") + "-") if table_prefix else ""


def configure_table_prefix(table_prefix: str) -> None:
    os.environ[C.DYNAMODB_TABLE_PREFIX] = table_prefix
    setattr(odb.DDBO, "_instance", None)


def table_for_name(ddbo, table_name: str):
    tables = {
        USERS: ddbo.users,
        UNIQUE_EMAILS: ddbo.unique_emails,
        COURSES: ddbo.courses,
        COURSE_USERS: ddbo.course_users,
        MOVIES: ddbo.movies,
        FRAMES: ddbo.movie_frames,
    }
    return tables[table_name]


def scan_all(table) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    scan_kwargs: dict[str, Any] = {}
    while True:
        response = table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if last_key is None:
            return items
        scan_kwargs["ExclusiveStartKey"] = last_key


def query_all(table, **query_kwargs) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    while True:
        response = table.query(**query_kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if last_key is None:
            return items
        query_kwargs["ExclusiveStartKey"] = last_key


def list_dynamodb_table_names(dynamodb) -> list[str]:
    table_names: list[str] = []
    list_kwargs: dict[str, Any] = {}
    while True:
        response = dynamodb.meta.client.list_tables(**list_kwargs)
        table_names.extend(response.get("TableNames", []))
        last_table_name = response.get("LastEvaluatedTableName")
        if last_table_name is None:
            return sorted(table_names)
        list_kwargs["ExclusiveStartTableName"] = last_table_name


def prefix_for_table_name(table_name: str, base_table_name: str) -> str | None:
    if table_name == base_table_name:
        return ""
    if not table_name.endswith(base_table_name):
        return None
    prefix = table_name[: -len(base_table_name)]
    if prefix.endswith("-"):
        return prefix
    return None


def complete_prefixes(table_names: list[str]) -> list[str]:
    tables_by_prefix: dict[str, set[str]] = {}
    for table_name in table_names:
        for base_table_name in REQUIRED_PREFIX_TABLES:
            prefix = prefix_for_table_name(table_name, base_table_name)
            if prefix is not None:
                tables_by_prefix.setdefault(prefix, set()).add(base_table_name)

    required_tables = set(REQUIRED_PREFIX_TABLES)
    return sorted(
        prefix
        for prefix, base_table_names in tables_by_prefix.items()
        if base_table_names >= required_tables
    )


def epoch_seconds(value: Any) -> int | None:
    """Return a sane Unix timestamp, or None for absent/non-timestamp values."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        try:
            epoch = int(value)
        except (OverflowError, ValueError):
            return None
    elif isinstance(value, int):
        epoch = value
    elif isinstance(value, str):
        try:
            epoch = int(Decimal(value.strip()))
        except (ArithmeticError, ValueError):
            return None
    else:
        return None
    if epoch <= 0:
        return None
    return epoch


def date_projection_kwargs(date_fields: tuple[str, ...]) -> dict[str, Any]:
    expression_names = {
        f"#date{i}": field_name
        for i, field_name in enumerate(date_fields)
    }
    return {
        "ProjectionExpression": ", ".join(expression_names),
        "ExpressionAttributeNames": expression_names,
    }


def summarize_table_dates(table, date_fields: tuple[str, ...]) -> TableDateSummary:
    summary = TableDateSummary(date_range=TimestampRange())
    scan_kwargs: dict[str, Any] = {
        "ConsistentRead": True,
        **date_projection_kwargs(date_fields),
    }
    while True:
        response = table.scan(**scan_kwargs)
        summary.count += int(response["Count"])
        for item in response.get("Items", []):
            for field_name in date_fields:
                summary.date_range.include(item.get(field_name))
        last_key = response.get("LastEvaluatedKey")
        if last_key is None:
            return summary
        scan_kwargs["ExclusiveStartKey"] = last_key


def format_epoch_seconds(epoch: int | None) -> str:
    if epoch is None:
        return "-"
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def list_prefix_row(summary: PrefixSummary) -> tuple[str, str, str, str, str, str]:
    prefix = summary.prefix if summary.prefix else "(none)"
    return (
        prefix,
        str(summary.courses),
        str(summary.users),
        str(summary.movies),
        format_epoch_seconds(summary.date_from),
        format_epoch_seconds(summary.date_to),
    )


def format_list_prefix_row(
    row: tuple[str, ...],
    widths: tuple[int, ...],
) -> str:
    cells = []
    for cell, width, right_aligned in zip(row, widths, LIST_PREFIX_RIGHT_ALIGNED):
        cells.append(cell.rjust(width) if right_aligned else cell.ljust(width))
    return "  ".join(cells).rstrip()


def format_list_prefixes(summaries: list[PrefixSummary]) -> list[str]:
    rows = [LIST_PREFIX_HEADERS] + [list_prefix_row(summary) for summary in summaries]
    widths = tuple(
        max(len(row[index]) for row in rows)
        for index in range(len(LIST_PREFIX_HEADERS))
    )
    return [format_list_prefix_row(row, widths) for row in rows]


def prefix_summaries(dynamodb) -> list[PrefixSummary]:
    summaries: list[PrefixSummary] = []
    for prefix in complete_prefixes(list_dynamodb_table_names(dynamodb)):
        course_summary = summarize_table_dates(
            dynamodb.Table(prefix + COURSES),
            COURSE_DATE_FIELDS,
        )
        user_summary = summarize_table_dates(
            dynamodb.Table(prefix + USERS),
            USER_DATE_FIELDS,
        )
        movie_summary = summarize_table_dates(
            dynamodb.Table(prefix + MOVIES),
            MOVIE_DATE_FIELDS,
        )
        date_range = TimestampRange()
        date_range.include_range(course_summary.date_range)
        date_range.include_range(user_summary.date_range)
        date_range.include_range(movie_summary.date_range)
        summaries.append(
            PrefixSummary(
                prefix=prefix,
                courses=course_summary.count,
                users=user_summary.count,
                movies=movie_summary.count,
                date_from=date_range.date_from,
                date_to=date_range.date_to,
            )
        )
    return summaries


def prompt_run_aws_sso_login(exc: TokenRetrievalError) -> bool:
    print(f"AWS SSO token retrieval failed: {exc}", file=sys.stderr)
    print("Run `aws sso login` and retry? [y/N] ", end="", file=sys.stderr, flush=True)
    answer = sys.stdin.readline().strip().lower()
    return answer in ("y", "yes")


def run_aws_sso_login() -> None:
    try:
        result = subprocess.run(["aws", "sso", "login"], check=False)
    except FileNotFoundError as exc:
        raise DbBackupError("cannot run `aws sso login`: aws command not found") from exc
    if result.returncode != 0:
        raise DbBackupError(
            f"`aws sso login` failed with exit status {result.returncode}"
        )


def prefix_summaries_with_sso_retry() -> list[PrefixSummary]:
    try:
        return prefix_summaries(odb.DDBO.resource())
    except TokenRetrievalError as exc:
        if not prompt_run_aws_sso_login(exc):
            raise DbBackupError(
                "AWS SSO token retrieval failed; run `aws sso login` and retry"
            ) from exc
    run_aws_sso_login()
    return prefix_summaries(odb.DDBO.resource())


def command_list_prefixes(_args) -> int:
    summaries = prefix_summaries_with_sso_retry()
    for line in format_list_prefixes(summaries):
        print(line)
    return 0


def sort_value(value: Any) -> str | int:
    if isinstance(value, Decimal):
        return int(value)
    return str(value)


def sort_rows(table_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sort_keys = ROW_SORT_KEYS[table_name]
    return sorted(rows, key=lambda row: tuple(sort_value(row.get(key, "")) for key in sort_keys))


def display_value(value: Any) -> str:
    """Return a compact operator-facing value."""
    if value is None:
        return "-"
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return str(int(value))
        return str(value)
    return str(value)


def short_value(value: Any, *, limit: int = 64) -> str:
    text = display_value(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def selected_row_ids(rows: list[dict[str, Any]], key: str) -> set[str]:
    return {row[key] for row in rows}


def get_course_user(ddbo, course_id: str, user_id: str) -> dict[str, Any] | None:
    response = ddbo.course_users.get_item(
        Key={COURSE_ID: course_id, USER_ID: user_id},
        ConsistentRead=True,
    )
    return response.get("Item")


def get_movie_frames(ddbo, movie_id: str) -> list[dict[str, Any]]:
    return query_all(
        ddbo.movie_frames,
        KeyConditionExpression=Key(MOVIE_ID).eq(movie_id),
        ConsistentRead=True,
    )


def is_selected_movie(movie: dict[str, Any], *, include_deleted: bool) -> bool:
    return include_deleted or int(movie.get(DELETED, 0) or 0) == 0


def sanitized_movie_row(movie: dict[str, Any]) -> dict[str, Any]:
    row = copy.deepcopy(movie)
    row[MOVIE_ZIPFILE_URN] = None
    row[MOVIE_TRACED_URN] = None
    return row


def add_row_by_key(
        rows_by_key: dict[Any, dict[str, Any]],
        row: dict[str, Any] | None,
        *keys: str) -> None:
    if row is None:
        return
    rows_by_key[tuple(row[key] for key in keys)] = row


def build_backup_dataset(ddbo, selection: Selection, *, include_deleted: bool) -> BackupDataset:
    users_by_id: dict[Any, dict[str, Any]] = {}
    courses_by_id: dict[Any, dict[str, Any]] = {}
    course_users_by_key: dict[Any, dict[str, Any]] = {}
    movies_by_id: dict[Any, dict[str, Any]] = {}
    frames_by_key: dict[Any, dict[str, Any]] = {}

    def add_user(user_id: str) -> None:
        add_row_by_key(users_by_id, ddbo.get_user(user_id), USER_ID)

    def add_course(course_id: str) -> None:
        add_row_by_key(courses_by_id, ddbo.get_course(course_id), COURSE_ID)

    def add_course_user(course_id: str, user_id: str) -> None:
        add_row_by_key(
            course_users_by_key,
            get_course_user(ddbo, course_id, user_id),
            COURSE_ID,
            USER_ID,
        )

    def add_movie(movie: dict[str, Any]) -> None:
        if not is_selected_movie(movie, include_deleted=include_deleted):
            return
        add_row_by_key(movies_by_id, sanitized_movie_row(movie), MOVIE_ID)
        for frame in get_movie_frames(ddbo, movie[MOVIE_ID]):
            add_row_by_key(frames_by_key, frame, MOVIE_ID, FRAME_NUMBER)

    if selection.all_items:
        for user in scan_all(ddbo.users):
            add_row_by_key(users_by_id, user, USER_ID)
        for course in scan_all(ddbo.courses):
            add_row_by_key(courses_by_id, course, COURSE_ID)
        for course_user in scan_all(ddbo.course_users):
            add_row_by_key(course_users_by_key, course_user, COURSE_ID, USER_ID)
        for movie in scan_all(ddbo.movies):
            add_movie(movie)
    elif selection.course_id is not None:
        add_course(selection.course_id)
        course_users = query_all(
            ddbo.course_users,
            KeyConditionExpression=Key(COURSE_ID).eq(selection.course_id),
            ConsistentRead=True,
        )
        for course_user in course_users:
            add_row_by_key(course_users_by_key, course_user, COURSE_ID, USER_ID)
            add_user(course_user[USER_ID])
        for movie in ddbo.get_movies_for_course_id(selection.course_id):
            add_user(movie[USER_ID])
            add_movie(movie)
    elif selection.user_email is not None:
        user = ddbo.get_user_email(selection.user_email)
        add_row_by_key(users_by_id, user, USER_ID)
        user_movies = [
            movie
            for movie in ddbo.get_movies_for_user_id(user[USER_ID])
            if is_selected_movie(movie, include_deleted=include_deleted)
        ]
        course_ids = {movie[COURSE_ID] for movie in user_movies}
        if user.get(PRIMARY_COURSE_ID):
            course_ids.add(user[PRIMARY_COURSE_ID])
        for course_id in course_ids:
            add_course(course_id)
            add_course_user(course_id, user[USER_ID])
        for movie in user_movies:
            add_movie(movie)
    elif selection.movie_id is not None:
        movie = ddbo.get_movie(selection.movie_id)
        if not is_selected_movie(movie, include_deleted=include_deleted):
            raise DbBackupError(f"movie {selection.movie_id} is deleted; use --include-deleted")
        add_user(movie[USER_ID])
        add_course(movie[COURSE_ID])
        add_course_user(movie[COURSE_ID], movie[USER_ID])
        add_movie(movie)

    return BackupDataset(
        users=sort_rows(USERS, list(users_by_id.values())),
        courses=sort_rows(COURSES, list(courses_by_id.values())),
        course_users=sort_rows(COURSE_USERS, list(course_users_by_key.values())),
        movies=sort_rows(MOVIES, list(movies_by_id.values())),
        frames=sort_rows(FRAMES, list(frames_by_key.values())),
    )


def backup_readme() -> str:
    return (
        "Plant Tracer Backup Archive\n"
        "===========================\n\n"
        "This archive contains student data, course data, movie metadata, "
        "trackpoint annotations, and movie files. It is not password protected.\n\n"
        "Store and transmit this file as sensitive data. It can be restored into "
        "a Plant Tracer deployment by an operator with suitable DynamoDB and S3 "
        "credentials.\n"
    )


def write_table_jsonl(
        archive: zipfile.ZipFile,
        table_name: str,
        rows: list[dict[str, Any]]) -> None:
    body = "".join(json_dumps(encode_item(row)) + "\n" for row in rows)
    archive.writestr(TABLE_MEMBER_BY_NAME[table_name], body)


def client_error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


def is_missing_s3_object_error(exc: ClientError) -> bool:
    status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return status_code == 404 or client_error_code(exc) in {"404", "NoSuchKey", "NotFound"}


def read_archive_manifest(path: str | Path) -> Manifest:
    try:
        with zipfile.ZipFile(path) as archive:
            return Manifest.model_validate(json.loads(archive.read(MEMBER_MANIFEST)))
    except KeyError as exc:
        raise DbBackupError(f"archive is missing {MEMBER_MANIFEST}") from exc
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise DbBackupError(f"cannot read backup archive {path}: {exc}") from exc


def existing_backup_for_output(output: Path, table_prefix: str) -> ExistingBackup | None:
    if not output.exists():
        return None
    manifest = read_archive_manifest(output)
    output_prefix = normalized_table_prefix(manifest.source_table_prefix)
    requested_prefix = normalized_table_prefix(table_prefix)
    if output_prefix != requested_prefix:
        raise DbBackupError(
            f"{output} already contains a backup for DynamoDB table prefix "
            f"{output_prefix!r}, not {requested_prefix!r}; refusing to overwrite"
        )
    return ExistingBackup(path=output, manifest=manifest)


def existing_movie_object_for_candidate(
        existing_backup: ExistingBackup | None,
        bucket: str,
        key: str) -> MovieObject | None:
    if existing_backup is None:
        return None
    for movie_object in existing_backup.manifest.movies:
        if movie_object.bucket == bucket and movie_object.key == key:
            return movie_object
    return None


def movie_object_candidate(
        movie: dict[str, Any],
        existing_backup: ExistingBackup | None = None) -> MovieObjectCandidate | str:
    movie_id = movie[MOVIE_ID]
    urn = movie.get(MOVIE_DATA_URN)
    if not urn:
        return f"movie {movie_id} has no {MOVIE_DATA_URN}; skipping movie"
    try:
        bucket, key = parse_s3_urn(urn=urn)
        existing_movie_object = existing_movie_object_for_candidate(
            existing_backup,
            bucket,
            key,
        )
        response = s3_client().head_object(Bucket=bucket, Key=key)
    except (RuntimeError, ValueError) as exc:
        return f"movie {movie_id} has invalid {MOVIE_DATA_URN} {urn}: {exc}; skipping movie"
    except ClientError as exc:
        if is_missing_s3_object_error(exc):
            existing_movie_object = existing_movie_object_for_candidate(
                existing_backup,
                bucket,
                key,
            )
            if existing_movie_object is not None:
                return MovieObjectCandidate(
                    movie_id=movie_id,
                    urn=urn,
                    bucket=bucket,
                    key=key,
                    size=existing_movie_object.size,
                    existing_movie_object=existing_movie_object,
                    warning=(
                        f"movie {movie_id} object {urn} is missing in S3; "
                        "reusing existing archive copy"
                    ),
                )
            return f"movie {movie_id} object {urn} does not exist; skipping movie"
        raise DbBackupError(f"cannot check movie object {urn}: {exc}") from exc
    return MovieObjectCandidate(
        movie_id=movie_id,
        urn=urn,
        bucket=bucket,
        key=key,
        size=response.get("ContentLength"),
        existing_movie_object=existing_movie_object,
    )


def preflight_movie_objects(
        movies: list[dict[str, Any]],
        existing_backup: ExistingBackup | None = None) -> BackupPreflight:
    preflight = BackupPreflight(
        movie_objects=[],
        skipped_movie_ids=set(),
        warnings=[],
    )
    for movie in movies:
        candidate = movie_object_candidate(movie, existing_backup)
        if isinstance(candidate, str):
            preflight.skipped_movie_ids.add(movie[MOVIE_ID])
            preflight.warnings.append(candidate)
        else:
            preflight.movie_objects.append(candidate)
            if candidate.warning is not None:
                preflight.warnings.append(candidate.warning)
    return preflight


def backup_dataset_without_movies(
        dataset: BackupDataset,
        skipped_movie_ids: set[str]) -> BackupDataset:
    if not skipped_movie_ids:
        return dataset
    return BackupDataset(
        users=dataset.users,
        courses=dataset.courses,
        course_users=dataset.course_users,
        movies=[
            movie for movie in dataset.movies
            if movie[MOVIE_ID] not in skipped_movie_ids
        ],
        frames=[
            frame for frame in dataset.frames
            if frame[MOVIE_ID] not in skipped_movie_ids
        ],
    )


def read_existing_movie_object(
        candidate: MovieObjectCandidate,
        existing_archive: zipfile.ZipFile | None) -> bytes:
    movie_object = candidate.existing_movie_object
    if movie_object is None:
        raise DbBackupError(f"movie {candidate.movie_id} has no reusable archive object")
    if existing_archive is None:
        raise DbBackupError(f"movie {candidate.movie_id} cannot reuse an unopened archive")
    try:
        body = existing_archive.read(movie_object.member_name)
    except KeyError as exc:
        raise DbBackupError(
            f"existing archive is missing {movie_object.member_name}"
        ) from exc
    digest = hashlib.sha256(body).hexdigest()
    if digest != movie_object.sha256:
        raise DbBackupError(
            f"checksum mismatch for existing archive member {movie_object.member_name}: "
            f"{digest} != {movie_object.sha256}"
        )
    return body


def read_movie_object(
        candidate: MovieObjectCandidate,
        existing_archive: zipfile.ZipFile | None = None) -> bytes:
    if candidate.existing_movie_object is not None:
        return read_existing_movie_object(candidate, existing_archive)
    try:
        return s3_client().get_object(
            Bucket=candidate.bucket,
            Key=candidate.key,
        )["Body"].read()
    except ClientError as exc:
        raise DbBackupError(f"cannot read movie object {candidate.urn}: {exc}") from exc


def make_manifest(
        *,
        args,
        selection: Selection,
        options: BackupOptions,
        dataset: BackupDataset,
        movie_objects: list[MovieObject],
        warnings: list[str]) -> Manifest:
    table_counts = {
        table_name: len(rows)
        for table_name, rows in dataset.table_rows().items()
    }
    return Manifest(
        format_version=FORMAT_VERSION,
        app_version=__version__,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        operator=getpass.getuser(),
        source_host=socket.gethostname(),
        aws_region=os.environ.get(C.AWS_REGION),
        source_table_prefix=normalized_table_prefix(args.table_prefix),
        source_s3_bucket=os.environ.get(C.PLANTTRACER_S3_BUCKET),
        selection=selection,
        options=options,
        table_counts=table_counts,
        movies=movie_objects,
        warnings=warnings,
    )


def backup_status(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def backup_archive_temp_path(output: Path) -> Path:
    return output.with_name(f".{output.name}.tmp")


def command_backup(args) -> int:
    configure_table_prefix(args.table_prefix)
    selection = selection_from_args(args, default_all=True)
    options = BackupOptions(include_deleted=args.include_deleted)
    output = Path(args.output)
    backup_status(f"backup: checking output archive {output}")
    existing_backup = existing_backup_for_output(output, args.table_prefix)
    ddbo = odb.DDBO()
    backup_status(f"backup: examining DynamoDB tables for {selection.label}")
    dataset = build_backup_dataset(ddbo, selection, include_deleted=args.include_deleted)
    backup_status(f"backup: preflight checking {len(dataset.movies)} movie objects")
    preflight = preflight_movie_objects(dataset.movies, existing_backup)
    warnings = [
        "Backup may not be transactionally consistent if the application is active."
    ] + preflight.warnings
    for warning in preflight.warnings:
        backup_status(f"WARNING: {warning}")
    dataset = backup_dataset_without_movies(dataset, preflight.skipped_movie_ids)
    movie_objects: list[MovieObject] = []

    temp_output = backup_archive_temp_path(output)
    backup_status(f"backup: creating archive {output}")
    try:
        with contextlib.ExitStack() as stack, zipfile.ZipFile(
                temp_output,
                mode="w",
                compression=zipfile.ZIP_DEFLATED) as archive:
            existing_archive = None
            if existing_backup is not None:
                existing_archive = stack.enter_context(zipfile.ZipFile(existing_backup.path))
            archive.writestr(MEMBER_README, backup_readme())
            for table_name, rows in dataset.table_rows().items():
                write_table_jsonl(archive, table_name, rows)

            for candidate in preflight.movie_objects:
                if candidate.existing_movie_object is not None:
                    backup_status(f"backup: reusing archived movie object {candidate.movie_id}")
                else:
                    backup_status(f"backup: downloading movie object {candidate.movie_id}")
                body = read_movie_object(candidate, existing_archive)
                member_name = f"{MOVIE_MEMBER_PREFIX}{candidate.movie_id}.mp4"
                digest = hashlib.sha256(body).hexdigest()
                archive.writestr(member_name, body)
                movie_objects.append(
                    MovieObject(
                        movie_id=candidate.movie_id,
                        member_name=member_name,
                        urn=candidate.urn,
                        bucket=candidate.bucket,
                        key=candidate.key,
                        size=len(body),
                        sha256=digest,
                    )
                )

            manifest = make_manifest(
                args=args,
                selection=selection,
                options=options,
                dataset=dataset,
                movie_objects=movie_objects,
                warnings=warnings,
            )
            archive.writestr(
                MEMBER_MANIFEST,
                json.dumps(manifest.model_dump(by_alias=True), indent=2, sort_keys=True) + "\n",
            )
        temp_output.replace(output)
    except Exception:
        temp_output.unlink(missing_ok=True)
        raise

    print(
        f"wrote {output}: {len(dataset.users)} users, {len(dataset.courses)} courses, "
        f"{len(dataset.movies)} movies, {len(movie_objects)} movie objects"
    )
    return 0


def read_archive(path: str | Path) -> ArchiveData:
    tables: dict[str, list[dict[str, Any]]] = {}
    with zipfile.ZipFile(path) as archive:
        manifest = Manifest.model_validate(json.loads(archive.read(MEMBER_MANIFEST)))
        if manifest.format_version != FORMAT_VERSION:
            raise DbBackupError(
                f"unsupported backup format {manifest.format_version}; expected {FORMAT_VERSION}"
            )
        for table_name, member_name in TABLE_MEMBER_BY_NAME.items():
            try:
                body = archive.read(member_name).decode("utf-8")
            except KeyError as exc:
                raise DbBackupError(f"archive is missing {member_name}") from exc
            tables[table_name] = [
                decode_item(json.loads(line))
                for line in body.splitlines()
                if line.strip()
            ]
    return ArchiveData(manifest=manifest, tables=tables)


def selected_archive_data(data: ArchiveData, selection: Selection) -> ArchiveData:
    if selection.all_items:
        return data

    users = data.tables[USERS]
    courses = data.tables[COURSES]
    course_users = data.tables[COURSE_USERS]
    movies = data.tables[MOVIES]
    frames = data.tables[FRAMES]
    selected_user_ids: set[str] = set()
    selected_course_ids: set[str] = set()
    selected_movie_ids: set[str] = set()

    if selection.course_id is not None:
        selected_course_ids.add(selection.course_id)
        selected_course_users = [
            row for row in course_users if row[COURSE_ID] == selection.course_id
        ]
        selected_user_ids.update(row[USER_ID] for row in selected_course_users)
        selected_movie_ids.update(
            row[MOVIE_ID] for row in movies if row[COURSE_ID] == selection.course_id
        )
    elif selection.user_email is not None:
        selected_users = [row for row in users if row[EMAIL] == selection.user_email]
        if not selected_users:
            raise DbBackupError(f"archive has no user with email {selection.user_email}")
        selected_user_ids.add(selected_users[0][USER_ID])
        selected_movie_ids.update(
            row[MOVIE_ID] for row in movies if row[USER_ID] in selected_user_ids
        )
        selected_course_ids.update(
            row[COURSE_ID] for row in movies if row[MOVIE_ID] in selected_movie_ids
        )
        if selected_users[0].get(PRIMARY_COURSE_ID):
            selected_course_ids.add(selected_users[0][PRIMARY_COURSE_ID])
    elif selection.movie_id is not None:
        selected_movies = [row for row in movies if row[MOVIE_ID] == selection.movie_id]
        if not selected_movies:
            raise DbBackupError(f"archive has no movie {selection.movie_id}")
        movie = selected_movies[0]
        selected_movie_ids.add(movie[MOVIE_ID])
        selected_user_ids.add(movie[USER_ID])
        selected_course_ids.add(movie[COURSE_ID])

    if not selected_user_ids:
        selected_user_ids.update(
            row[USER_ID] for row in movies if row[MOVIE_ID] in selected_movie_ids
        )
    selected_course_ids.update(
        row[COURSE_ID] for row in movies if row[MOVIE_ID] in selected_movie_ids
    )

    filtered_tables = {
        USERS: [row for row in users if row[USER_ID] in selected_user_ids],
        COURSES: [row for row in courses if row[COURSE_ID] in selected_course_ids],
        COURSE_USERS: [
            row
            for row in course_users
            if row[COURSE_ID] in selected_course_ids and row[USER_ID] in selected_user_ids
        ],
        MOVIES: [row for row in movies if row[MOVIE_ID] in selected_movie_ids],
        FRAMES: [row for row in frames if row[MOVIE_ID] in selected_movie_ids],
    }
    manifest = data.manifest.model_copy(
        update={
            "movies": [
                movie_object
                for movie_object in data.manifest.movies
                if movie_object.movie_id in selected_movie_ids
            ]
        }
    )
    return ArchiveData(manifest=manifest, tables=filtered_tables)


def print_archive_summary(data: ArchiveData, *, stream) -> None:
    manifest = data.manifest
    print(f"format version: {manifest.format_version}", file=stream)
    print(f"created at: {manifest.created_at}", file=stream)
    print(f"application version: {manifest.app_version}", file=stream)
    print(f"source table prefix: {manifest.source_table_prefix}", file=stream)
    print(f"source S3 bucket: {manifest.source_s3_bucket}", file=stream)
    print(f"selection: {manifest.selection.label}", file=stream)
    print("tables:", file=stream)
    for table_name in TABLE_MEMBER_BY_NAME:
        count = len(data.tables.get(table_name, []))
        print(f"  {table_name}: {count}", file=stream)
    total_movie_bytes = sum(movie_object.size for movie_object in manifest.movies)
    print(f"movie objects: {len(manifest.movies)}", file=stream)
    print(f"movie object bytes: {total_movie_bytes}", file=stream)


def print_user_summaries(users: list[dict[str, Any]], *, stream) -> None:
    print("users:", file=stream)
    for user in sort_rows(USERS, users):
        print(
            f"  {user[USER_ID]} email={short_value(user.get(EMAIL))} "
            f"name={short_value(user.get(USER_NAME))} "
            f"primary_course_id={short_value(user.get(PRIMARY_COURSE_ID))}",
            file=stream,
        )


def print_course_summaries(courses: list[dict[str, Any]], *, stream) -> None:
    print("courses:", file=stream)
    for course in sort_rows(COURSES, courses):
        print(
            f"  {course[COURSE_ID]} name={short_value(course.get(COURSE_NAME))}",
            file=stream,
        )


def print_course_user_summaries(course_users: list[dict[str, Any]], *, stream) -> None:
    print("course users:", file=stream)
    for course_user in sort_rows(COURSE_USERS, course_users):
        print(
            f"  course_id={course_user[COURSE_ID]} user_id={course_user[USER_ID]}",
            file=stream,
        )


def print_movie_summaries(movies: list[dict[str, Any]], *, stream) -> None:
    print("movies:", file=stream)
    for movie in sort_rows(MOVIES, movies):
        print(
            f"  {movie[MOVIE_ID]} title={short_value(movie.get(TITLE))} "
            f"course_id={short_value(movie.get(COURSE_ID))} "
            f"user_id={short_value(movie.get(USER_ID))} "
            f"deleted={display_value(movie.get(DELETED))}",
            file=stream,
        )


def frame_number(frame: dict[str, Any]) -> int:
    return int(frame[FRAME_NUMBER])


def frame_trackpoint_summary(frame: dict[str, Any]) -> tuple[int, tuple[str, ...]]:
    trackpoints = frame.get(TRACKPOINTS, [])
    labels = tuple(
        sorted(
            str(trackpoint[TRACKPOINT_LABEL])
            for trackpoint in trackpoints
            if trackpoint.get(TRACKPOINT_LABEL)
        )
    )
    return len(trackpoints), labels


def frame_range_text(start: int, end: int) -> str:
    if start == end:
        return f"frame {start}"
    return f"frames {start}-{end}"


def label_list_text(labels: tuple[str, ...]) -> str:
    if not labels:
        return "[]"
    return "[" + ", ".join(labels) + "]"


def print_frame_trackpoint_summaries(frames: list[dict[str, Any]], *, stream) -> None:
    print("frame trackpoints:", file=stream)
    print(f"  total frames: {len(frames)}", file=stream)
    frames_by_movie: dict[str, list[dict[str, Any]]] = {}
    for frame in frames:
        frames_by_movie.setdefault(frame[MOVIE_ID], []).append(frame)

    for movie_id in sorted(frames_by_movie):
        movie_frames = sorted(frames_by_movie[movie_id], key=frame_number)
        range_start = frame_number(movie_frames[0])
        range_end = range_start
        last_summary = frame_trackpoint_summary(movie_frames[0])
        for frame in movie_frames[1:]:
            current_frame_number = frame_number(frame)
            current_summary = frame_trackpoint_summary(frame)
            if current_frame_number == range_end + 1 and current_summary == last_summary:
                range_end = current_frame_number
                continue
            print_frame_trackpoint_range(
                movie_id,
                range_start,
                range_end,
                last_summary,
                stream=stream,
            )
            range_start = current_frame_number
            range_end = current_frame_number
            last_summary = current_summary
        print_frame_trackpoint_range(
            movie_id,
            range_start,
            range_end,
            last_summary,
            stream=stream,
        )


def print_frame_trackpoint_range(
        movie_id: str,
        range_start: int,
        range_end: int,
        summary: tuple[int, tuple[str, ...]],
        *,
        stream) -> None:
    trackpoint_count, labels = summary
    noun = "trackpoint" if trackpoint_count == 1 else "trackpoints"
    print(
        f"  movie_id={movie_id} {frame_range_text(range_start, range_end)}: "
        f"{trackpoint_count} {noun} {label_list_text(labels)}",
        file=stream,
    )


def print_movie_object_summaries(movie_objects: list[MovieObject], *, stream) -> None:
    print("movie objects:", file=stream)
    for movie_object in sorted(movie_objects, key=lambda item: item.movie_id):
        print(
            f"  {movie_object.movie_id} member={movie_object.member_name} "
            f"bytes={movie_object.size} sha256={movie_object.sha256}",
            file=stream,
        )


def print_archive_verbose(data: ArchiveData, *, stream) -> None:
    print_archive_summary(data, stream=stream)
    print_user_summaries(data.tables[USERS], stream=stream)
    print_course_summaries(data.tables[COURSES], stream=stream)
    print_course_user_summaries(data.tables[COURSE_USERS], stream=stream)
    print_movie_summaries(data.tables[MOVIES], stream=stream)
    print_movie_object_summaries(data.manifest.movies, stream=stream)
    print_frame_trackpoint_summaries(data.tables[FRAMES], stream=stream)


def command_inspect(args) -> int:
    data = read_archive(args.archive)
    if args.verbose:
        print_archive_verbose(data, stream=sys.stdout)
    else:
        print_archive_summary(data, stream=sys.stdout)
    return 0


def find_email_collisions(ddbo, users: list[dict[str, Any]]) -> list[str]:
    collisions: list[str] = []
    for user in users:
        try:
            ddbo.get_user_email(user[EMAIL])
            collisions.append(user[EMAIL])
        except odb.InvalidUser_Email:
            continue
    return sorted(set(collisions))


def target_bucket() -> str:
    bucket = os.environ.get(C.PLANTTRACER_S3_BUCKET)
    if not bucket:
        raise DbBackupError(f"{C.PLANTTRACER_S3_BUCKET} is not set")
    return bucket


def rewrite_movie_rows_for_target_bucket(
        rows: list[dict[str, Any]],
        movie_objects: list[MovieObject]) -> list[dict[str, Any]]:
    bucket = target_bucket()
    object_by_movie_id = {movie.movie_id: movie for movie in movie_objects}
    rewritten: list[dict[str, Any]] = []
    for row in rows:
        new_row = copy.deepcopy(row)
        movie_object = object_by_movie_id.get(row[MOVIE_ID])
        if movie_object is not None and new_row.get(MOVIE_DATA_URN):
            new_row[MOVIE_DATA_URN] = f"s3://{bucket}/{movie_object.key}"
        rewritten.append(new_row)
    return rewritten


def write_rows(table, rows: list[dict[str, Any]]) -> None:
    with table.batch_writer() as batch:
        for row in rows:
            batch.put_item(Item=row)


def restore_movie_objects(archive_path: str | Path, movie_objects: list[MovieObject]) -> None:
    bucket = target_bucket()
    with zipfile.ZipFile(archive_path) as archive:
        for movie_object in movie_objects:
            body = archive.read(movie_object.member_name)
            digest = hashlib.sha256(body).hexdigest()
            if digest != movie_object.sha256:
                raise DbBackupError(
                    f"checksum mismatch for {movie_object.member_name}: "
                    f"{digest} != {movie_object.sha256}"
                )
            s3_client().put_object(Bucket=bucket, Key=movie_object.key, Body=body)


def restore_rows(ddbo, data: ArchiveData) -> None:
    tables = {
        table_name: [copy.deepcopy(row) for row in rows]
        for table_name, rows in data.tables.items()
    }
    tables[MOVIES] = rewrite_movie_rows_for_target_bucket(
        tables[MOVIES],
        data.manifest.movies,
    )

    for table_name in TABLES_IN_RESTORE_ORDER:
        write_rows(table_for_name(ddbo, table_name), tables[table_name])

    unique_email_rows = [{EMAIL: user[EMAIL]} for user in tables[USERS]]
    write_rows(ddbo.unique_emails, unique_email_rows)


def command_restore(args) -> int:
    configure_table_prefix(args.table_prefix)
    data = selected_archive_data(read_archive(args.archive), selection_from_args(args))
    ddbo = odb.DDBO()
    collisions = find_email_collisions(ddbo, data.tables[USERS])
    if collisions:
        print(
            "restore blocked: email address already exists: " + ", ".join(collisions),
            file=sys.stderr,
        )
        return 1

    print(
        f"{'commit' if args.commit else 'preflight'} restore: "
        f"{len(data.tables[USERS])} users, {len(data.tables[COURSES])} courses, "
        f"{len(data.tables[MOVIES])} movies",
        file=sys.stderr,
    )
    if not args.commit:
        return 0

    restore_movie_objects(args.archive, data.manifest.movies)
    restore_rows(ddbo, data)
    if args.regenerate_zips:
        raise DbBackupError("--regenerate-zips is not implemented yet")
    return 0


def command_send_restore_links(args) -> int:
    configure_table_prefix(args.table_prefix)
    data = selected_archive_data(read_archive(args.archive), selection_from_args(args))
    ddbo = odb.DDBO()
    emails = sorted({user[EMAIL] for user in data.tables[USERS]})
    if not args.send:
        print(f"dry run: would send restore links to {len(emails)} users", file=sys.stderr)
        for email in emails:
            print(f"  {email}", file=sys.stderr)
        return 0

    endpoint = args.planttracer_endpoint or os.environ.get(C.PLANTTRACER_API_BASE)
    if not endpoint:
        raise DbBackupError("--planttracer-endpoint is required with --send")
    for email in emails:
        ddbo.get_user_email(email)
        new_api_key = odb.make_new_api_key(email=email)
        mailer.send_links(
            email=email,
            planttracer_endpoint=endpoint,
            new_api_key=new_api_key,
        )
        print(f"sent restore link to {email}")
    return 0


def migrate_s3_urn(urn: str, *, from_course_id: str, to_course_id: str, commit: bool) -> str:
    bucket, key = parse_s3_urn(urn=urn)
    source_prefix = f"{from_course_id}/"
    if not key.startswith(source_prefix):
        raise DbBackupError(f"S3 key {key} does not start with {source_prefix}")
    new_key = f"{to_course_id}/{key[len(source_prefix):]}"
    if commit and new_key != key:
        body = s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()
        s3_client().put_object(Bucket=bucket, Key=new_key, Body=body)
        s3_client().delete_object(Bucket=bucket, Key=key)
    return f"s3://{bucket}/{new_key}"


def migrate_movie_frames(
        ddbo,
        *,
        movie_id: str,
        from_course_id: str,
        to_course_id: str) -> None:
    for frame in get_movie_frames(ddbo, movie_id):
        frame_urn = frame.get(FRAME_URN)
        if not frame_urn:
            continue
        new_urn = migrate_s3_urn(
            frame_urn,
            from_course_id=from_course_id,
            to_course_id=to_course_id,
            commit=True,
        )
        ddbo.movie_frames.update_item(
            Key={MOVIE_ID: movie_id, FRAME_NUMBER: frame[FRAME_NUMBER]},
            UpdateExpression="SET #frame_urn = :frame_urn",
            ExpressionAttributeNames={"#frame_urn": FRAME_URN},
            ExpressionAttributeValues={":frame_urn": new_urn},
        )


def update_user_course_reference(ddbo, user_id: str, from_course: dict, to_course: dict) -> None:
    user = ddbo.get_user(user_id)
    courses = [course_id for course_id in user.get(COURSES, []) if course_id != from_course[COURSE_ID]]
    if to_course[COURSE_ID] not in courses:
        courses.append(to_course[COURSE_ID])
    admin_for_courses = [
        course_id
        for course_id in user.get(ADMIN_FOR_COURSES, [])
        if course_id != from_course[COURSE_ID]
    ]
    if from_course[COURSE_ID] in user.get(ADMIN_FOR_COURSES, []):
        admin_for_courses.append(to_course[COURSE_ID])

    updates: dict[str, Any] = {
        COURSES: sorted(courses),
        ADMIN_FOR_COURSES: sorted(set(admin_for_courses)),
    }
    if user.get(PRIMARY_COURSE_ID) == from_course[COURSE_ID]:
        updates[PRIMARY_COURSE_ID] = to_course[COURSE_ID]
        updates[PRIMARY_COURSE_NAME] = to_course[COURSE_NAME]
    ddbo.update_table(ddbo.users, user_id, updates)


def update_course_admin_references(
        ddbo,
        *,
        from_course: dict,
        to_course: dict,
        affected_user_ids: set[str]) -> None:
    admins_to_move = [
        user_id
        for user_id in from_course.get(ADMINS_FOR_COURSE, [])
        if user_id in affected_user_ids
    ]
    if not admins_to_move:
        return
    from_admins = [
        user_id
        for user_id in from_course.get(ADMINS_FOR_COURSE, [])
        if user_id not in admins_to_move
    ]
    to_admins = sorted(set(to_course.get(ADMINS_FOR_COURSE, []) + admins_to_move))
    ddbo.update_table(ddbo.courses, from_course[COURSE_ID], {ADMINS_FOR_COURSE: from_admins})
    ddbo.update_table(ddbo.courses, to_course[COURSE_ID], {ADMINS_FOR_COURSE: to_admins})


def migrate_movie_row(ddbo, movie: dict[str, Any], from_course_id: str, to_course_id: str) -> None:
    updates: dict[str, Any] = {COURSE_ID: to_course_id}
    for field_name in MOVIE_S3_URN_FIELDS:
        urn = movie.get(field_name)
        if urn:
            updates[field_name] = migrate_s3_urn(
                urn,
                from_course_id=from_course_id,
                to_course_id=to_course_id,
                commit=True,
            )
    ddbo.update_table(ddbo.movies, movie[MOVIE_ID], updates)
    migrate_movie_frames(
        ddbo,
        movie_id=movie[MOVIE_ID],
        from_course_id=from_course_id,
        to_course_id=to_course_id,
    )


def migration_selection(ddbo, args) -> tuple[dict, dict, set[str], list[dict[str, Any]]]:
    from_course = ddbo.get_course(args.from_course_id)
    to_course = ddbo.get_course(args.to_course_id)
    movies = ddbo.get_movies_for_course_id(args.from_course_id)
    if args.user_email:
        user = ddbo.get_user_email(args.user_email)
        user_ids = {user[USER_ID]}
        movies = [movie for movie in movies if movie[USER_ID] == user[USER_ID]]
    else:
        user_ids = set(odb.course_enrollments(args.from_course_id))
        user_ids.update(from_course.get(ADMINS_FOR_COURSE, []))
        user_ids.update(movie[USER_ID] for movie in movies)
    return from_course, to_course, user_ids, movies


def command_migrate_course(args) -> int:
    configure_table_prefix(args.table_prefix)
    ddbo = odb.DDBO()
    from_course, to_course, user_ids, movies = migration_selection(ddbo, args)
    print(
        f"{'commit' if args.commit else 'preflight'} migrate-course: "
        f"{len(user_ids)} users, {len(movies)} movies from {args.from_course_id} "
        f"to {args.to_course_id}",
        file=sys.stderr,
    )
    for movie in movies:
        for field_name in MOVIE_S3_URN_FIELDS:
            urn = movie.get(field_name)
            if urn:
                migrate_s3_urn(
                    urn,
                    from_course_id=args.from_course_id,
                    to_course_id=args.to_course_id,
                    commit=False,
                )
    if not args.commit:
        return 0

    for user_id in sorted(user_ids):
        update_user_course_reference(ddbo, user_id, from_course, to_course)
        ddbo.course_users.put_item(Item={COURSE_ID: args.to_course_id, USER_ID: user_id})
        ddbo.course_users.delete_item(Key={COURSE_ID: args.from_course_id, USER_ID: user_id})
    update_course_admin_references(
        ddbo,
        from_course=from_course,
        to_course=to_course,
        affected_user_ids=user_ids,
    )
    for movie in movies:
        migrate_movie_row(ddbo, movie, args.from_course_id, args.to_course_id)
    return 0


def add_table_prefix(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--table-prefix",
        required=True,
        help=f"DynamoDB table prefix; overrides {C.DYNAMODB_TABLE_PREFIX}",
    )


def add_selection(
        parser: argparse.ArgumentParser,
        *,
        allow_movie: bool = True,
        required: bool = True) -> None:
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument("--all", action="store_true", dest="all_items", help="select all records")
    group.add_argument("--course-id", help="select one course dependency set")
    group.add_argument("--user-email", help="select one user dependency set")
    if allow_movie:
        group.add_argument("--movie-id", help="select one movie dependency set")


def selection_from_args(args, *, default_all: bool = False) -> Selection:
    all_items = getattr(args, "all_items", False)
    selectors = (
        all_items,
        getattr(args, "course_id", None) is not None,
        getattr(args, "user_email", None) is not None,
        getattr(args, "movie_id", None) is not None,
    )
    if default_all and not any(selectors):
        all_items = True
    return Selection.model_validate(
        {
            "all": all_items,
            "course_id": getattr(args, "course_id", None),
            "user_email": getattr(args, "user_email", None),
            "movie_id": getattr(args, "movie_id", None),
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plant Tracer DynamoDB/S3 backup and restore tool.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    clogging.add_argument(parser, loglevel_default="WARNING")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create a .ptb backup archive")
    add_table_prefix(backup)
    backup.add_argument("--output", required=True, help="Output .ptb file")
    add_selection(backup, required=False)
    backup.add_argument(
        "--include-deleted",
        action="store_true",
        help="include deleted movies",
    )

    restore = subparsers.add_parser("restore", help="Restore a .ptb backup archive")
    add_table_prefix(restore)
    restore.add_argument("archive", help=".ptb archive")
    add_selection(restore)
    restore.add_argument("--commit", action="store_true", help="write data")
    restore.add_argument(
        "--regenerate-zips",
        action="store_true",
        help="regenerate omitted movie ZIP artifacts after restore",
    )

    inspect = subparsers.add_parser("inspect", help="Inspect a .ptb backup archive")
    inspect.add_argument("archive", help=".ptb archive")
    inspect.add_argument(
        "--verbose",
        action="store_true",
        help="print one-line summaries for records and grouped frame trackpoints",
    )

    subparsers.add_parser(
        "list-prefixes",
        help="List complete DynamoDB table prefixes with counts and date ranges",
    )

    send_links = subparsers.add_parser(
        "send-restore-links",
        help="Send fresh login links to restored users",
    )
    add_table_prefix(send_links)
    send_links.add_argument("archive", help=".ptb archive")
    add_selection(send_links, allow_movie=False)
    send_links.add_argument("--send", action="store_true", help="send email")
    send_links.add_argument(
        "--planttracer-endpoint",
        help="Plant Tracer https:// endpoint used in login links",
    )

    migrate = subparsers.add_parser(
        "migrate-course",
        help="Rewrite course references and S3 keys from one course ID to another",
    )
    add_table_prefix(migrate)
    migrate.add_argument("--from-course-id", required=True, help="source course ID")
    migrate.add_argument("--to-course-id", required=True, help="target course ID")
    migrate.add_argument("--user-email", help="limit migration to one user")
    migrate.add_argument("--commit", action="store_true", help="write data")
    return parser


def dispatch(args) -> int:
    commands: dict[str, Any] = {
        "backup": command_backup,
        "inspect": command_inspect,
        "list-prefixes": command_list_prefixes,
        "restore": command_restore,
        "send-restore-links": command_send_restore_links,
        "migrate-course": command_migrate_course,
    }
    command = commands[args.command]
    return command(args)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)
    try:
        return dispatch(args)
    except DbBackupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
