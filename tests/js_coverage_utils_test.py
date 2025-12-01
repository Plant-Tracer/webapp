"""Tests for js_coverage_utils module."""

import json
import tempfile
from pathlib import Path

from .js_coverage_utils import (
    _merge_hit_counters,
    _merge_branch_counters,
    _merge_file_coverage,
    merge_coverage_files,
)


def test_merge_hit_counters_empty():
    """Test merging with empty dicts."""
    assert not _merge_hit_counters({}, {})
    assert _merge_hit_counters({"0": 1}, {}) == {"0": 1}
    assert _merge_hit_counters({}, {"0": 1}) == {"0": 1}


def test_merge_hit_counters_overlapping():
    """Test merging overlapping hit counters."""
    base = {"0": 1, "1": 2, "2": 0}
    overlay = {"0": 3, "1": 0, "3": 5}
    result = _merge_hit_counters(base, overlay)
    assert result == {"0": 4, "1": 2, "2": 0, "3": 5}


def test_merge_branch_counters_empty():
    """Test merging with empty branch dicts."""
    assert not _merge_branch_counters({}, {})
    assert _merge_branch_counters({"0": [1, 0]}, {}) == {"0": [1, 0]}
    assert _merge_branch_counters({}, {"0": [1, 0]}) == {"0": [1, 0]}


def test_merge_branch_counters_overlapping():
    """Test merging overlapping branch counters."""
    base = {"0": [1, 0], "1": [2, 3]}
    overlay = {"0": [0, 1], "2": [4, 5]}
    result = _merge_branch_counters(base, overlay)
    assert result == {"0": [1, 1], "1": [2, 3], "2": [4, 5]}


def test_merge_branch_counters_different_lengths():
    """Test merging branch counters with different array lengths."""
    base = {"0": [1, 0]}
    overlay = {"0": [0, 1, 2]}
    result = _merge_branch_counters(base, overlay)
    assert result == {"0": [1, 1, 2]}


def test_merge_file_coverage():
    """Test merging complete file coverage objects."""
    base = {
        "path": "/path/to/file.js",
        "s": {"0": 1, "1": 0},
        "f": {"0": 2},
        "b": {"0": [1, 0]},
        "statementMap": {"0": {"start": {"line": 1}}, "1": {"start": {"line": 2}}},
        "fnMap": {"0": {"name": "test"}},
        "branchMap": {"0": {"type": "if"}},
    }
    overlay = {
        "path": "/path/to/file.js",
        "s": {"0": 0, "1": 3},
        "f": {"0": 1},
        "b": {"0": [0, 2]},
        "statementMap": {"2": {"start": {"line": 3}}},
        "fnMap": {"1": {"name": "test2"}},
        "branchMap": {"1": {"type": "switch"}},
    }
    result = _merge_file_coverage(base, overlay)

    # Verify hit counters are summed
    assert result["s"] == {"0": 1, "1": 3}
    assert result["f"] == {"0": 3}
    assert result["b"] == {"0": [1, 2]}

    # Verify maps are merged
    assert "0" in result["statementMap"]
    assert "1" in result["statementMap"]
    assert "2" in result["statementMap"]
    assert "0" in result["fnMap"]
    assert "1" in result["fnMap"]
    assert "0" in result["branchMap"]
    assert "1" in result["branchMap"]


def test_merge_coverage_files():
    """Test merging two coverage files with overlapping files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        jest_path = Path(tmpdir) / "jest-coverage.json"
        browser_path = Path(tmpdir) / "browser-coverage.json"
        output_path = Path(tmpdir) / "merged-coverage.json"

        # Create Jest coverage
        jest_coverage = {
            "/path/to/file1.js": {
                "s": {"0": 1, "1": 0},
                "f": {"0": 2},
                "b": {"0": [1, 0]},
            },
            "/path/to/file2.js": {
                "s": {"0": 5},
                "f": {},
                "b": {},
            },
        }
        with open(jest_path, "w", encoding="utf-8") as f:
            json.dump(jest_coverage, f)

        # Create browser coverage (overlaps with file1.js)
        browser_coverage = {
            "/path/to/file1.js": {
                "s": {"0": 0, "1": 3},
                "f": {"0": 1},
                "b": {"0": [0, 2]},
            },
            "/path/to/file3.js": {
                "s": {"0": 10},
                "f": {"0": 5},
                "b": {},
            },
        }
        with open(browser_path, "w", encoding="utf-8") as f:
            json.dump(browser_coverage, f)

        # Merge coverage files
        merge_coverage_files(jest_path, browser_path, output_path)

        # Read merged output
        with open(output_path, "r", encoding="utf-8") as f:
            merged = json.load(f)

        # Verify all files are present
        assert "/path/to/file1.js" in merged
        assert "/path/to/file2.js" in merged
        assert "/path/to/file3.js" in merged

        # Verify overlapping file has merged counters
        file1 = merged["/path/to/file1.js"]
        assert file1["s"] == {"0": 1, "1": 3}  # Summed
        assert file1["f"] == {"0": 3}  # Summed
        assert file1["b"] == {"0": [1, 2]}  # Summed

        # Verify non-overlapping files are unchanged
        assert merged["/path/to/file2.js"]["s"] == {"0": 5}
        assert merged["/path/to/file3.js"]["s"] == {"0": 10}
