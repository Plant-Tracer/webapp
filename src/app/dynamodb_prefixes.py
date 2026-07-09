"""
Shared DynamoDB table-prefix discovery for operator CLI tools.
"""

import time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from . import odbmaint
from .odb import (
    COURSES,
    CREATED,
    CREATED_AT,
    DATE_UPLOADED,
    MOVIE_STATE_UPDATED_AT,
    MOVIES,
    USERS,
)

TABLE_NAMES = "TableNames"
LAST_EVALUATED_TABLE_NAME = "LastEvaluatedTableName"
EXCLUSIVE_START_TABLE_NAME = "ExclusiveStartTableName"
ITEMS = "Items"
COUNT = "Count"
LAST_EVALUATED_KEY = "LastEvaluatedKey"
EXCLUSIVE_START_KEY = "ExclusiveStartKey"
CONSISTENT_READ = "ConsistentRead"
PROJECTION_EXPRESSION = "ProjectionExpression"
EXPRESSION_ATTRIBUTE_NAMES = "ExpressionAttributeNames"

LIST_PREFIX_HEADERS = ("prefix", "courses", "users", "movies", "from", "to")
LIST_PREFIX_RIGHT_ALIGNED = (False, True, True, True, False, False)
COURSE_DATE_FIELDS = (CREATED, CREATED_AT)
USER_DATE_FIELDS = (CREATED,)
MOVIE_DATE_FIELDS = (CREATED_AT, DATE_UPLOADED, MOVIE_STATE_UPDATED_AT)
DYNAMODB_TABLE_CONFIGURATIONS = tuple(odbmaint.load_table_configurations())
REQUIRED_PREFIX_TABLES = tuple(
    table_config[odbmaint.TableName]
    for table_config in DYNAMODB_TABLE_CONFIGURATIONS
)


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


def list_dynamodb_table_names(dynamodb) -> list[str]:
    """Return all DynamoDB table names for the configured resource."""
    table_names: list[str] = []
    list_kwargs: dict[str, Any] = {}
    while True:
        response = dynamodb.meta.client.list_tables(**list_kwargs)
        table_names.extend(response.get(TABLE_NAMES, []))
        last_table_name = response.get(LAST_EVALUATED_TABLE_NAME)
        if last_table_name is None:
            return sorted(table_names)
        list_kwargs[EXCLUSIVE_START_TABLE_NAME] = last_table_name


def prefix_for_table_name(table_name: str, base_table_name: str) -> str | None:
    """Return the Plant Tracer prefix for a table/base-name pair, if any."""
    if table_name == base_table_name:
        return ""
    if not table_name.endswith(base_table_name):
        return None
    prefix = table_name[: -len(base_table_name)]
    if prefix.endswith("-"):
        return prefix
    return None


def complete_prefixes(table_names: list[str]) -> list[str]:
    """Return prefixes that have every configured Plant Tracer DynamoDB table."""
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
        PROJECTION_EXPRESSION: ", ".join(expression_names),
        EXPRESSION_ATTRIBUTE_NAMES: expression_names,
    }


def summarize_table_dates(table, date_fields: tuple[str, ...]) -> TableDateSummary:
    summary = TableDateSummary(date_range=TimestampRange())
    scan_kwargs: dict[str, Any] = {
        CONSISTENT_READ: True,
        **date_projection_kwargs(date_fields),
    }
    while True:
        response = table.scan(**scan_kwargs)
        summary.count += int(response[COUNT])
        for item in response.get(ITEMS, []):
            for field_name in date_fields:
                summary.date_range.include(item.get(field_name))
        last_key = response.get(LAST_EVALUATED_KEY)
        if last_key is None:
            return summary
        scan_kwargs[EXCLUSIVE_START_KEY] = last_key


def prefix_summaries(dynamodb) -> list[PrefixSummary]:
    """Return count/date summaries for complete table prefixes."""
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
