"""Least-privilege contracts for Lambda DynamoDB access."""

from pathlib import Path

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DYNAMODB_ACTIONS = {
    "dynamodb:BatchGetItem",
    "dynamodb:BatchWriteItem",
    "dynamodb:ConditionCheckItem",
    "dynamodb:DeleteItem",
    "dynamodb:DescribeTable",
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    "dynamodb:Query",
    "dynamodb:Scan",
    "dynamodb:UpdateItem",
}


@pytest.mark.parametrize("role_name", ["LambdaWebExecutionRole", "LambdaResizeExecutionRole"])
def test_lambda_dynamodb_policy_matches_approved_operations(role_name):
    """Keep both runtime roles aligned with audited and retained operations."""
    template = yaml.load(  # noqa: S506 - local trusted CloudFormation source
        (PROJECT_ROOT / "template.yaml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    statements = template["Resources"][role_name]["Properties"]["Policies"][0][
        "PolicyDocument"
    ]["Statement"]
    dynamodb_statement = next(
        statement for statement in statements
        if any(action.startswith("dynamodb:") for action in statement.get("Action", []))
    )

    assert set(dynamodb_statement["Action"]) == EXPECTED_DYNAMODB_ACTIONS
    assert len(dynamodb_statement["Resource"]) == 2
