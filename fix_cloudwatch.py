"""
demo code for zappa - how to set the cloudwatch retention
"""

import json
import logging
import boto3

logger = logging.getLogger(__name__)

# https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups

def set_cloudwatch_log_retention(log_group_name, retention_days):
    """
    Set the retention policy for a CloudWatch Logs log group.
    """
    logs_client = boto3.client('logs')
    try:
        logs_client.put_retention_policy(
            logGroupName=log_group_name,
            retentionInDays=retention_days
        )
        print(f"Set CloudWatch log retention for {log_group_name} to {retention_days} days.")
    except Exception as e:      # pylint: disable=broad-exception-caught
        print(f"Failed to set CloudWatch log retention: {str(e)}")

if __name__=="__main__":
    with open("zappa_settings.json","r") as f:
        zappa_conf = json.load(f)
    for (name,conf) in zappa_conf.items():
        try:
            retention_days = int(conf['cloudwatch_retention_days'])
        except KeyError:
            continue
        log_group_name = '/aws/lambda/' + conf['project_name'] + name
        print("Setting",log_group_name,"to",retention_days,"days")
        set_cloudwatch_log_retention(log_group_name,retention_days)
