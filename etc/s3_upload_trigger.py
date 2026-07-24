#!/usr/bin/env python3
"""Inspect or safely enable S3 delivery to EventBridge on the shared bucket."""

import argparse
import json
import os

import boto3


TOPIC_CONFIGURATIONS = "TopicConfigurations"
QUEUE_CONFIGURATIONS = "QueueConfigurations"
LAMBDA_CONFIGURATIONS = "LambdaFunctionConfigurations"
EVENTBRIDGE_CONFIGURATION = "EventBridgeConfiguration"
ALLOWED_CONFIGURATION_KEYS = (
    TOPIC_CONFIGURATIONS,
    QUEUE_CONFIGURATIONS,
    LAMBDA_CONFIGURATIONS,
    EVENTBRIDGE_CONFIGURATION,
)


def configuration_with_eventbridge(configuration):
    """Return the writable notification fields with EventBridge enabled."""
    updated = {
        key: value
        for key, value in configuration.items()
        if key in ALLOWED_CONFIGURATION_KEYS and key != EVENTBRIDGE_CONFIGURATION
    }
    updated[EVENTBRIDGE_CONFIGURATION] = {}
    return updated


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the merged configuration")
    parser.add_argument(
        "--confirm-bucket",
        help="required with --apply; must exactly match PLANTTRACER_S3_BUCKET",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bucket = os.environ.get("PLANTTRACER_S3_BUCKET", "").strip()
    if not bucket:
        raise SystemExit("PLANTTRACER_S3_BUCKET must be set")
    if args.apply and args.confirm_bucket != bucket:
        raise SystemExit("--confirm-bucket must exactly match PLANTTRACER_S3_BUCKET")

    client = boto3.client("s3")
    current = client.get_bucket_notification_configuration(Bucket=bucket)
    print(json.dumps(current, indent=2, default=str))
    if EVENTBRIDGE_CONFIGURATION in current:
        print(f"EventBridge delivery is already enabled for {bucket}.")
        return 0
    if not args.apply:
        print(f"EventBridge delivery is disabled for {bucket}; no changes made.")
        return 0

    updated = configuration_with_eventbridge(current)
    client.put_bucket_notification_configuration(
        Bucket=bucket,
        NotificationConfiguration=updated,
    )
    verified = client.get_bucket_notification_configuration(Bucket=bucket)
    if EVENTBRIDGE_CONFIGURATION not in verified:
        raise RuntimeError(f"EventBridge delivery was not enabled for {bucket}")
    print(f"EventBridge delivery enabled and verified for {bucket}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
