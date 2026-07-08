"""Application version source tests."""

from pathlib import Path
import tomllib

from app.constants import PYPROJECT_PROJECT, PYPROJECT_VERSION, __version__, pyproject_version


def test_application_version_matches_pyproject():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject_path.open("rb") as stream:
        pyproject = tomllib.load(stream)
    assert __version__ == pyproject[PYPROJECT_PROJECT][PYPROJECT_VERSION]


def test_pyproject_version_reads_project_version(tmp_path):
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    assert pyproject_version(pyproject_path) == "1.2.3"
