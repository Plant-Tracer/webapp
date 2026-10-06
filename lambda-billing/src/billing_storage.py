"""Collect daily S3 storage history without listing or reading bucket objects.

ListBuckets discovers account-owned general-purpose buckets and their regions.
CloudWatch supplies daily byte and object samples for the preceding two months.
Query all documented storage types so lifecycle transitions retain their history.
Only reported samples contribute; absent days remain unknown rather than zero.
The scheduled billing collector caches this history for the web UI and digest.
"""

import calendar
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from app.billing_models import BucketStorage, StorageDay, StorageSummary

# AWS protocol names are centralized for requests and response parsing.
BUCKETS, NAME, REGION = 'Buckets', 'Name', 'BucketRegion'
ID, VALUES, TIMES, STATUS = 'Id', 'Values', 'Timestamps', 'StatusCode'
RESULTS, TOKEN, QUERIES = 'MetricDataResults', 'NextToken', 'MetricDataQueries'
START, END = 'StartTime', 'EndTime'
METRIC_STAT, METRIC, NAMESPACE, METRIC_NAME = 'MetricStat', 'Metric', 'Namespace', 'MetricName'
DIMENSIONS, VALUE, PERIOD, STAT = 'Dimensions', 'Value', 'Period', 'Stat'
STORAGE_TYPES = (
    'StandardStorage', 'ReducedRedundancyStorage', 'StandardIAStorage', 'StandardIAObjectOverhead',
    'StandardIASizeOverhead', 'OneZoneIAStorage', 'OneZoneIASizeOverhead',
    'IntelligentTieringFAStorage', 'IntelligentTieringIAStorage', 'IntelligentTieringAAStorage',
    'IntelligentTieringAIAStorage', 'IntelligentTieringDAAStorage', 'IntAAObjectOverhead',
    'IntAAS3ObjectOverhead', 'IntDAAObjectOverhead', 'IntDAAS3ObjectOverhead',
    'GlacierStorage', 'GlacierStagingStorage', 'GlacierObjectOverhead', 'GlacierS3ObjectOverhead',
    'GlacierInstantRetrievalStorage', 'GlacierIRSizeOverhead', 'DeepArchiveStorage',
    'DeepArchiveStagingStorage', 'DeepArchiveObjectOverhead', 'DeepArchiveS3ObjectOverhead',
)


class StorageMetric(BaseModel):
    """One page of a daily metric series from CloudWatch."""
    identifier: str = Field(alias=ID)
    values: list[float] = Field(alias=VALUES)
    timestamps: list[datetime] = Field(alias=TIMES)
    status: str = Field(alias=STATUS)


def storage_window(now):
    """Two calendar months ending at today's UTC midnight; exclude unfinished days."""
    end = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    year, month = divmod(end.year * 12 + end.month - 3, 12)
    start = end.replace(year=year, month=month + 1, day=min(end.day, calendar.monthrange(year, month + 1)[1]))
    return start, end


def storage_queries(bucket):
    """Use Average for daily gauges; never sum the same day's repeated samples."""
    return [{ID: f's{index}', METRIC_STAT: {METRIC: {
        NAMESPACE: 'AWS/S3', METRIC_NAME: 'NumberOfObjects' if index == 0 else 'BucketSizeBytes',
        DIMENSIONS: [{NAME: 'BucketName', VALUE: bucket}, {NAME: 'StorageType', VALUE: storage}]},
        PERIOD: 86400, STAT: 'Average'}}
        for index, storage in enumerate(('AllStorageTypes', *STORAGE_TYPES))]


def bucket_history(client, name, region, start, end):
    """Merge pages by series/date, retaining gaps and rejecting partial API results."""
    series = {f's{i}': {} for i in range(len(STORAGE_TYPES) + 1)}
    parameters = {START: start, END: end, QUERIES: storage_queries(name)}
    seen = set()
    incomplete = set()
    while True:
        page = client.get_metric_data(**parameters)
        for raw in page[RESULTS]:
            metric = StorageMetric.model_validate(raw)
            if metric.status == 'PartialData' and page.get(TOKEN):
                incomplete.add(metric.identifier)
            elif metric.status == 'Complete':
                incomplete.discard(metric.identifier)
            else:
                raise ValueError(f'Incomplete S3 metric for {name}: {metric.status}')
            if len(metric.timestamps) != len(metric.values):
                raise ValueError(f'Mismatched S3 samples for {name}')
            seen.add(metric.identifier)
            for stamp, value in zip(metric.timestamps, metric.values):
                day = stamp.astimezone(timezone.utc).date()
                if start.date() <= day < end.date():
                    series[metric.identifier][day] = value
        if not page.get(TOKEN):
            break
        parameters[TOKEN] = page[TOKEN]
    if incomplete:
        raise ValueError(f'Incomplete S3 metric pages for {name}')
    if seen != set(series):
        raise ValueError(f'CloudWatch omitted S3 series for {name}')
    days = []
    day = start.date()
    while day < end.date():
        sizes = [samples[day] for key, samples in series.items() if key != 's0' and day in samples]
        days.append(StorageDay(day=day, size_bytes=sum(sizes) if sizes else None, objects=series['s0'].get(day)))
        day += timedelta(days=1)
    return BucketStorage(name=name, region=region, days=days)


def collect_storage(session, now):
    """Discover buckets with pagination, then query CloudWatch in each bucket's region."""
    start, end = storage_window(now)
    buckets = []
    clients = {}
    for page in session.client('s3', region_name='us-east-1').get_paginator('list_buckets').paginate(MaxBuckets=1000):
        for bucket in page[BUCKETS]:
            region = bucket[REGION]
            if region not in clients:
                clients[region] = session.client('cloudwatch', region_name=region)
            buckets.append(bucket_history(clients[region], bucket[NAME], region, start, end))
    return StorageSummary(start=start.date(), end=end.date(), buckets=sorted(buckets, key=lambda b: b.name))
