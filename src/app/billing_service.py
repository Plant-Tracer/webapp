"""Read the private billing cache for the superadmin dashboard.

This module performs one S3 read and never calls Cost Explorer or CloudWatch.
The admin route authenticates and authorizes the viewer before calling it.
Typed validation rejects malformed caches; failures are explicit, not zero spend.
Old snapshots remain visible with a stale marker and their original periods.
Console links are generated here and never taken from cached third-party data.
"""

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ValidationError

from . import s3_presigned
from .billing_models import BILLING_BUCKET_ENV, CACHE_KEY, STALE_AFTER, BillingSnapshot, month_boundaries
from .constants import logger


BODY = "Body"
START_DATE, END_DATE, GRANULARITY, AGGREGATE = "startDate", "endDate", "granularity", "costAggregate"


class BillingResponse(BaseModel):
    """The UI can distinguish setup, stale data, and retrieval failures."""
    state: str
    message: str
    snapshot: BillingSnapshot | None = None
    current_url: str
    previous_url: str
    dashboards_url: str = "https://console.aws.amazon.com/costmanagement/home#/dashboards"


def cost_url(start, end):
    """Cost Explorer uses an inclusive end date in its console URL."""
    params = urlencode({START_DATE: str(start), END_DATE: str(end),
                        GRANULARITY: "Monthly", AGGREGATE: "unBlendedCost"})
    return "https://console.aws.amazon.com/costmanagement/home#/cost-explorer?" + params


def billing_summary(now=None) -> BillingResponse:
    """Read only the cached summary, failing visibly while preserving privacy."""
    now = now or datetime.now(timezone.utc)
    previous, current, _ = month_boundaries(now)
    response = BillingResponse(
        state="unconfigured", message="Billing collection has not been configured.",
        current_url=cost_url(current, now.date()),
        previous_url=cost_url(previous, current - timedelta(days=1)),
    )
    bucket = os.environ.get(BILLING_BUCKET_ENV)
    if not bucket:
        return response
    try:
        stored = s3_presigned.s3_client().get_object(Bucket=bucket, Key=CACHE_KEY)
        with stored[BODY] as body:
            snapshot = BillingSnapshot.model_validate_json(body.read(2_000_001))
        if snapshot.collected_at > now:
            raise ValueError("Billing snapshot is dated in the future")
    except (BotoCoreError, ClientError, ValidationError, ValueError, OSError):
        logger.warning("Billing summary cache unavailable", exc_info=True)
        response.state = "unavailable"
        response.message = "Billing summary is unavailable; no zero values have been assumed."
        return response
    response.snapshot = snapshot
    stale = now - snapshot.collected_at > STALE_AFTER or snapshot.current.start != current
    response.state = "stale" if stale else "ready"
    response.message = "Cached summary is stale; showing the last successful collection." if stale else (
        "Updated daily. AWS billing data may lag usage; current charges are estimates.")
    return response
