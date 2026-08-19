#!/usr/bin/env python3
"""Create or update SAM config files with TOML-aware quoting."""

import argparse
import json
import shlex
from pathlib import Path

import tomlkit

DEFAULT_ENVIRONMENT = "default"
DEPLOY = "deploy"
DYNAMODB_TABLE_PREFIX = "DynamoDBTablePrefix"
PARAMETERS = "parameters"
PARAMETER_OVERRIDES = "parameter_overrides"
STACK_NAME = "stack_name"


def _set_parameter_override(params, name: str, value: str) -> bool:
    """Set one SAM parameter override while preserving the other entries."""
    raw_overrides = params.get(PARAMETER_OVERRIDES, "")
    tokens = shlex.split(raw_overrides) if isinstance(raw_overrides, str) else []
    overrides: list[tuple[str, str]] = []
    found = False
    for token in tokens:
        key, separator, old_value = token.partition("=")
        if not separator:
            continue
        if key == name:
            overrides.append((key, value))
            found = True
        else:
            overrides.append((key, old_value))
    if not found:
        overrides.append((name, value))
    updated = " ".join(f"{key}={json.dumps(item_value)}" for key, item_value in overrides)
    if raw_overrides == updated:
        return False
    params[PARAMETER_OVERRIDES] = updated
    return True


def bootstrap_config(config_path: str, requested_stack_name: str | None,
                     requested_dynamodb_prefix: str | None = None) -> bool:
    """Create or update a SAM config and return whether the file changed."""
    path = Path(config_path)
    if path.exists():
        document = tomlkit.parse(path.read_text(encoding="utf-8"))
    else:
        document = tomlkit.document()
        document.add("version", 0.1)

    changed = False
    if requested_stack_name or requested_dynamodb_prefix:
        environment = document.get(DEFAULT_ENVIRONMENT)
        if environment is None:
            environment = tomlkit.table()
            document.add(DEFAULT_ENVIRONMENT, environment)
            changed = True
        deploy = environment.get(DEPLOY)
        if deploy is None:
            deploy = tomlkit.table()
            environment.add(DEPLOY, deploy)
            changed = True
        params = deploy.get(PARAMETERS)
        if params is None:
            params = tomlkit.table()
            deploy.add(PARAMETERS, params)
            changed = True
        if requested_stack_name and params.get(STACK_NAME) != requested_stack_name:
            params[STACK_NAME] = requested_stack_name
            changed = True

    if requested_dynamodb_prefix:
        normalized_prefix = f"{requested_dynamodb_prefix.rstrip('-')}-"
        changed = _set_parameter_override(
            params, DYNAMODB_TABLE_PREFIX, normalized_prefix) or changed

    if not path.exists() or changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomlkit.dumps(document), encoding="utf-8")
        return True
    return False


def main() -> None:
    """Run the SAM config writer."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samconfig", default="samconfig.toml", metavar="FILE")
    parser.add_argument("--stack-name")
    parser.add_argument("--dynamodb-table-prefix")
    args = parser.parse_args()

    changed = bootstrap_config(
        args.samconfig, args.stack_name, args.dynamodb_table_prefix)
    action = "Updated" if changed else "Verified"
    print(f"{action} {args.samconfig}")


if __name__ == "__main__":
    main()
