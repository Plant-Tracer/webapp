"""Tests for the deployed workflow command and verification logic."""

import json
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

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
