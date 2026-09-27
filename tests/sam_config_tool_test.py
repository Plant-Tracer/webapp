"""Tests for safe selection and writing of per-stack SAM configuration."""

import os
import subprocess
import tomllib
from pathlib import Path

import pytest

from app.deployment_metadata import DeployMetadata
from etc import sam_config_tool, sam_config_writer

STACK_ENVIRONMENT_VARIABLE = "STACK"
STACK_NAME_ENVIRONMENT_VARIABLE = "STACK_NAME"
DYNAMODB_PREFIX_ENVIRONMENT_VARIABLE = "DYNAMODB_TABLE_PREFIX"


@pytest.mark.parametrize("failed_artifact", [None, "resize", "web"])
def test_make_deploy_metadata_stamp(tmp_path: Path, failed_artifact: str | None) -> None:
    resize_dir = tmp_path / "LambdaResizeFunction" / "resize_app"
    web_dir = tmp_path / "LambdaWebFunction" / "app"
    resize_dir.mkdir(parents=True)
    web_dir.mkdir(parents=True)
    if failed_artifact is not None:
        failed_dir = resize_dir if failed_artifact == "resize" else web_dir
        (failed_dir / "deploy_metadata.json").mkdir()

    result = subprocess.run(
        ["make", "stamp-sam-deploy-metadata", f"SAM_BUILD_DIR={tmp_path}"],
        capture_output=True, text=True, check=False,
    )

    if failed_artifact is not None:
        assert result.returncode != 0
        assert "Stamped deploy metadata" not in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        resize = DeployMetadata.model_validate_json(
            (resize_dir / "deploy_metadata.json").read_text(encoding="utf-8"))
        web = DeployMetadata.model_validate_json(
            (web_dir / "deploy_metadata.json").read_text(encoding="utf-8"))
        assert resize.deployed_at == web.deployed_at
        assert resize.deployed_at.endswith("Z")


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


def test_bootstrap_config_updates_stack_and_dynamodb_prefix(tmp_path: Path) -> None:
    config_path = tmp_path / "existing.toml"
    _write_config(config_path, "prod")

    assert sam_config_writer.bootstrap_config(
        str(config_path), "slg-dev", "slg-dev")

    assert sam_config_tool.stack_name(str(config_path)) == "slg-dev"
    assert (
        sam_config_tool.parameter_override(str(config_path), "DynamoDBTablePrefix")
        == "slg-dev-"
    )
    assert (
        sam_config_tool.parameter_override(str(config_path), "LogLevel")
        == "warning with spaces"
    )


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


def test_make_stack_name_overrides_stack_selector(tmp_path: Path) -> None:
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

    assert result.returncode == 0, result.stdout + result.stderr
    assert sam_config_tool.stack_name(str(config_path)) == "slg-dev"
    assert (
        sam_config_tool.parameter_override(str(config_path), "DynamoDBTablePrefix")
        == "slg-dev-"
    )


def test_make_cli_prefix_updates_sam_config(tmp_path: Path) -> None:
    config_path = tmp_path / "slg-dev.toml"
    _write_config(config_path, "slg-dev")
    environment = _make_environment()
    environment[STACK_NAME_ENVIRONMENT_VARIABLE] = "slg-dev"
    environment[DYNAMODB_PREFIX_ENVIRONMENT_VARIABLE] = "test"

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "sam-config-path-check",
            f"SAM_CONFIG={config_path}",
        ],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        sam_config_tool.parameter_override(str(config_path), "DynamoDBTablePrefix")
        == "test-"
    )


def test_make_stack_name_overrides_config_and_defaults_prefix(tmp_path: Path) -> None:
    config_path = tmp_path / "slg-dev.toml"
    _write_config(config_path, "prod")
    environment = _make_environment()
    environment[STACK_NAME_ENVIRONMENT_VARIABLE] = "slg-dev"

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "sam-config-path-check",
            f"SAM_CONFIG={config_path}",
        ],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert sam_config_tool.stack_name(str(config_path)) == "slg-dev"
    assert (
        sam_config_tool.parameter_override(str(config_path), "DynamoDBTablePrefix")
        == "slg-dev-"
    )


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
