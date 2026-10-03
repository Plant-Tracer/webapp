"""Collect one account-wide billing snapshot daily for all Plant Tracer stacks.

Cost Explorer supplies both calendar months in three paginated queries.
CloudWatch supplies regional function metrics across versions, never aliases.
Lambda inventory supplies stack ownership and retained SnapStart snapshot sizes.
Only a complete collection replaces the private S3 cache; failures leave it stale.
This standalone scheduled function has billing access; the web function does not.
"""

import argparse
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field, ValidationError

from billing_email import send_weekly

from app.billing_models import (BILLING_BUCKET_ENV, CACHE_KEY, BillingSnapshot,
                                Charges, FunctionUsage, MonthCosts, month_boundaries)

LOGGER = logging.getLogger(__name__)
# AWS wire keys are centralized so requests and response parsing agree.
TYPE, KEY, VALUES, DIMENSIONS = "Type", "Key", "Values", "Dimensions"
START, END, TOKEN = "Start", "End", "NextPageToken"
COST, QUANTITY = "UnblendedCost", "UsageQuantity"
SERVICE, RECORD, USAGE = "SERVICE", "RECORD_TYPE", "USAGE_TYPE"
STACK_TAG, LOGICAL_TAG = "aws:cloudformation:stack-name", "aws:cloudformation:logical-id"
METRIC_NAMES = ("Invocations", "Errors", "Duration")
ID, METRIC_STAT, METRIC, NAMESPACE = "Id", "MetricStat", "Metric", "Namespace"
METRIC_NAME, NAME, VALUE, PERIOD, STAT = "MetricName", "Name", "Value", "Period", "Stat"
RETURN_DATA, NEXT_TOKEN = "ReturnData", "NextToken"
FUNCTION_NAME, TAGS, BODY = "FunctionName", "Tags", "Body"
FUNCTIONS, VERSIONS, VERSION, MEMORY, SNAPSTART = "Functions", "Versions", "Version", "MemorySize", "SnapStart"
OPTIMIZATION, ACCOUNT = "OptimizationStatus", "Account"
TIME_PERIOD, GRANULARITY, METRICS, GROUP_BY, FILTER = "TimePeriod", "Granularity", "Metrics", "GroupBy", "Filter"
FUNCTION_ARN = "FunctionArn"
QUERIES, START_TIME, END_TIME, RESULTS = "MetricDataQueries", "StartTime", "EndTime", "MetricDataResults"
ERROR, CODE = "Error", "Code"
CACHE_USAGE = "Lambda-SnapStart-Cached-GB-S"


class Amount(BaseModel):
    """AWS cost metric with its unit."""
    amount: Decimal = Field(alias="Amount")
    unit: str = Field(alias="Unit")


class CostGroup(BaseModel):
    """One AWS grouping and its cost/quantity metrics."""
    keys: list[str] = Field(alias="Keys")
    metrics: dict[str, Amount] = Field(alias="Metrics")


class CostPeriod(BaseModel):
    """One monthly result, possibly spread across multiple pages."""
    period: dict[str, str] = Field(alias="TimePeriod")
    groups: list[CostGroup] = Field(alias="Groups")
    estimated: bool = Field(alias="Estimated")


class CostPage(BaseModel):
    """Paginated Cost Explorer output."""
    periods: list[CostPeriod] = Field(alias="ResultsByTime")
    token: str | None = Field(default=None, alias="NextPageToken")


class MetricResult(BaseModel):
    """A timestamped metric series; incomplete results must not look like zero."""
    identifier: str = Field(alias="Id")
    timestamps: list[datetime] = Field(alias="Timestamps")
    values: list[float] = Field(alias="Values")
    status: str = Field(alias="StatusCode")


def cost_pages(client, start, end, groups, service=None):
    """Read every page without silently truncating expensive results."""
    parameters = {TIME_PERIOD: {START: str(start), END: str(end)},
                  GRANULARITY: "MONTHLY", METRICS: [COST, QUANTITY],
                  GROUP_BY: [{TYPE: kind, KEY: key} for kind, key in groups]}
    if service:
        parameters[FILTER] = {DIMENSIONS: {KEY: SERVICE, VALUES: [service]}}
    while True:
        page = CostPage.model_validate(client.get_cost_and_usage(**parameters))
        yield from page.periods
        if not page.token:
            break
        parameters[TOKEN] = page.token


def add_charge(rows, name, amount, record):
    """Accumulate signed credits separately while reconciling net costs."""
    row = next((item for item in rows if item.name == name), None)
    if row is None:
        row = Charges(name=name)
        rows.append(row)
    if record in ("Credit", "Refund"):
        row.credits += amount
    else:
        row.gross += amount


def collect_costs(client, now):
    """Two cost queries plus stack attribution; never mix quantities with different units."""
    previous, current, end = month_boundaries(now)
    months = [MonthCosts(start=previous, end=current, estimated=False),
              MonthCosts(start=current, end=end, estimated=False)]
    cache_cost, cache_quantity = Decimal(0), Decimal(0)
    for service, grouping, attribute in (
        (None, SERVICE, "services"), ("AWS Lambda", USAGE, "lambda_usage"),
        (None, STACK_TAG, "stack_gross"),
    ):
        kind = "TAG" if grouping == STACK_TAG else "DIMENSION"
        seen = set()
        for period in cost_pages(client, previous, end, [(kind, grouping), ("DIMENSION", RECORD)], service):
            month = next(m for m in months if str(m.start) == period.period[START])
            seen.add(month.start)
            month.estimated |= period.estimated
            for group in period.groups:
                amount = group.metrics[COST]
                if amount.unit != "USD":
                    raise ValueError("Only USD billing summaries are supported")
                name, record = group.keys
                if attribute == "stack_gross":
                    name = name.partition("$")[2] or "Unallocated / shared"
                add_charge(getattr(month, attribute), name, amount.amount, record)
                if attribute == "lambda_usage" and name == CACHE_USAGE and record == "Usage":
                    cache_cost += amount.amount
                    cache_quantity += group.metrics[QUANTITY].amount
        if seen != {previous, current}:
            raise ValueError("Cost Explorer omitted a requested month")
    for month in months:
        month.total.gross = sum((row.gross for row in month.services), Decimal(0))
        month.total.credits = sum((row.credits for row in month.services), Decimal(0))
    return months, cache_cost / cache_quantity if cache_quantity else None


def collect_functions(client, region):
    """Include all current functions and label untagged/shared ownership explicitly."""
    result = []
    for page in client.get_paginator("list_functions").paginate():
        for function in page[FUNCTIONS]:
            name = function[FUNCTION_NAME]
            tags = client.list_tags(Resource=function[FUNCTION_ARN])[TAGS]
            item = FunctionUsage(name=name, region=region, stack=tags.get(STACK_TAG, "Unallocated / shared"),
                                 component=tags.get(LOGICAL_TAG, "Other"))
            for versions in client.get_paginator("list_versions_by_function").paginate(FunctionName=name):
                for version in versions[VERSIONS]:
                    if version[VERSION] != "$LATEST" and version.get(SNAPSTART, {}).get(OPTIMIZATION) == "On":
                        item.snapshots += 1
                        item.snapshot_gb += Decimal(version[MEMORY]) / 1024
            result.append(item)
    return sorted(result, key=lambda item: (item.stack, item.name))


def metric_queries(functions):
    """Query only FunctionName dimensions, which include all published versions."""
    return [{ID: f"f{index}m{metric}", METRIC_STAT: {
        METRIC: {NAMESPACE: "AWS/Lambda", METRIC_NAME: name,
                 DIMENSIONS: [{NAME: FUNCTION_NAME, VALUE: function.name}]},
        PERIOD: 86400, STAT: "Sum"}, RETURN_DATA: True}
        for index, function in enumerate(functions) for metric, name in enumerate(METRIC_NAMES)]


def apply_metric(functions, result, month_start, window_start, window_end, more_pages=False):
    """Add a page's daily samples into the correct month, retaining missing data as null."""
    valid_status = result.status == "Complete" or (more_pages and result.status == "PartialData")
    if not valid_status or len(result.timestamps) != len(result.values):
        raise ValueError("Incomplete CloudWatch metric data")
    function_index, metric_index = result.identifier[1:].split("m")
    function = functions[int(function_index)]
    field = ("invocations", "errors", "duration_ms")[int(metric_index)]
    for stamp, value in zip(result.timestamps, result.values):
        if window_start <= stamp < window_end:
            activity = function.current if stamp.astimezone(timezone.utc).date() >= month_start else function.previous
            setattr(activity, field, (getattr(activity, field) or 0) + value)


def collect_activity(client, functions, now):
    """Batch and paginate CloudWatch requests for both calendar months together."""
    previous, current, _ = month_boundaries(now)
    start = datetime.combine(previous, datetime.min.time(), tzinfo=timezone.utc)
    queries = metric_queries(functions)
    for offset in range(0, len(queries), 500):
        parameters = {QUERIES: queries[offset:offset + 500],
                      START_TIME: start, END_TIME: now}
        while True:
            page = client.get_metric_data(**parameters)
            for raw in page[RESULTS]:
                apply_metric(functions, MetricResult.model_validate(raw), current, start, now, bool(page.get(NEXT_TOKEN)))
            if not page.get(NEXT_TOKEN):
                break
            parameters[NEXT_TOKEN] = page[NEXT_TOKEN]


def collect(session, now=None):
    """Read AWS data without writing cloud resources; useful for local verification."""
    now = now or datetime.now(timezone.utc)
    region = session.region_name or "us-east-1"
    account = session.client("sts").get_caller_identity()[ACCOUNT]
    months, rate = collect_costs(session.client("ce", region_name="us-east-1"), now)
    functions = collect_functions(session.client("lambda", region_name=region), region)
    collect_activity(session.client("cloudwatch", region_name=region), functions, now)
    return BillingSnapshot(account_id=account, collected_at=now, activity_region=region,
                           previous=months[0], current=months[1], functions=functions,
                           cache_rate_per_gb_second=rate)


def lambda_handler(event, _context):
    """Skip duplicate daily refreshes and atomically publish only a complete snapshot."""
    now = datetime.now(timezone.utc)
    session = boto3.Session()
    s3 = session.client("s3")
    bucket = os.environ[BILLING_BUCKET_ENV]
    if event.get("weekly") is True:
        send_weekly(s3, session.client("ses"), bucket, now)
        return
    try:
        existing = s3.get_object(Bucket=bucket, Key=CACHE_KEY)
        with existing[BODY] as body:
            snapshot = BillingSnapshot.model_validate_json(body.read())
        if snapshot.collected_at.date() == now.date():
            return
    except ClientError as exc:
        if exc.response[ERROR][CODE] not in ("NoSuchKey", "404"):
            raise
    except ValidationError:
        LOGGER.warning("Replacing malformed billing cache")
    snapshot = collect(session, now)
    s3.put_object(Bucket=bucket, Key=CACHE_KEY, Body=snapshot.model_dump_json().encode(),
                  ContentType="application/json")
    LOGGER.info("Published billing summary for account %s", snapshot.account_id)


def main():
    """Collect live read-only evidence to a local file; never modify AWS from this CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    snapshot = collect(boto3.Session())
    Path(args.output).write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
