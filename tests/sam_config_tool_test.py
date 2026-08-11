"""Tests for safe selection and writing of per-stack SAM configuration."""

import os
import subprocess
import tomllib
from pathlib import Path

from etc import sam_config_tool, sam_config_writer

STACK_ENVIRONMENT_VARIABLE = "STACK"
STACK_NAME_ENVIRONMENT_VARIABLE = "STACK_NAME"
DYNAMODB_PREFIX_ENVIRONMENT_VARIABLE = "DYNAMODB_TABLE_PREFIX"


def _write_config(path: Path, stack_name: str, prefix: str = "prod-") -> None:
    path.write_text(
        "version = 0.1\n\n"
        "[default.deploy.parameters]\n"
        f'stack_name = "{stack_name}"\n'
        f'parameter_overrides = \'BaseDomain="planttracer.com" '
        f'DynamoDBTablePrefix="{prefix}" LogLevel="warning with spaces"\'\n',
        encoding="utf-8",
    )


def _make_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        STACK_ENVIRONMENT_VARIABLE,
        STACK_NAME_ENVIRONMENT_VARIABLE,
        DYNAMODB_PREFIX_ENVIRONMENT_VARIABLE,
    ):
        environment.pop(name, None)
    return environment


def test_parameter_overrides_preserve_quoted_spaces(tmp_path: Path) -> None:
    config_path = tmp_path / "quoted.toml"
    _write_config(config_path, "slg-dev")

    assert sam_config_tool.stack_name(str(config_path)) == "slg-dev"
    assert (
        sam_config_tool.parameter_override(str(config_path), "DynamoDBTablePrefix")
        == "prod-"
    )
    assert (
        sam_config_tool.parameter_override(str(config_path), "LogLevel")
        == "warning with spaces"
    )


def test_bootstrap_config_creates_valid_quoted_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "configs" / "slg-dev.toml"

    assert sam_config_writer.bootstrap_config(str(config_path), 'slg-"dev')

    with config_path.open("rb") as config_file:
        config = tomllib.load(config_file)
    assert config["default"]["deploy"]["parameters"]["stack_name"] == 'slg-"dev'


def test_bootstrap_config_preserves_existing_values(tmp_path: Path) -> None:
    config_path = tmp_path / "existing.toml"
    _write_config(config_path, "slg-dev")
    original_overrides = sam_config_tool.deploy_parameters(str(config_path))[
        "parameter_overrides"
    ]

    assert not sam_config_writer.bootstrap_config(str(config_path), "slg-dev")

    params = sam_config_tool.deploy_parameters(str(config_path))
    assert params["stack_name"] == "slg-dev"
    assert params["parameter_overrides"] == original_overrides


def test_make_stack_name_alias_selects_per_stack_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "samconfigs"
    config_dir.mkdir()
    config_path = config_dir / "slg-dev.toml"
    _write_config(config_path, "slg-dev")

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "sam-config-show",
            "STACK_NAME=slg-dev",
            "DYNAMODB_TABLE_PREFIX=prod",
            f"SAM_CONFIG_DIR={config_dir}",
        ],
        cwd=Path(__file__).parents[1],
        env=_make_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert f"SAM_CONFIG={config_path}" in result.stdout
    assert "STACK_NAME=slg-dev" in result.stdout
    assert "CONFIG_STACK_NAME=slg-dev" in result.stdout
    assert "DYNAMODB_TABLE_PREFIX=prod-" in result.stdout


def test_make_rejects_conflicting_stack_selectors(tmp_path: Path) -> None:
    config_path = tmp_path / "slg-dev.toml"
    _write_config(config_path, "slg-dev")

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "sam-config-path-check",
            "STACK=prod",
            "STACK_NAME=slg-dev",
            f"SAM_CONFIG={config_path}",
        ],
        cwd=Path(__file__).parents[1],
        env=_make_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "STACK_NAME=slg-dev conflicts with STACK=prod" in result.stdout


def test_make_rejects_conflicting_dynamodb_prefix(tmp_path: Path) -> None:
    config_path = tmp_path / "slg-dev.toml"
    _write_config(config_path, "slg-dev")

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "sam-config-path-check",
            "STACK_NAME=slg-dev",
            "DYNAMODB_TABLE_PREFIX=test",
            f"SAM_CONFIG={config_path}",
        ],
        cwd=Path(__file__).parents[1],
        env=_make_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "DYNAMODB_TABLE_PREFIX=test" in result.stdout
    assert "configures prod-" in result.stdout


def test_guided_bootstrap_allows_missing_dynamodb_override(tmp_path: Path) -> None:
    config_path = tmp_path / "new-stack.toml"

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "sam-config-guided-bootstrap",
            "STACK_NAME=new-stack",
            "DYNAMODB_TABLE_PREFIX=test",
            f"SAM_CONFIG={config_path}",
        ],
        cwd=Path(__file__).parents[1],
        env=_make_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert sam_config_tool.stack_name(str(config_path)) == "new-stack"
