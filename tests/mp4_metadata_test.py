"""Tests for etc/mp4_metadata.py CLI (view and set research-attribution comment)."""
# pylint: disable=duplicate-code  # _get_comment mirrors CLI get_comment for assertions
import os
import shutil
import subprocess
import sys

import pytest
from mutagen.mp4 import MP4

from app.paths import ROOT_DIR

from .constants import TEST_CIRCUMNUTATION_PATH

SCRIPT = os.path.join(ROOT_DIR, "etc", "mp4_metadata.py")
COMMENT_ATOM = "\xa9cmt"


def _get_comment(path: str) -> str | None:
    """Read comment tag (mirrors CLI logic for assertion)."""
    try:
        mp4 = MP4(path)
        if mp4.tags is None:
            return None
        values = mp4.tags.get(COMMENT_ATOM, [])
        if not values:
            return None
        part = values[0]
        return part if isinstance(part, str) else str(part)
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def _run_cli(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SCRIPT] + list(args),
        cwd=cwd or ROOT_DIR,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


@pytest.fixture
def sample_mp4(tmp_path):
    """Copy a real MP4 to a temp path so we can mutate it."""
    if not os.path.isfile(TEST_CIRCUMNUTATION_PATH):
        pytest.skip(f"Test data not found: {TEST_CIRCUMNUTATION_PATH}")
    dest = tmp_path / "sample.mp4"
    shutil.copy2(TEST_CIRCUMNUTATION_PATH, dest)
    return str(dest)


def test_mp4_metadata_no_args_prints_help():
    """Running with no arguments prints help and exits 0."""
    result = _run_cli()
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "View or set" in result.stdout


def test_mp4_metadata_print_tags(sample_mp4):
    """Running with only path prints tags (no set option)."""
    result = _run_cli(sample_mp4)
    assert result.returncode == 0
    assert result.stderr == ""
    # May or may not have existing comment; at least no error
    assert "Error opening" not in result.stdout


def test_mp4_metadata_set_research_prohibited(sample_mp4):
    """--set-research-prohibited sets comment to 'research use prohibited'."""
    result = _run_cli("--set-research-prohibited", sample_mp4)
    assert result.returncode == 0
    assert "research use prohibited" in result.stdout
    assert _get_comment(sample_mp4) == "research use prohibited"


def test_mp4_metadata_set_research_credit(sample_mp4):
    """--set-research-credit NAME sets comment to 'research use allowed; credit NAME'."""
    result = _run_cli("--set-research-credit", "Alyssa P. Hacker", sample_mp4)
    assert result.returncode == 0
    expected = "research use allowed; credit Alyssa P. Hacker"
    assert expected in result.stdout
    assert _get_comment(sample_mp4) == expected


def test_mp4_metadata_set_research_anonymous(sample_mp4):
    """--set-research-anonymous sets comment to 'research use allowed (no credit required)'."""
    result = _run_cli("--set-research-anonymous", sample_mp4)
    assert result.returncode == 0
    expected = "research use allowed (no credit required)"
    assert expected in result.stdout
    assert _get_comment(sample_mp4) == expected
