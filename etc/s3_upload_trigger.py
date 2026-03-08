#!/usr/bin/env python3
"""
Idempotently add S3 bucket notification so that objects created under prefix
uploads/ invoke the lambda-resize Lambda. If the trigger is already present,
leave the bucket notification unchanged. Intended to be run from bootstrap.sh.
Uses boto3 (no extra deps beyond the app).
"""
import os
import sys

# Add src so we can run from repo root or etc/
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import boto3  # pylint: disable=wrong-import-position

# Unique id for our Lambda config so we can detect it when re-running
TRIGGER_ID = "PlantTracerUploads"
UPLOAD_PREFIX = "uploads/"


def main() -> int:
    bucket = os.environ.get("PLANTTRACER_S3_BUCKET", "").strip()
    lambda_arn = os.environ.get("LAMBDA_RESIZE_ARN", "").strip()
    if not bucket or not lambda_arn:
        print("s3_upload_trigger: PLANTTRACER_S3_BUCKET and LAMBDA_RESIZE_ARN must be set", file=sys.stderr)
        return 0  # Idempotent: skip without failing bootstrap
    try:
        client = boto3.client("s3")
        cfg = client.get_bucket_notification_configuration(Bucket=bucket)
        lambdas = list(cfg.get("LambdaFunctionConfigurations") or [])
        if any(c.get("Id") == TRIGGER_ID for c in lambdas):
            print("s3_upload_trigger: trigger already present, skipping")
            return 0
        lambdas.append({
            "Id": TRIGGER_ID,
            "LambdaFunctionArn": lambda_arn,
            "Events": ["s3:ObjectCreated:*"],
            "Filter": {
                "Key": {"FilterRules": [{"Name": "prefix", "Value": UPLOAD_PREFIX}]},
            },
        })
        # Preserve existing config; only set LambdaFunctionConfigurations (merge with existing)
        allowed = {"TopicConfigurations", "QueueConfigurations", "LambdaFunctionConfigurations", "EventBridgeConfiguration"}
        payload = {k: v for k, v in cfg.items() if k in allowed and v}
        payload["LambdaFunctionConfigurations"] = lambdas
        client.put_bucket_notification_configuration(
            Bucket=bucket,
            NotificationConfiguration=payload,
        )
        print("s3_upload_trigger: added Lambda trigger for prefix uploads/")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"s3_upload_trigger: failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
