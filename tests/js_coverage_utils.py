"""
Utilities for collecting and merging JavaScript coverage from browser tests.

This module handles extraction of Istanbul coverage data from Chromium
and merging it with Jest coverage output.
"""

import json
from pathlib import Path
from typing import Any


def _merge_coverage_counters(
    existing: dict[str, int],
    new: dict[str, int]
) -> dict[str, int]:
    """
    Merge two coverage counter dictionaries by summing counts.

    Used for 's' (statement) and 'f' (function) coverage counters.

    Args:
        existing: Existing coverage counters (e.g., {"0": 1, "1": 2})
        new: New coverage counters to merge in

    Returns:
        Merged counters with summed hit counts
    """
    result = dict(existing)
    for key, count in new.items():
        if key in result:
            result[key] += count
        else:
            result[key] = count
    return result


def _merge_branch_counters(
    existing: dict[str, list[int]],
    new: dict[str, list[int]]
) -> dict[str, list[int]]:
    """
    Merge branch coverage counters by summing branch hit counts.

    Branch counters are arrays where each element represents a branch path.
    For example, an if/else has [then_count, else_count].

    Args:
        existing: Existing branch counters (e.g., {"0": [1, 0], "1": [0, 2]})
        new: New branch counters to merge in

    Returns:
        Merged branch counters with summed hit counts per branch
    """
    from itertools import zip_longest

    result = {key: list(counts) for key, counts in existing.items()}
    for key, counts in new.items():
        if key in result:
            # Sum counts for each branch path, handling different lengths
            existing_counts = result[key]
            result[key] = [
                (e or 0) + (n or 0)
                for e, n in zip_longest(existing_counts, counts, fillvalue=0)
            ]
        else:
            result[key] = list(counts)
    return result


def merge_file_coverage(
    existing: dict[str, Any],
    new: dict[str, Any]
) -> dict[str, Any]:
    """
    Deep merge two Istanbul file coverage objects.

    Combines coverage counters (s, f, b) by summing hit counts rather than
    replacing them. This ensures coverage data from multiple test runs
    (e.g., Jest unit tests and browser integration tests) is properly combined.

    Args:
        existing: Existing file coverage object
        new: New file coverage object to merge in

    Returns:
        Merged file coverage with combined hit counts
    """
    result = dict(existing)

    # Merge statement counters (s)
    if 's' in new:
        result['s'] = _merge_coverage_counters(
            result.get('s', {}),
            new['s']
        )

    # Merge function counters (f)
    if 'f' in new:
        result['f'] = _merge_coverage_counters(
            result.get('f', {}),
            new['f']
        )

    # Merge branch counters (b)
    if 'b' in new:
        result['b'] = _merge_branch_counters(
            result.get('b', {}),
            new['b']
        )

    # For maps (statementMap, fnMap, branchMap), always use new data.
    # These maps define the structure of the code (locations of statements, functions,
    # and branches). When instrumenting the same file, Istanbul generates consistent
    # maps, so using the newer version ensures we have current source mappings.
    # The counters (s, f, b) are what we merge; the maps just describe what they mean.
    for map_key in ('statementMap', 'fnMap', 'branchMap'):
        if map_key in new:
            result[map_key] = new[map_key]

    # Update path if present
    if 'path' in new:
        result['path'] = new['path']

    return result


def extract_coverage_from_browser(driver) -> dict[str, Any] | None:
    """
    Extract Istanbul coverage data from browser's window.__coverage__.

    Args:
        driver: Selenium WebDriver instance

    Returns:
        Coverage data dict in Istanbul format, or None if not available
    """
    try:
        coverage = driver.execute_script("return window.__coverage__;")
        if coverage:
            return coverage
    except Exception:  # pylint: disable=broad-exception-caught
        # Coverage not available - page may not be instrumented
        pass
    return None


def save_browser_coverage(coverage_data: dict[str, Any], output_path: Path) -> None:
    """
    Save browser coverage data to file in Istanbul format.

    Args:
        coverage_data: Coverage data from browser
        output_path: Path to save coverage file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(coverage_data, f, indent=2)


def merge_coverage_files(
    jest_coverage_path: Path,
    browser_coverage_path: Path,
    output_path: Path
) -> None:
    """
    Merge Jest and browser coverage files into single coverage report.

    Args:
        jest_coverage_path: Path to Jest coverage-final.json
        browser_coverage_path: Path to browser coverage file
        output_path: Path to save merged coverage
    """
    merged = {}

    # Load Jest coverage
    if jest_coverage_path.exists():
        with open(jest_coverage_path, 'r', encoding='utf-8') as f:
            jest_coverage = json.load(f)
            merged.update(jest_coverage)

    # Load and merge browser coverage
    if browser_coverage_path.exists():
        with open(browser_coverage_path, 'r', encoding='utf-8') as f:
            browser_coverage = json.load(f)
            # Deep merge coverage data - combine hit counts for overlapping files
            for file_path, file_coverage in browser_coverage.items():
                if file_path in merged:
                    merged[file_path] = merge_file_coverage(merged[file_path], file_coverage)
                else:
                    merged[file_path] = file_coverage

    # Save merged coverage
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2)


def get_coverage_output_path() -> Path:
    """Get path for browser coverage output file."""
    git_root = Path(__file__).parent.parent
    return git_root / "coverage" / "browser-coverage.json"
