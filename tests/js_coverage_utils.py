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
    
    Accumulates coverage across multiple tests by merging with existing coverage.

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
            existing_coverage = {}
    
    # Merge new coverage with existing
    merged = dict(existing_coverage)
    for file_path, file_coverage in coverage_data.items():
        if file_path in merged:
            merged[file_path] = _merge_file_coverage(merged[file_path], file_coverage)
        else:
            merged[file_path] = file_coverage
    
    # Save merged coverage
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2)


def convert_browser_coverage_to_xml(json_path: Path, xml_path: Path) -> None:
    """
    Convert Istanbul coverage JSON to Clover XML format.
    
    Args:
        json_path: Path to browser coverage JSON file
        xml_path: Path to save Clover XML file
    """
    import xml.etree.ElementTree as ET
    from datetime import datetime
    
    if not json_path.exists():
        return
    
    with open(json_path, 'r', encoding='utf-8') as f:
        coverage = json.load(f)
    
    timestamp = int(datetime.now().timestamp() * 1000)
    
    # Create root element
    root = ET.Element('coverage')
    root.set('generated', str(timestamp))
    root.set('clover', '3.2.0')
    
    project = ET.SubElement(root, 'project')
    project.set('timestamp', str(timestamp))
    project.set('name', 'All files')
    
    # Calculate metrics
    total_statements = 0
    covered_statements = 0
    total_conditionals = 0
    covered_conditionals = 0
    total_methods = 0
    covered_methods = 0
    
    for file_path, file_coverage in coverage.items():
        s = file_coverage.get('s', {})
        f = file_coverage.get('f', {})
        b = file_coverage.get('b', {})
        
        total_statements += len(s)
        covered_statements += sum(1 for count in s.values() if count > 0)
        total_methods += len(f)
        covered_methods += sum(1 for count in f.values() if count > 0)
        
        # Count branches (conditionals)
        for branch_counts in b.values():
            if isinstance(branch_counts, list):
                total_conditionals += len(branch_counts)
                covered_conditionals += sum(1 for count in branch_counts if count > 0)
    
    elements = total_statements + total_conditionals + total_methods
    covered_elements = covered_statements + covered_conditionals + covered_methods
    
    # Project metrics
    metrics = ET.SubElement(project, 'metrics')
    metrics.set('statements', str(total_statements))
    metrics.set('coveredstatements', str(covered_statements))
    metrics.set('conditionals', str(total_conditionals))
    metrics.set('coveredconditionals', str(covered_conditionals))
    metrics.set('methods', str(total_methods))
    metrics.set('coveredmethods', str(covered_methods))
    metrics.set('elements', str(elements))
    metrics.set('coveredelements', str(covered_elements))
    metrics.set('complexity', '0')
    metrics.set('loc', str(total_statements))
    metrics.set('ncloc', str(total_statements))
    metrics.set('packages', '1')
    metrics.set('files', str(len(coverage)))
    metrics.set('classes', str(len(coverage)))
    
    # Add file coverage
    for file_path, file_coverage in coverage.items():
        file_elem = ET.SubElement(project, 'file')
        file_name = Path(file_path).name
        file_elem.set('name', file_name)
        file_elem.set('path', file_path)
        
        s = file_coverage.get('s', {})
        f = file_coverage.get('f', {})
        b = file_coverage.get('b', {})
        statement_map = file_coverage.get('statementMap', {})
        
        file_statements = len(s)
        file_covered_statements = sum(1 for count in s.values() if count > 0)
        file_methods = len(f)
        file_covered_methods = sum(1 for count in f.values() if count > 0)
        
        file_conditionals = sum(len(branch_counts) if isinstance(branch_counts, list) else 0 for branch_counts in b.values())
        file_covered_conditionals = sum(
            sum(1 for count in (branch_counts if isinstance(branch_counts, list) else []) if count > 0)
            for branch_counts in b.values()
        )
        
        file_metrics = ET.SubElement(file_elem, 'metrics')
        file_metrics.set('statements', str(file_statements))
        file_metrics.set('coveredstatements', str(file_covered_statements))
        file_metrics.set('conditionals', str(file_conditionals))
        file_metrics.set('coveredconditionals', str(file_covered_conditionals))
        file_metrics.set('methods', str(file_methods))
        file_metrics.set('coveredmethods', str(file_covered_methods))
        
        # Add line coverage
        for stmt_id, count in s.items():
            if stmt_id in statement_map:
                stmt_info = statement_map[stmt_id]
                line_num = stmt_info.get('start', {}).get('line', 0)
                if line_num > 0:
                    line_elem = ET.SubElement(file_elem, 'line')
                    line_elem.set('num', str(line_num))
                    line_elem.set('count', str(count))
                    line_elem.set('type', 'stmt')
        
        # Add branch coverage
        branch_map = file_coverage.get('branchMap', {})
        for branch_id, branch_counts in b.items():
            if branch_id in branch_map:
                branch_info = branch_map[branch_id]
                line_num = branch_info.get('line', 0)
                if line_num > 0 and isinstance(branch_counts, list):
                    line_elem = ET.SubElement(file_elem, 'line')
                    line_elem.set('num', str(line_num))
                    line_elem.set('count', str(max(branch_counts) if branch_counts else 0))
                    line_elem.set('type', 'cond')
                    true_count = sum(1 for c in branch_counts if c > 0)
                    false_count = len(branch_counts) - true_count
                    line_elem.set('truecount', str(true_count))
                    line_elem.set('falsecount', str(false_count))
    
    # Write XML
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    ET.indent(tree, space='  ')
    tree.write(xml_path, encoding='utf-8', xml_declaration=True)


def get_coverage_output_path() -> Path:
    """Get path for browser coverage output file."""
    git_root = Path(__file__).parent.parent
    return git_root / "coverage" / "browser-coverage.json"
