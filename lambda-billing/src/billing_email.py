"""Send the requested weekly billing digest from the already collected cache.

The Monday schedule supplies a separate event to the serial collector function.
This path reads S3 and sends SES mail; it never makes paid billing queries.
A persisted ISO-week receipt suppresses normal retries after a successful send.
Stale or missing data fails visibly in Lambda logs rather than emailing zeroes.
SES and S3 are not transactional, so a failed receipt write can duplicate mail.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from botocore.exceptions import ClientError
from pydantic import BaseModel

from app.billing_models import CACHE_KEY, STALE_AFTER, BillingSnapshot, month_boundaries

LOGGER = logging.getLogger(__name__)
SENDER = "admin@planttracer.com"
RECIPIENT = "plantadmin@planttracer.com"
RECEIPT_KEY = "weekly-email.json"
BODY, ERROR, CODE = "Body", "Error", "Code"
TO, SUBJECT, TEXT, DATA, CHARSET = "ToAddresses", "Subject", "Text", "Data", "Charset"
MESSAGE_ID = "MessageId"


class EmailReceipt(BaseModel):
    """Record an SES-accepted weekly digest, not a guarantee of inbox delivery."""
    week: str
    message_id: str
    sent_at: datetime


def usd(value):
    """Format observed money consistently without losing small charge categories."""
    return "Unavailable" if value is None else f"${value:,.4f}"


def statistic(value, divisor=1):
    """Missing CloudWatch samples are unknown, not zero."""
    return "No data" if value is None else f"{value / divisor:,.2f}"


def digest(snapshot):
    """Plain text is readable in mail clients and does not embed remote tracking."""
    lines = ["Plant Tracer weekly AWS summary", f"Account: {snapshot.account_id}",
             f"Collected: {snapshot.collected_at.isoformat()}",
             "Spend: all regions/services. Charges are estimates until AWS finalizes them.",
             f"Function activity: {snapshot.activity_region}; existing functions, all versions.", ""]
    for month, period in ((snapshot.current, "current"), (snapshot.previous, "previous")):
        lines.extend([f"{month.start} to {month.end} UTC (end exclusive)",
                      f"Charges {usd(month.total.gross)}; credits/refunds {usd(month.total.credits)}; net {usd(month.total.net)}"])
        for label, rows in (("Services", month.services), ("Lambda charge types", month.lambda_usage),
                            ("Billing stack tags", month.stack_gross)):
            lines.append(label + ":")
            lines.extend(f"  {row.name}: charges {usd(row.gross)}, credits {usd(row.credits)}, net {usd(row.net)}"
                         for row in rows)
        lines.append("Function activity (invocations / errors / execution seconds):")
        for function in snapshot.functions:
            activity = getattr(function, period)
            lines.append(f"  {function.stack} / {function.name} ({function.component}): "
                         f"{statistic(activity.invocations)} / {statistic(activity.errors)} / "
                         f"{statistic(activity.duration_ms, 1000)}")
        totals = []
        for field, divisor in (("invocations", 1), ("errors", 1), ("duration_ms", 1000)):
            values = [getattr(getattr(item, period), field) for item in snapshot.functions]
            known = [value for value in values if value is not None]
            missing = len(values) - len(known)
            totals.append(statistic(sum(known), divisor) + f" ({missing} functions: no data)" if known else "No data")
        lines.append("Reported subtotal: " + " / ".join(totals))
        lines.append("")
    lines.extend([f"Retained SnapStart snapshots: {sum(item.snapshots for item in snapshot.functions)}",
                  f"Estimated 30-day caching run rate: {usd(snapshot.snapshot_monthly_estimate)} (excludes restores/credits).",
                  "Unallocated/shared costs lack an active stack billing tag; activity is not cost allocation.",
                  "No data means no samples, not zero. Execution time is not billed duration.",
                  "Admin: https://prod.planttracer.com/admin",
                  "AWS Cost Explorer: https://console.aws.amazon.com/costmanagement/home#/cost-explorer",
                  "AWS dashboards: https://console.aws.amazon.com/costmanagement/home#/dashboards"])
    return "\n".join(lines)


def send_weekly(s3, ses, bucket, now):
    """Validate freshness, suppress repeated weeks, and persist the SES receipt."""
    week = now.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%G-W%V")
    try:
        with s3.get_object(Bucket=bucket, Key=RECEIPT_KEY)[BODY] as body:
            receipt = EmailReceipt.model_validate_json(body.read())
        if receipt.week == week:
            return
    except ClientError as exc:
        if exc.response[ERROR][CODE] not in ("NoSuchKey", "404"):
            raise
    with s3.get_object(Bucket=bucket, Key=CACHE_KEY)[BODY] as body:
        snapshot = BillingSnapshot.model_validate_json(body.read())
    if not (timedelta(0) <= now - snapshot.collected_at <= STALE_AFTER) or (
            snapshot.current.start != month_boundaries(now)[1]):
        raise ValueError("Weekly email requires a fresh current-month billing cache")
    result = ses.send_email(Source=SENDER, Destination={TO: [RECIPIENT]}, Message={
        SUBJECT: {DATA: f"Plant Tracer AWS spend — {week}", CHARSET: "UTF-8"},
        BODY: {TEXT: {DATA: digest(snapshot), CHARSET: "UTF-8"}}})
    receipt = EmailReceipt(week=week, message_id=result[MESSAGE_ID], sent_at=now)
    s3.put_object(Bucket=bucket, Key=RECEIPT_KEY, Body=receipt.model_dump_json().encode(),
                  ContentType="application/json")
    LOGGER.info("SES accepted weekly billing digest for %s: %s", week, receipt.message_id)
