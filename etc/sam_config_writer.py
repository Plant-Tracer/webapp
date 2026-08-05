#!/usr/bin/env python3
"""Create or update SAM config files with TOML-aware quoting."""

import argparse
from pathlib import Path

import tomlkit

DEFAULT_ENVIRONMENT = "default"
DEPLOY = "deploy"
PARAMETERS = "parameters"
STACK_NAME = "stack_name"


def bootstrap_config(config_path: str, requested_stack_name: str | None) -> bool:
    """Create or update a SAM config and return whether the file changed."""
    path = Path(config_path)
    if path.exists():
        document = tomlkit.parse(path.read_text(encoding="utf-8"))
    else:
        document = tomlkit.document()
        document.add("version", 0.1)

    changed = False
    if requested_stack_name:
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
        if params.get(STACK_NAME) != requested_stack_name:
            params[STACK_NAME] = requested_stack_name
            changed = True

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
    args = parser.parse_args()

    changed = bootstrap_config(args.samconfig, args.stack_name)
    action = "Updated" if changed else "Verified"
    print(f"{action} {args.samconfig}")


if __name__ == "__main__":
    main()
