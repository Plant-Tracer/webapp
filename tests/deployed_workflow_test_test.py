"""Tests for the deployed workflow command and verification logic."""

import json
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests
from PIL import Image

import deployed_workflow_test
from app.schema import Trackpoint


def test_endpoint_only_uses_committed_reference_files():
    args = deployed_workflow_test.parse_args([
        "--endpoint", "https://prod.planttracer.com/",
    ])

    assert args.stack_name is None
    for fixture in (args.movie, args.reference_csv, args.reference_xlsx,
                    args.reference_traced_movie, args.reference_frame):
        assert fixture.is_file()


def test_deployment_info_reads_api_version():
    response_body = json.dumps({
        "stack_name": "prod",
        "DYNAMODB_TABLE_PREFIX": "prod-",
    }).encode("utf-8")

    class VersionHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # pylint: disable=invalid-name
            assert self.path == "/api/ver"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

    with ThreadingHTTPServer(("127.0.0.1", 0), VersionHandler) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            info = deployed_workflow_test.deployment_info(
                f"http://127.0.0.1:{server.server_port}/")
        finally:
            server.shutdown()
            thread.join()

    assert info.stack_name == "prod"
    assert info.dynamodb_table_prefix == "prod-"


def test_deployment_info_http_error_includes_response_body():
    response_body = b'{"error":true,"message":"S3 bucket has no CORS configuration"}'

    class UnavailableHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # pylint: disable=invalid-name
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

    with ThreadingHTTPServer(("127.0.0.1", 0), UnavailableHandler) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with pytest.raises(requests.HTTPError) as raised:
                deployed_workflow_test.deployment_info(
                    f"http://127.0.0.1:{server.server_port}/")
        finally:
            server.shutdown()
            thread.join()

    message = str(raised.value)
    assert "deployment identity request failed" in message
    assert "returned HTTP 503 Service Unavailable" in message
    assert "S3 bucket has no CORS configuration" in message


def test_validate_deployment_config_repairs_cors_before_workflow(monkeypatch):
    cors_configured = False
    configured_buckets = []
    eventbridge_buckets = []
    monkeypatch.setattr(deployed_workflow_test, "CORS_REPAIR_RECHECK_INTERVAL", 0)

    class ConfigHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # pylint: disable=invalid-name
            assert self.path == "/api/config-check"
            response_body = json.dumps({
                "dynamodb_ok": True,
                "dynamodb_message": "",
                "cors_ok": cors_configured,
                "cors_message": "" if cors_configured else "S3 bucket has no CORS configuration",
                "bucket_region_ok": True,
                "bucket_region_message": "",
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

    with ThreadingHTTPServer(("127.0.0.1", 0), ConfigHandler) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            def configure_cors(bucket):
                nonlocal cors_configured
                configured_buckets.append(bucket)
                cors_configured = True

            deployed_workflow_test.validate_deployment_config(
                f"http://127.0.0.1:{server.server_port}/",
                bucket="planttracer-test",
                cors_configurer=configure_cors,
                eventbridge_configurer=lambda bucket: eventbridge_buckets.append(bucket) or True,
            )
        finally:
            server.shutdown()
            thread.join()

    assert configured_buckets == ["planttracer-test"]
    assert eventbridge_buckets == ["planttracer-test"]


def reference_trackpoint():
    """Return a compact calibrated reference row."""
    return deployed_workflow_test.ReferenceTrackpoint.model_validate({
        "frame_number": 0,
        deployed_workflow_test.APEX_X_COLUMN: 10.5,
        deployed_workflow_test.APEX_Y_COLUMN: 20.5,
        deployed_workflow_test.RULER_0_X_COLUMN: 0,
        deployed_workflow_test.RULER_0_Y_COLUMN: 0,
        deployed_workflow_test.RULER_10_X_COLUMN: 10,
        deployed_workflow_test.RULER_10_Y_COLUMN: 0,
    })


def test_assert_position_accepts_dynamodb_decimals_and_enforces_tolerance():
    """DynamoDB Decimal coordinates compare numerically with CSV floats."""
    expected = reference_trackpoint()
    deployed_workflow_test.assert_position(
        Trackpoint(x=Decimal("10.5"), y=Decimal("20.5"), label="Apex", frame_number=0),
        expected,
        scale=1,
        frame_number=0,
    )
    with pytest.raises(AssertionError, match="Apex x"):
        deployed_workflow_test.assert_position(
            Trackpoint(x=Decimal("12.6"), y=Decimal("20.5"), label="Apex", frame_number=0),
            expected,
            scale=1,
            frame_number=0,
        )


def test_csv_trace_stats_requires_full_frame_coverage_and_motion():
    headers = ["frame_number", deployed_workflow_test.APEX_X_COLUMN,
               deployed_workflow_test.APEX_Y_COLUMN, deployed_workflow_test.RULER_0_X_COLUMN,
               deployed_workflow_test.RULER_0_Y_COLUMN,
               deployed_workflow_test.RULER_10_X_COLUMN,
               deployed_workflow_test.RULER_10_Y_COLUMN]
    rows = [headers, ["0", "10", "20", "0", "0", "10", "0"],
            ["1", "11", "21", "0", "0", "10", "0"],
            ["2", "12", "20", "0", "0", "10", "0"]]
    expected_start = deployed_workflow_test.ReferenceTrackpoint.model_validate(
        dict(zip(headers, rows[1])))
    expected_end = deployed_workflow_test.ReferenceTrackpoint.model_validate(
        dict(zip(headers, rows[-1])))

    stats = deployed_workflow_test.csv_trace_stats(rows, expected_start, expected_end)

    assert stats.rows == 3
    assert stats.first_frame == 0
    assert stats.last_frame == 2
    assert stats.unique_apex_positions == 3
    assert stats.apex_x_min == 10
    assert stats.apex_x_max == 12
    static_rows = [headers, rows[1], ["1", "10", "20", "0", "0", "10", "0"],
                   ["2", "10", "20", "0", "0", "10", "0"]]
    with pytest.raises(AssertionError, match="tracing did not produce motion"):
        deployed_workflow_test.csv_trace_stats(static_rows, expected_start, expected_end)


def test_trackpoint_comparison_accepts_small_drift_and_rejects_large_drift():
    headers = ["frame_number", deployed_workflow_test.APEX_X_COLUMN,
               deployed_workflow_test.APEX_Y_COLUMN, deployed_workflow_test.RULER_0_X_COLUMN,
               deployed_workflow_test.RULER_0_Y_COLUMN,
               deployed_workflow_test.RULER_10_X_COLUMN,
               deployed_workflow_test.RULER_10_Y_COLUMN]
    reference = [headers, ["0", "10", "20", "0", "0", "10", "0"],
                 ["1", "11", "21", "0", "0", "10", "0"]]
    within_tolerance = [headers, ["0", "11.5", "19", "1", "0", "11", "0"],
                        ["1", "12", "22", "1", "0", "11", "0"]]

    stats = deployed_workflow_test.compare_trackpoint_rows(
        within_tolerance, reference, export_name="CSV")

    assert stats.rows == 2
    assert stats.max_apex_delta_pixels == 1.5
    assert stats.max_ruler_delta_pixels == 1
    outside_tolerance = [headers, ["0", "12.1", "20", "0", "0", "10", "0"],
                         reference[2]]
    with pytest.raises(AssertionError, match="differs by 2.10 pixels"):
        deployed_workflow_test.compare_trackpoint_rows(
            outside_tolerance, reference, export_name="CSV")


def test_rendering_comparison_accepts_small_mean_channel_drift(tmp_path):
    reference = tmp_path / "reference.png"
    actual = tmp_path / "actual.png"
    movie = tmp_path / "downloaded.mov"
    Image.new("RGB", (2, 2), (100, 100, 100)).save(reference)
    Image.new("RGB", (2, 2), (98, 98, 98)).save(actual)
    movie.write_bytes(b"movie")

    stats = deployed_workflow_test.assert_renderings_match(reference, actual, movie)

    assert stats.mean_absolute_channel_delta == 2
    assert (tmp_path / "actual-difference.png").is_file()


def test_rendering_mismatch_reports_reference_actual_and_movie_paths(tmp_path):
    reference = tmp_path / "reference.png"
    actual = tmp_path / "actual.png"
    movie = tmp_path / "downloaded.mov"
    Image.new("RGB", (2, 2), "white").save(reference)
    Image.new("RGB", (2, 2), "black").save(actual)
    movie.write_bytes(b"movie")

    with pytest.raises(AssertionError) as raised:
        deployed_workflow_test.assert_renderings_match(reference, actual, movie)

    message = str(raised.value)
    assert "meaningfully differs" in message
    assert f"reference_rendering={reference.resolve()}" in message
    assert f"actual_rendering={actual.resolve()}" in message
    assert f"downloaded_movie={movie.resolve()}" in message
    assert f"difference_rendering={tmp_path / 'actual-difference.png'}" in message
    assert "differing_pixels=4/4" in message
    assert "max_channel_delta=255" in message
    assert "mean_absolute_channel_delta=255.000" in message
    assert (tmp_path / "actual-difference.png").is_file()
