"""
Utilities for collecting and merging JavaScript coverage from browser tests.

This module handles extraction of Istanbul coverage data from Chromium
and merging it with Jest coverage output.
"""

import json
from pathlib import Path
from typing import Any


def _merge_hit_counters(base: dict[str, int], overlay: dict[str, int]) -> dict[str, int]:
    """
    Merge two hit counter dicts by adding values together.

    Args:
        base: Base hit counter dict (e.g., {"0": 1, "1": 2})
        overlay: Overlay hit counter dict to merge

    Returns:
        Merged hit counter dict with values summed
    """
    result = dict(base)
    for key, value in overlay.items():
        result[key] = result.get(key, 0) + value
    return result


def _merge_branch_counters(base: dict[str, list], overlay: dict[str, list]) -> dict[str, list]:
    """
    Merge two branch counter dicts by adding array elements.

    Args:
        base: Base branch counter dict (e.g., {"0": [1, 0], "1": [2, 3]})
        overlay: Overlay branch counter dict to merge

    Returns:
        Merged branch counter dict with array elements summed
    """
    result = {}
    all_keys = set(base.keys()) | set(overlay.keys())

    for key in all_keys:
        base_arr = base.get(key, [])
        overlay_arr = overlay.get(key, [])

        # Handle different array lengths by extending with zeros
        max_len = max(len(base_arr), len(overlay_arr))
        base_arr = list(base_arr) + [0] * (max_len - len(base_arr))
        overlay_arr = list(overlay_arr) + [0] * (max_len - len(overlay_arr))

        result[key] = [b + o for b, o in zip(base_arr, overlay_arr)]

    return result


def _merge_file_coverage(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """
    Merge two Istanbul file coverage objects.

    Combines hit counters (s, f, b) by adding values, and preserves
    the map structures from the base with overlay additions.

    Args:
        base: Base coverage object for a file
        overlay: Overlay coverage object to merge

    Returns:
        Merged coverage object
    """
    result = dict(base)

    # Merge statement hits (s)
    if 's' in overlay:
        result['s'] = _merge_hit_counters(result.get('s', {}), overlay['s'])

    # Merge function hits (f)
    if 'f' in overlay:
        result['f'] = _merge_hit_counters(result.get('f', {}), overlay['f'])

    # Merge branch hits (b)
    if 'b' in overlay:
        result['b'] = _merge_branch_counters(result.get('b', {}), overlay['b'])

    # Update maps to include any new entries from overlay
    for map_key in ('statementMap', 'fnMap', 'branchMap'):
        if map_key in overlay:
            base_map = result.get(map_key, {})
            result[map_key] = {**base_map, **overlay[map_key]}

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
    
    Merges with existing coverage if the file already exists, to accumulate
    coverage across multiple tests.

    Args:
        coverage_data: Coverage data from browser
        output_path: Path to save coverage file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing coverage if it exists
    existing_coverage = {}
    if output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_coverage = json.load(f)
        except (json.JSONDecodeError, IOError):
            # If file is corrupted or can't be read, start fresh
            existing_coverage = {}
    
    # Merge new coverage with existing
    git_root = Path(__file__).parent.parent
    merged = dict(existing_coverage)
    
    for file_path, file_coverage in coverage_data.items():
        normalized_path = _normalize_path(file_path, git_root)
        if normalized_path in merged:
            merged[normalized_path] = _merge_file_coverage(merged[normalized_path], file_coverage)
        else:
            merged[normalized_path] = file_coverage
    
    # Save merged coverage
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2)


def _normalize_path(path_str: str, git_root: Path) -> str:
    """
    Normalize a file path to be relative to git root with forward slashes.
    
    Handles various path formats:
    - Absolute paths (e.g., /home/user/project/src/app/static/file.js)
    - Relative paths (e.g., src/app/static/file.js)
    - Paths with instrumented directory (e.g., src/app/static-instrumented/file.js -> src/app/static/file.js)
    
    Args:
        path_str: File path (may be absolute or relative)
        git_root: Git root directory
        
    Returns:
        Normalized path relative to git root with forward slashes
    """
    # Convert to Path object to handle both absolute and relative paths
    path_obj = Path(path_str)
    
    # If it's an absolute path, make it relative to git root
    if path_obj.is_absolute():
        try:
            # Try to make it relative to git root
            relative = path_obj.relative_to(git_root)
        except ValueError:
            # If it's not under git root, try to find a common parent
            # or just use the original path
            relative = path_obj
    else:
        relative = path_obj
    
    # Convert to string with forward slashes (works on all platforms)
    normalized = str(relative).replace('\\', '/')
    
    # Replace static-instrumented with static to match source files
    # This handles cases where browser coverage references instrumented files
    normalized = normalized.replace('static-instrumented/', 'static/')
    
    return normalized


def merge_coverage_files(
    jest_coverage_path: Path,
    browser_coverage_path: Path,
    output_path: Path
) -> None:
    """
    Merge Jest and browser coverage files into single coverage report.
    
    Normalizes paths to ensure browser coverage paths match Jest coverage paths.

    Args:
        jest_coverage_path: Path to Jest coverage-final.json
        browser_coverage_path: Path to browser coverage file
        output_path: Path to save merged coverage
    """
    merged = {}
    git_root = Path(__file__).parent.parent

    # Load Jest coverage
    if jest_coverage_path.exists():
        with open(jest_coverage_path, 'r', encoding='utf-8') as f:
            jest_coverage = json.load(f)
            # Normalize Jest paths and add to merged
            for file_path, file_coverage in jest_coverage.items():
                normalized_path = _normalize_path(file_path, git_root)
                merged[normalized_path] = file_coverage

    # Load and merge browser coverage
    if browser_coverage_path.exists():
        with open(browser_coverage_path, 'r', encoding='utf-8') as f:
            browser_coverage = json.load(f)
            # Normalize browser coverage paths and merge
            for file_path, file_coverage in browser_coverage.items():
                normalized_path = _normalize_path(file_path, git_root)
                if normalized_path in merged:
                    merged[normalized_path] = _merge_file_coverage(merged[normalized_path], file_coverage)
                else:
                    merged[normalized_path] = file_coverage

    # Save merged coverage
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2)


def get_coverage_output_path() -> Path:
    """Get path for browser coverage output file."""
    git_root = Path(__file__).parent.parent
    return git_root / "coverage" / "browser-coverage.json"
