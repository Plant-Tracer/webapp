#!/usr/bin/env python3
"""
General-purpose tool for template.yaml and samconfig.toml.
Parses SAM config, safely bootstraps config files, and runs operational commands.
"""
import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

import tomllib

DEPLOY = "deploy"
PARAMETERS = "parameters"
PARAMETER_OVERRIDES = "parameter_overrides"
STACK_NAME = "stack_name"


def _find_deploy_parameters(config: dict) -> dict | None:
    """Find first [env.deploy.parameters] section in loaded TOML."""
    for _, top_val in config.items():
        if not isinstance(top_val, dict):
            continue
        deploy = top_val.get(DEPLOY)
        if not isinstance(deploy, dict):
            continue
        params = deploy.get(PARAMETERS)
        if isinstance(params, dict):
            return params
    return None


def _parse_parameter_overrides(overrides_str: str) -> dict[str, str]:
    """Parse SAM parameter_overrides using shell-style quoting."""
    result: dict[str, str] = {}
    for token in shlex.split(overrides_str):
        key, separator, value = token.partition("=")
        if separator and key:
            result[key] = value
    return result


def load_toml(config_path: str) -> dict:
    """Load one SAM TOML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with path.open("rb") as config_file:
        return tomllib.load(config_file)


def deploy_parameters(config_path: str) -> dict:
    """Return the first SAM deploy-parameters table."""
    params = _find_deploy_parameters(load_toml(config_path))
    if params is None:
        raise ValueError(f"No [env.deploy.parameters] section in {config_path}")
    return params


def stack_name(config_path: str) -> str:
    """Return the configured CloudFormation stack name."""
    value = deploy_parameters(config_path).get(STACK_NAME)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{STACK_NAME} not found in deploy.parameters")
    return value.strip()


def parameter_override(config_path: str, name: str) -> str:
    """Return one value from SAM's parameter_overrides string."""
    value = deploy_parameters(config_path).get(PARAMETER_OVERRIDES)
    if not isinstance(value, str):
        raise ValueError(f"{PARAMETER_OVERRIDES} not found in deploy.parameters")
    overrides = _parse_parameter_overrides(value)
    if name not in overrides:
        raise ValueError(f"{name} not found in {PARAMETER_OVERRIDES}")
    return overrides[name]


def load_sam_config(config_path: str) -> tuple[str, str, str, str]:
    """Load samconfig.toml and return (stack_name, region, hostname, host_label).

    Hostname is derived from stack name: stack_name.base_domain (e.g. mystack.planttracer.com).
    host_label is the stack_name (for callers that expect a label).
    """
    try:
        params = deploy_parameters(config_path)
        configured_stack_name = stack_name(config_path)
    except (FileNotFoundError, ValueError) as error:
        sys.exit(str(error))

    region = params.get("region", "us-east-1")
    if isinstance(region, str):
        region = region.strip('"')
    else:
        region = "us-east-1"

    overrides_str = params.get(PARAMETER_OVERRIDES)
    if not isinstance(overrides_str, str):
        sys.exit(f"{PARAMETER_OVERRIDES} not found in deploy.parameters")

    overrides = _parse_parameter_overrides(overrides_str)
    base_domain = overrides.get("BaseDomain", "planttracer.com").strip() or "planttracer.com"
    hostname = f"{configured_stack_name}.{base_domain}"
    return (configured_stack_name, region, hostname, configured_stack_name)


def cmd_ssh_clean(config_path: str) -> None:
    """Remove host key for the VM hostname (ssh-keygen -R hostname)."""
    _stack, _region, hostname, _ = load_sam_config(config_path)
    if not hostname:
        return
    result = subprocess.run(
        ["ssh-keygen", "-R", hostname],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 and "not found" not in (result.stderr or "").lower():
        print("No previous key in .ssh/known_hosts:")
        print(result.stderr or result.stdout, file=sys.stderr, end="")
    print(f"Removed old SSH host key for {hostname}...", flush=True)
    print("")
    print(f"Access with ssh ubuntu@{hostname}")


def _get_instance_id(config_path: str) -> tuple[str, str]:
    """Resolve stack's running EC2 instance id and region from config. Returns (instance_id, region)."""
    stack_name, region, _hostname, _ = load_sam_config(config_path)
    result = subprocess.run(
        [
            "aws",
            "ec2",
            "describe-instances",
            "--region",
            region,
            "--filters",
            f"Name=tag:Name,Values={stack_name}-app",
            "Name=instance-state-name,Values=running",
            "--query",
            "Reservations[].Instances[].InstanceId",
            "--output",
            "text",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        sys.exit(result.returncode)
    instance_id = (result.stdout or "").strip().split()
    if not instance_id:
        print(
            f"Error: No running instance found for stack {stack_name}",
            file=sys.stderr,
        )
        sys.exit(1)
    return (instance_id[0], region)


def cmd_ssh(config_path: str, identity_file: str | None = None) -> None:
    """Run SSH to the stack's VM (hostname from config). Replaces process so ~^Z works."""
    _stack, _region, hostname, _ = load_sam_config(config_path)
    cmd = ["ssh"]
    if identity_file:
        cmd.extend(["-i", str(Path(identity_file).expanduser())])
    cmd.append(f"ubuntu@{hostname}")
    print("Running:", " ".join(cmd), flush=True)
    os.execvp("ssh", cmd)


def cmd_ssm_start_session(config_path: str) -> None:
    """Start AWS SSM session to the stack's EC2 instance. Replaces process for TTY."""
    target, region = _get_instance_id(config_path)
    cmd = [
        "aws",
        "ssm",
        "start-session",
        "--target",
        target,
        "--region",
        region,
    ]
    print("Running:", " ".join(cmd), flush=True)
    os.execvp("aws", cmd)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="General-purpose tool for template.yaml and samconfig.toml",
    )
    parser.add_argument(
        "--samconfig",
        metavar="FILE",
        default="samconfig.toml",
        help="Path to samconfig.toml (default: samconfig.toml)",
    )
    parser.add_argument(
        "-i",
        "--identity",
        metavar="FILE",
        dest="identity_file",
        help="SSH identity (private key) file, e.g. ~/.ssh/plantadmin.pem",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("stack-name", help="print configured stack_name")
    parameter_parser = subparsers.add_parser(
        "parameter-override",
        help="print one value from parameter_overrides",
    )
    parameter_parser.add_argument("--name", required=True)
    subparsers.add_parser("ssh-clean", help="remove the configured hostname from known_hosts")
    subparsers.add_parser("ssh", help="SSH to the configured stack")
    subparsers.add_parser("ssm-start-session", help="start an AWS SSM session")
    args = parser.parse_args()

    try:
        if args.command == "stack-name":
            print(stack_name(args.samconfig))
        elif args.command == "parameter-override":
            print(parameter_override(args.samconfig, args.name))
        elif args.command == "ssh-clean":
            cmd_ssh_clean(args.samconfig)
        elif args.command == "ssh":
            cmd_ssh(args.samconfig, identity_file=getattr(args, "identity_file", None))
        elif args.command == "ssm-start-session":
            cmd_ssm_start_session(args.samconfig)
        else:
            parser.error(f"Unknown command: {args.command}")
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
