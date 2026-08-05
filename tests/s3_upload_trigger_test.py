"""Tests for preserving shared-bucket notification destinations."""

from etc.s3_upload_trigger import (
    EVENTBRIDGE_CONFIGURATION,
    configuration_with_eventbridge,
)


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
