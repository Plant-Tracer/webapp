#!/usr/bin/env python3
"""
Normalize coverage file paths to be relative to git root for codecov compatibility.

This script converts absolute paths in coverage-final.json to relative paths
so that codecov can properly match them to the repository structure.
"""
import json
import os
import sys
from pathlib import Path

def normalize_coverage_paths(coverage_file: str) -> None:
    """Normalize paths in coverage-final.json to be relative to git root."""
    git_root = Path.cwd()
    coverage_path = Path(coverage_file)
    
    if not coverage_path.exists():
        print(f"Warning: {coverage_file} not found, skipping normalization")
        return
    
    with open(coverage_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Convert absolute paths to relative paths
    normalized = {}
    for abs_path, cov_data in data.items():
        try:
            # Convert absolute path to relative
            if os.path.isabs(abs_path):
                rel_path = os.path.relpath(abs_path, git_root)
            else:
                rel_path = abs_path
            
            # Update the path in the coverage data if it exists
            if isinstance(cov_data, dict) and 'path' in cov_data:
                if os.path.isabs(cov_data['path']):
                    cov_data['path'] = os.path.relpath(cov_data['path'], git_root)
            
            normalized[rel_path] = cov_data
        except (ValueError, TypeError) as e:
            # If path can't be converted, keep as is
            print(f"Warning: Could not normalize path {abs_path}: {e}")
            normalized[abs_path] = cov_data
    
    # Write back
    with open(coverage_path, 'w', encoding='utf-8') as f:
        json.dump(normalized, f, indent=2)
    
    print(f"Normalized {len(data)} coverage files to use relative paths")

if __name__ == '__main__':
    coverage_file = sys.argv[1] if len(sys.argv) > 1 else 'coverage/coverage-final.json'
    normalize_coverage_paths(coverage_file)

