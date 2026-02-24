#!/usr/bin/env python3
"""
General-purpose tool for template.yaml and samconfig.toml.
Parses SAM config and runs commands: ssh-clean (ssh-keygen -R hostname), ssh / ssm-start-session (SSM session).
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

import tomllib


def _find_deploy_parameters(config: dict) -> dict | None:
    """Find first [env.deploy.parameters] section in loaded TOML."""
    for _, top_val in config.items():
        if not isinstance(top_val, dict):
            continue
        deploy = top_val.get("deploy")
        if not isinstance(deploy, dict):
            continue
        params = deploy.get("parameters")
        if isinstance(params, dict):
            return params
    return None


def _parse_parameter_overrides(overrides_str: str) -> dict[str, str]:
    """Parse parameter_overrides string into key=value dict (values may be quoted)."""
    result: dict[str, str] = {}
    # Match Key="value" or Key="value with spaces"
    for match in re.finditer(r'(\w+)="([^"]*)"', overrides_str):
        result[match.group(1)] = match.group(2)
    return result


def load_sam_config(config_path: str) -> tuple[str, str, str, str]:
    """Load samconfig.toml and return (stack_name, region, hostname, host_label)."""
    path = Path(config_path)
    if not path.exists():
        sys.exit(f"Config file not found: {config_path}")

    with path.open("rb") as f:
        config = tomllib.load(f)

    params = _find_deploy_parameters(config)
    if not params:
        sys.exit(f"No [env.deploy.parameters] section in {config_path}")

    stack_name = params.get("stack_name")
    if isinstance(stack_name, str):
        stack_name = stack_name.strip('"')
    else:
        sys.exit("stack_name not found in deploy.parameters")

    region = params.get("region", "us-east-1")
    if isinstance(region, str):
        region = region.strip('"')
    else:
        region = "us-east-1"

    overrides_str = params.get("parameter_overrides")
    if not isinstance(overrides_str, str):
        sys.exit("parameter_overrides not found in deploy.parameters")

    overrides = _parse_parameter_overrides(overrides_str)
    host_label = overrides.get("HostLabel", "").strip()
    base_domain = overrides.get("BaseDomain", "").strip()
    if not host_label or not base_domain:
        sys.exit("HostLabel or BaseDomain missing in parameter_overrides")

    hostname = f"{host_label}.{base_domain}"
    return (stack_name, region, hostname, host_label)


def cmd_ssh_clean(config_path: str) -> None:
    """Remove host key for the VM hostname (ssh-keygen -R hostname)."""
    _stack, _region, hostname, _ = load_sam_config(config_path)
    if not hostname:
        return
    print(f"Removing old SSH host key for {hostname}...", flush=True)
    result = subprocess.run(
        ["ssh-keygen", "-R", hostname],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 and "not found" not in (result.stderr or "").lower():
        print(result.stderr or result.stdout, file=sys.stderr, end="")


def cmd_ssh(config_path: str) -> None:
    """Start SSM session to the stack's EC2 instance."""
    stack_name, region, _hostname, _ = load_sam_config(config_path)
    result = subprocess.run(
        [
            "aws",
            "ec2",
            "describe-instances",
            "--region",
            region,
            "--filters",
            f"Name=tag:Name,Values=PlantTracer-{stack_name}-app",
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
    target = instance_id[0]
    print(f"Connecting to {target}...", flush=True)
    subprocess.run(
        ["aws", "ssm", "start-session", "--target", target, "--region", region],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="General-purpose tool for template.yaml and samconfig.toml",
    )
    parser.add_argument(
        "config",
        metavar="samconfig.toml",
        help="Path to samconfig.toml",
    )
    parser.add_argument(
        "command",
        choices=["ssh-clean", "ssh", "ssm-start-session"],
        help="ssh-clean: run ssh-keygen -R hostname; ssh / ssm-start-session: start SSM session to VM",
    )
    args = parser.parse_args()

    if args.command == "ssh-clean":
        cmd_ssh_clean(args.config)
    elif args.command in ("ssh", "ssm-start-session"):
        cmd_ssh(args.config)
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
