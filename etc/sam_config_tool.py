#!/usr/bin/env python3
"""
General-purpose tool for template.yaml and samconfig.toml.
Parses SAM config and runs commands: ssh-clean (ssh-keygen -R hostname), ssh (SSH to VM), ssm-start-session (AWS SSM session).
"""
import argparse
import os
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
    """Load samconfig.toml and return (stack_name, region, hostname, host_label).

    Hostname is derived from stack name: stack_name.base_domain (e.g. mystack.planttracer.com).
    host_label is the stack_name (for callers that expect a label).
    """
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
    base_domain = overrides.get("BaseDomain", "planttracer.com").strip() or "planttracer.com"
    hostname = f"{stack_name}.{base_domain}"
    return (stack_name, region, hostname, stack_name)


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
    parser.add_argument(
        "command",
        choices=["ssh-clean", "ssh", "ssm-start-session"],
        help="ssh-clean: ssh-keygen -R hostname; ssh: SSH to VM; ssm-start-session: AWS SSM session",
    )
    args = parser.parse_args()

    if args.command == "ssh-clean":
        cmd_ssh_clean(args.samconfig)
    elif args.command == "ssh":
        cmd_ssh(args.samconfig, identity_file=getattr(args, "identity_file", None))
    elif args.command == "ssm-start-session":
        cmd_ssm_start_session(args.samconfig)
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
