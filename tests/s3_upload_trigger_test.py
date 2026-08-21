"""Tests for preserving shared-bucket notification destinations."""

from etc.s3_upload_trigger import (
    EVENTBRIDGE_CONFIGURATION,
    configure_bucket_eventbridge,
    configuration_with_eventbridge,
)


class RecordingS3Client:
    """Small stateful S3 notification implementation for configuration logic."""

    def __init__(self, configuration):
        self.configuration = configuration
        self.put_calls = []

    def get_bucket_notification_configuration(self, *, Bucket):
        del Bucket
        return self.configuration

    def put_bucket_notification_configuration(self, *, Bucket, NotificationConfiguration):
        self.put_calls.append((Bucket, NotificationConfiguration))
        self.configuration = NotificationConfiguration


def test_configuration_with_eventbridge_preserves_existing_destinations():
    current = {
        "ResponseMetadata": {"RequestId": "not writable"},
        "TopicConfigurations": [{"Id": "topic-1"}],
        "QueueConfigurations": [{"Id": "queue-1"}],
        "LambdaFunctionConfigurations": [{"Id": "lambda-1"}],
    }

    updated = configuration_with_eventbridge(current)

    assert updated == {
        "TopicConfigurations": [{"Id": "topic-1"}],
        "QueueConfigurations": [{"Id": "queue-1"}],
        "LambdaFunctionConfigurations": [{"Id": "lambda-1"}],
        EVENTBRIDGE_CONFIGURATION: {},
    }


def test_configure_bucket_eventbridge_is_idempotent_and_preserves_destinations():
    client = RecordingS3Client({"QueueConfigurations": [{"Id": "queue-1"}]})

    assert configure_bucket_eventbridge("archive", client=client) is True
    assert client.put_calls == [("archive", {
        "QueueConfigurations": [{"Id": "queue-1"}],
        EVENTBRIDGE_CONFIGURATION: {},
    })]
    assert configure_bucket_eventbridge("archive", client=client) is False
    assert len(client.put_calls) == 1
