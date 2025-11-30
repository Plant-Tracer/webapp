"""
Utilities for collecting and merging JavaScript coverage from browser tests.

This module handles extraction of Istanbul coverage data from Chromium
and merging it with Jest coverage output.
"""

import json
import os
from pathlib import Path
from typing import Any


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
    except Exception:
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
            # Merge coverage data - browser coverage takes precedence for overlapping files
            for file_path, file_coverage in browser_coverage.items():
                merged[file_path] = file_coverage
    
    # Save merged coverage
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2)


def get_coverage_output_path() -> Path:
    """Get path for browser coverage output file."""
    git_root = Path(__file__).parent.parent
    return git_root / "coverage" / "browser-coverage.json"

