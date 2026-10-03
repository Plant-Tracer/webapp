"""Exercise billing arithmetic, AWS pagination, and private admin delivery.

Pure calendar and aggregation checks catch credits and month-boundary mistakes.
Botocore Stubber covers remote billing protocols unavailable in local emulators.
Actual S3 cache reads use MinIO, and authorization uses DynamoDB Local users.
The browser check goes through Flask, authentication, S3, and the real JS module.
No paid AWS APIs or production resources are used by these tests.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import uuid

import boto3
from botocore.stub import ANY, Stubber
from botocore.exceptions import ClientError
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from billing_storage import STORAGE_TYPES, bucket_history, storage_queries, storage_window
from billing_email import (BILLING_URL_ENV, BODY, CHARSET, DATA, MESSAGE_ID, RECIPIENT, RECEIPT_KEY,
                           SENDER, SUBJECT, TEXT, TO, digest, send_weekly)
from billing_collector import (MetricResult, add_charge, apply_metric, collect_activity,
                               cache_is_current, collect_costs, collect_stack_lifetimes, cost_pages, metric_queries)

from app import apikey, billing_service, odb, s3_presigned
from app.billing_models import (BILLING_BUCKET_ENV, CACHE_KEY, BillingSnapshot, Charges,
                                BucketStorage, StorageDay, StorageSummary, FunctionUsage, MonthCosts, StackLifetime, month_boundaries)

from .constants import ADMIN_EMAIL


NOW = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)


def snapshot(now=NOW):
    """A complete cache with a real zero and unavailable metrics for comparison."""
    previous, current, end = month_boundaries(now)
    return BillingSnapshot(account_id="123456789012", collected_at=now, activity_region="us-east-1",
                           current=MonthCosts(start=current, end=end, total=Charges(name="AWS", gross=5)),
                           previous=MonthCosts(start=previous, end=current,
                                               total=Charges(name="AWS", gross=52, credits=-50)),
                           functions=[FunctionUsage(name="prod-web", region="us-east-1", stack="prod",
                                                    component="LambdaWebFunction", snapshots=1,
                                                    snapshot_gb=Decimal("0.5"))],
                           cache_rate_per_gb_second=Decimal("0.0000015"))


@pytest.fixture
def cache_bucket(local_s3, monkeypatch):
    """A dedicated real MinIO bucket, cleaned without touching application data."""
    assert local_s3
    bucket = f"billing-test-{uuid.uuid4().hex}"
    client = s3_presigned.s3_client()
    client.create_bucket(Bucket=bucket)
    monkeypatch.setenv(BILLING_BUCKET_ENV, bucket)
    yield bucket
    client.delete_object(Bucket=bucket, Key=CACHE_KEY)
    client.delete_object(Bucket=bucket, Key=RECEIPT_KEY)
    client.delete_bucket(Bucket=bucket)


def publish(bucket, content):
    """Write test cache bytes through real S3 rather than replacing the reader."""
    s3_presigned.s3_client().put_object(Bucket=bucket, Key=CACHE_KEY, Body=content)


def test_month_boundaries_and_money():
    """UTC year transitions and signed credits must survive JSON round trips."""
    assert month_boundaries(datetime.fromisoformat("2027-01-01T00:30:00+02:00")) == (
        date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1))
    rows = []
    add_charge(rows, "Lambda", Decimal("52.57"), "Usage")
    add_charge(rows, "Lambda", Decimal("-50"), "Credit")
    add_charge(rows, "Lambda", Decimal("-1"), "Refund")
    assert rows[0].net == Decimal("1.57")
    data = BillingSnapshot.model_validate_json(snapshot().model_dump_json())
    assert data.snapshot_monthly_estimate == Decimal("1.944")


def test_cost_pagination():
    """A second CE page is consumed with the original query intact."""
    client = boto3.client("ce", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")
    period = {"TimePeriod": {"Start": "2026-09-01", "End": "2026-10-01"}, "Groups": [], "Estimated": False}
    expected = {"TimePeriod": {"Start": "2026-09-01", "End": "2026-10-04"}, "Granularity": "MONTHLY",
                "Metrics": ["UnblendedCost", "UsageQuantity"],
                "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}]}
    with Stubber(client) as stub:
        stub.add_response("get_cost_and_usage", {"ResultsByTime": [period], "NextPageToken": "page2"}, expected)
        stub.add_response("get_cost_and_usage", {"ResultsByTime": [period]}, {**expected, "NextPageToken": "page2"})
        assert len(list(cost_pages(client, date(2026, 9, 1), date(2026, 10, 4), [("DIMENSION", "SERVICE")]))) == 2
        stub.assert_no_pending_responses()


def test_metrics_separate_months_and_missing_values():
    """Daily totals include versions once and preserve unknown versus zero."""
    functions = snapshot().functions
    result = MetricResult(Id="f0m0", Timestamps=[NOW, NOW - timedelta(days=4)], Values=[0, 13], StatusCode="Complete")
    apply_metric(functions, result, date(2026, 10, 1), datetime(2026, 9, 1, tzinfo=timezone.utc), NOW + timedelta(seconds=1))
    assert functions[0].current.invocations == 0
    assert functions[0].previous.invocations == 13
    assert functions[0].current.errors is None
    boundary = MetricResult(Id="f0m0", Timestamps=[datetime.fromisoformat("2026-09-30T17:00:00-07:00")],
                            Values=[5], StatusCode="Complete")
    apply_metric(functions, boundary, date(2026, 10, 1), datetime(2026, 9, 1, tzinfo=timezone.utc), NOW)
    assert functions[0].current.invocations == 5
    assert functions[0].previous.invocations == 13
    result.status = "InternalError"
    with pytest.raises(ValueError, match="Incomplete"):
        apply_metric(functions, result, date(2026, 10, 1), NOW, NOW)


def test_metric_pagination():
    """CloudWatch pagination accumulates all pages without alias duplication."""
    functions = snapshot().functions
    queries = metric_queries(functions)
    assert queries[0]["MetricStat"]["Metric"]["Dimensions"] == [{"Name": "FunctionName", "Value": "prod-web"}]
    client = boto3.client("cloudwatch", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")
    expected = {"MetricDataQueries": queries, "StartTime": datetime(2026, 9, 1, tzinfo=timezone.utc), "EndTime": NOW}
    with Stubber(client) as stub:
        stub.add_response("get_metric_data", {"MetricDataResults": [
            {"Id": "f0m0", "Timestamps": [NOW-timedelta(days=3)], "Values": [7], "StatusCode": "PartialData"}],
            "NextToken": "next"}, expected)
        stub.add_response("get_metric_data", {"MetricDataResults": [
            {"Id": "f0m0", "Timestamps": [NOW-timedelta(days=1)], "Values": [5], "StatusCode": "Complete"}]},
            {**expected, "NextToken": "next"})
        collect_activity(client, functions, NOW)
        stub.assert_no_pending_responses()
    assert functions[0].previous.invocations == 7
    assert functions[0].current.invocations == 5


def test_cache_states(cache_bucket, monkeypatch):
    """Missing, corrupt, future, stale, and month-rollover caches stay distinguishable."""
    assert billing_service.billing_summary(NOW).state == "unavailable"
    publish(cache_bucket, b"broken")
    assert billing_service.billing_summary(NOW).snapshot is None
    publish(cache_bucket, snapshot(NOW + timedelta(days=1)).model_dump_json())
    assert billing_service.billing_summary(NOW).state == "unavailable"
    publish(cache_bucket, snapshot().model_dump_json())
    assert billing_service.billing_summary(NOW).state == "ready"
    assert billing_service.billing_summary(NOW + timedelta(days=2)).state == "stale"
    old = snapshot(datetime(2026, 9, 30, 23, tzinfo=timezone.utc))
    publish(cache_bucket, old.model_dump_json())
    response = billing_service.billing_summary(datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert response.state == "stale" and response.snapshot.current.start == date(2026, 9, 1)
    monkeypatch.delenv(BILLING_BUCKET_ENV)
    assert billing_service.billing_summary(NOW).state == "unconfigured"


def test_admin_billing_authorization(client, new_course, cache_bucket):
    """Account costs are private to superadmins, not course admins or auditors."""
    publish(cache_bucket, snapshot().model_dump_json())
    assert client.get("/api/admin/billing").status_code == 403
    assert client.get("/billing").status_code == 302
    client.set_cookie(apikey.cookie_name(), new_course[odb.API_KEY])
    for role in (odb.SUPER_ROLE_NONE, odb.SUPER_ROLE_SUPERAUDITOR, odb.SUPER_ROLE_SUPERADMIN):
        new_course["ddbo"].update_table(odb.DDBO().users, new_course[odb.USER_ID], {odb.SUPER_ROLE: role})
        response = client.get("/api/admin/billing")
        expected = 200 if role == odb.SUPER_ROLE_SUPERADMIN else 403
        assert response.status_code == expected
        assert client.get("/billing").status_code == expected
        admin_page = client.get("/admin")
        assert 'id="billing-content"' not in admin_page.text
        assert ('href="billing"' in admin_page.text) == (role == odb.SUPER_ROLE_SUPERADMIN)
    assert response.json["snapshot"]["previous"]["total"]["net"] == "2"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert client.get("/api/admin/billing").json == response.json
    client.set_cookie(apikey.cookie_name(), odb.make_new_api_key(email=new_course[ADMIN_EMAIL]))
    assert client.get("/billing").status_code == 403
    assert client.get("/api/admin/billing").status_code == 403
    assert 'href="billing"' not in client.get("/admin").text


@pytest.mark.selenium
def test_admin_billing_browser(live_server, chrome_driver, new_course, cache_bucket):
    """Authenticated admin renders real cached data and usable AWS destination links."""
    data = snapshot(datetime.now(timezone.utc))
    data.functions[0].stack_lifetime = StackLifetime(
        started_at=NOW - timedelta(days=3, hours=2, minutes=1), stopped_at=NOW, status="DELETE_COMPLETE")
    data.functions[0].previous.errors = 1
    data.storage = StorageSummary(start=date(2026, 8, 3), end=date(2026, 10, 3), buckets=[
        BucketStorage(name="test-bucket", region="us-east-1", days=[
            StorageDay(day=date(2026, 10, 1), size_bytes=2e9, objects=10),
            StorageDay(day=date(2026, 10, 2), size_bytes=3e9, objects=12)])])
    data.current.services = [Charges(name="Amazon Simple Storage Service", gross=1)]
    publish(cache_bucket, data.model_dump_json())
    new_course["ddbo"].update_table(odb.DDBO().users, new_course[odb.USER_ID], {odb.SUPER_ROLE: odb.SUPER_ROLE_SUPERADMIN})
    chrome_driver.get(live_server)
    chrome_driver.add_cookie({"name": apikey.cookie_name(), "value": new_course[odb.API_KEY]})
    chrome_driver.get(live_server + "/admin")
    assert not chrome_driver.find_elements(By.ID, "billing-content")
    chrome_driver.find_element(By.LINK_TEXT, "Billing").click()
    assert chrome_driver.current_url == live_server + "/billing"
    WebDriverWait(chrome_driver, 20).until(lambda driver: "$52.00" in driver.find_element(By.ID, "billing-content").text)
    panel = chrome_driver.find_element(By.ID, "admin-billing")
    assert panel.is_displayed()
    assert chrome_driver.find_element(By.TAG_NAME, "h1").text == "Billing"
    assert "No data" in panel.text and "$1.944" in panel.text
    assert "Elapsed: 3d 2h 1m" in panel.text
    error_link = panel.find_element(By.CSS_SELECTOR, "a[aria-label^='1 errors:']")
    assert "#logs-insights:queryDetail=" in error_link.get_attribute("href")
    assert "Credits / refunds" not in panel.text
    assert "test-bucket" in panel.text and "Reported storage: 3 GB" in panel.text
    assert panel.find_element(By.CSS_SELECTOR, "svg[role='img']").is_displayed()
    panel.find_element(By.CSS_SELECTOR, "select[aria-label='Storage history bucket']").send_keys("test-bucket")
    assert "1 of 1 buckets" in panel.text
    chrome_driver.save_screenshot(".tmp/billing-storage-browser.png")
    links = panel.find_elements(By.CSS_SELECTOR, "nav a")
    assert len(links) == 3
    assert all(link.get_attribute("href").startswith("https://console.aws.amazon.com/costmanagement/") for link in links)
    Path(".tmp").mkdir(exist_ok=True)
    chrome_driver.save_screenshot(".tmp/billing-admin.png")
    publish(cache_bucket, snapshot(datetime.now(timezone.utc) - timedelta(days=2)).model_dump_json())
    chrome_driver.refresh()
    WebDriverWait(chrome_driver, 20).until(
        lambda driver: "stale" in driver.find_element(By.ID, "billing-status").text)
    assert chrome_driver.find_element(By.ID, "billing-status").get_attribute("class") == "admin-error"
    chrome_driver.save_screenshot(".tmp/billing-admin-stale.png")


def test_weekly_email_receipt_and_freshness(cache_bucket, monkeypatch):
    """SES is the remote boundary; real S3 persists receipts and suppresses retries."""
    monkeypatch.setenv(BILLING_URL_ENV, "https://slg-dev.planttracer.com/billing")
    data = snapshot()
    data.functions[0].current.invocations = 0
    text = digest(data)
    assert "$52.0000" in text and "$-50.0000" in text and "No data" in text
    assert "2026-09-01 to 2026-10-01" in text
    assert "https://slg-dev.planttracer.com/billing" in text
    assert "0 functions: no data" not in text
    data.functions.append(data.functions[0].model_copy(deep=True))
    data.functions[1].current.invocations = None
    assert "Reported subtotal: 0.00 (1 function: no data)" in digest(data)
    data.functions.pop()
    publish(cache_bucket, data.model_dump_json())
    ses = boto3.client("ses", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")
    s3 = s3_presigned.s3_client()
    with Stubber(ses) as stub:
        stub.add_response("send_email", {MESSAGE_ID: "accepted-id"}, {
            "Source": SENDER, "Destination": {TO: [RECIPIENT]}, "Message": {
                SUBJECT: {DATA: "Plant Tracer AWS spend — 2026-W40", CHARSET: "UTF-8"},
                BODY: {TEXT: {DATA: text, CHARSET: "UTF-8"}}}})
        send_weekly(s3, ses, cache_bucket, NOW)
        send_weekly(s3, ses, cache_bucket, NOW + timedelta(hours=1))
        stub.assert_no_pending_responses()
        with pytest.raises(ValueError, match="fresh"):
            send_weekly(s3, ses, cache_bucket, NOW + timedelta(days=7))
    s3.delete_object(Bucket=cache_bucket, Key=RECEIPT_KEY)
    with Stubber(ses) as stub:
        stub.add_client_error("send_email", service_error_code="MessageRejected", expected_params={
            "Source": SENDER, "Destination": {TO: [RECIPIENT]}, "Message": ANY})
        with pytest.raises(ClientError, match="MessageRejected"):
            send_weekly(s3, ses, cache_bucket, NOW)
        with pytest.raises(ClientError, match="NoSuchKey"):
            s3.get_object(Bucket=cache_bucket, Key=RECEIPT_KEY)


def test_cost_reconciliation_and_unallocated_stack():
    """Real AWS response shapes reconcile service totals and observed snapshot rates."""
    client = boto3.client("ce", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")
    def group(name, record, amount, quantity="0"):
        return {"Keys": [name, record], "Metrics": {"UnblendedCost": {"Amount": amount, "Unit": "USD"},
                                                  "UsageQuantity": {"Amount": quantity, "Unit": "N/A"}}}
    def response(groups):
        return {"ResultsByTime": [
            {"TimePeriod": {"Start": "2026-09-01", "End": "2026-10-01"}, "Groups": groups, "Estimated": False},
            {"TimePeriod": {"Start": "2026-10-01", "End": "2026-10-04"}, "Groups": [], "Estimated": True}]}
    with Stubber(client) as stub:
        stub.add_response("get_cost_and_usage", response([
            group("AWS Lambda", "Usage", "52.57"), group("AWS Lambda", "Credit", "-50")]))
        stub.add_response("get_cost_and_usage", response([
            group("Lambda-SnapStart-Cached-GB-S", "Usage", "50", "1000000"),
            group("Lambda-SnapStart-Cached-GB-S", "Credit", "-50", "1000000")]))
        stub.add_response("get_cost_and_usage", response([group("aws:cloudformation:stack-name$", "Usage", "52.57")]))
        months, rate = collect_costs(client, NOW)
        stub.assert_no_pending_responses()
    assert months[0].total == Charges(name="All AWS services", gross=Decimal("52.57"), credits=-50)
    assert months[0].stack_gross[0].name == "Unallocated / shared"
    assert rate == Decimal("0.00005")
    assert months[1].estimated and months[1].total == Charges(name="All AWS services")
    with Stubber(client) as stub:
        stub.add_response("get_cost_and_usage", {"ResultsByTime": []})
        with pytest.raises(ValueError, match="omitted"):
            collect_costs(client, NOW)


def test_stack_lifetimes_match_ids_paginate_and_preserve_deleted_history():
    """Reused names never merge incarnations; deleted dates survive AWS history expiry."""
    client = boto3.client("cloudformation", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")
    functions = [FunctionUsage(name=f"fn-{key}", stack="prod", stack_id=key, region="us-east-1", component="Web")
                 for key in ("old", "new", "expired", "unavailable")]
    previous = snapshot()
    previous.functions = [functions[2].model_copy(deep=True)]
    previous.functions[0].stack_lifetime = StackLifetime(
        started_at=NOW - timedelta(days=200), stopped_at=NOW - timedelta(days=100), status="DELETE_COMPLETE")
    with Stubber(client) as stub:
        stub.add_response("list_stacks", {"StackSummaries": [
            {"StackId": "old", "StackName": "prod", "CreationTime": NOW - timedelta(days=20),
             "DeletionTime": NOW - timedelta(days=10), "StackStatus": "DELETE_COMPLETE"}], "NextToken": "next"}, {})
        stub.add_response("list_stacks", {"StackSummaries": [
            {"StackId": "new", "StackName": "prod", "CreationTime": NOW - timedelta(days=5),
             "StackStatus": "UPDATE_COMPLETE"}]}, {"NextToken": "next"})
        collect_stack_lifetimes(client, functions, previous)
        stub.assert_no_pending_responses()
    assert functions[0].stack_lifetime.stopped_at == NOW - timedelta(days=10)
    assert functions[1].stack_lifetime.started_at == NOW - timedelta(days=5)
    assert functions[1].stack_lifetime.stopped_at is None
    assert functions[2].stack_lifetime.stopped_at == NOW - timedelta(days=100)
    assert functions[3].stack_lifetime is None


def test_same_day_cache_upgrade_and_legacy_reader():
    """New deployments refresh an old same-day schema; readers still accept old caches."""
    data = snapshot()
    assert cache_is_current(data, NOW)
    assert not cache_is_current(data, NOW + timedelta(days=1))
    data.schema_version = 1
    old = data.model_dump(exclude={"functions": {"__all__": {"stack_id", "stack_lifetime"}}})
    read = BillingSnapshot.model_validate(old)
    assert read.functions[0].stack_lifetime is None
    assert not cache_is_current(read, NOW)


def test_s3_storage_history_aggregates_types_and_pages_without_filling_gaps():
    """Sum storage classes, preserve real zeroes, and never duplicate paginated samples."""
    client = boto3.client("cloudwatch", region_name="us-east-2", aws_access_key_id="test", aws_secret_access_key="test")
    start, end = storage_window(NOW)
    empty = [{"Id": f"s{i}", "Timestamps": [], "Values": [], "StatusCode": "Complete"}
             for i in range(len(STORAGE_TYPES) + 1)]
    one = NOW.replace(hour=0) - timedelta(days=2)
    two = one + timedelta(days=1)
    first = [dict(x) for x in empty]
    first[0].update(Timestamps=[one, two], Values=[10, 0])
    first[1].update(Timestamps=[one, two], Values=[100, 0], StatusCode="PartialData")
    second = [{"Id": "s2", "Timestamps": [one, end], "Values": [200, 999], "StatusCode": "Complete"},
              {"Id": "s1", "Timestamps": [one], "Values": [100], "StatusCode": "Complete"}]
    params = {"StartTime": start, "EndTime": end, "MetricDataQueries": storage_queries("bucket")}
    with Stubber(client) as stub:
        stub.add_response("get_metric_data", {"MetricDataResults": first, "NextToken": "next"}, params)
        stub.add_response("get_metric_data", {"MetricDataResults": second}, {**params, "NextToken": "next"})
        bucket = bucket_history(client, "bucket", "us-east-2", start, end)
        stub.assert_no_pending_responses()
    assert bucket.days[-2].size_bytes == 300 and bucket.days[-2].objects == 10
    assert bucket.days[-1].size_bytes == 0 and bucket.days[-1].objects == 0
    assert bucket.days[0].size_bytes is None and bucket.days[0].objects is None
    assert bucket.region == "us-east-2" and len(bucket.days) == 61
    with Stubber(client) as stub:
        stub.add_response("get_metric_data", {"MetricDataResults": [{**empty[0], "StatusCode": "PartialData"}]}, params)
        with pytest.raises(ValueError, match="Incomplete S3 metric"):
            bucket_history(client, "bucket", "us-east-2", start, end)
    with Stubber(client) as stub:
        stub.add_response("get_metric_data", {"MetricDataResults": []}, params)
        with pytest.raises(ValueError, match="omitted"):
            bucket_history(client, "bucket", "us-east-2", start, end)


def test_storage_calendar_and_service_names_in_cache_and_digest():
    """History spans two calendar months at year/leap boundaries; names retain AWS identity."""
    start, end = storage_window(datetime(2024, 4, 30, 15, tzinfo=timezone.utc))
    assert start.date() == date(2024, 2, 29) and end.hour == 0
    start, _ = storage_window(datetime(2026, 1, 31, tzinfo=timezone.utc))
    assert start.date() == date(2025, 11, 30)
    data = snapshot()
    data.current.services = [Charges(name="Amazon Simple Storage Service"), Charges(name="Amazon Simple Email Service")]
    assert data.current.services[0].model_dump()["display_name"] == "Amazon Simple Storage Service (S3)"
    assert Charges(name="Unknown service").display_name == "Unknown service"
    assert "Amazon Simple Email Service (SES)" in digest(data)
    data.storage = StorageSummary(start=start.date(), end=NOW.date(), buckets=[
        BucketStorage(name="empty", region="us-east-1"),
        BucketStorage(name="archive", region="us-east-2", days=[StorageDay(day=NOW.date(), size_bytes=2e9, objects=12)])])
    message = digest(data)
    assert "2.00 GB / 12.00 objects" in message and "empty (us-east-1): No data" in message


def test_metric_pagination_rejects_abandoned_partial_series():
    """A global next token cannot certify a metric omitted from later pages."""
    functions = snapshot().functions
    client = boto3.client("cloudwatch", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")
    expected = {"MetricDataQueries": metric_queries(functions),
                "StartTime": datetime(2026, 9, 1, tzinfo=timezone.utc), "EndTime": NOW}
    with Stubber(client) as stub:
        stub.add_response("get_metric_data", {"MetricDataResults": [
            {"Id": "f0m0", "Timestamps": [NOW-timedelta(days=3)], "Values": [7], "StatusCode": "PartialData"}],
            "NextToken": "next"}, expected)
        stub.add_response("get_metric_data", {"MetricDataResults": [
            {"Id": "f0m1", "Timestamps": [], "Values": [], "StatusCode": "Complete"}]},
            {**expected, "NextToken": "next"})
        with pytest.raises(ValueError, match="Incomplete CloudWatch metric pages"):
            collect_activity(client, functions, NOW)
        stub.assert_no_pending_responses()
