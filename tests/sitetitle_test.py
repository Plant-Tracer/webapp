"""
Test functions to verify the title of the Plant Tracer webapp home/index page.

Uses the live_server and chrome_driver fixtures from conftest so the test
hits the real Flask app (main Plant Tracer index), not an arbitrary URL.
"""

import sys

import pytest

from app.constants import logger

PLANTTRACER_TITLE = 'Plant Tracer'


def test_sitetitle_just_selenium(chrome_driver, live_server):
    """Load the Plant Tracer root page and assert its title."""
    logger.info("live_server %s", live_server)
    chrome_driver.get(live_server)
    if chrome_driver.title != PLANTTRACER_TITLE:
        print("\n--- Page dump (title mismatch) ---", file=sys.stderr)
        print(f"Current URL: {chrome_driver.current_url}", file=sys.stderr)
        print(f"Page title: {chrome_driver.title!r}", file=sys.stderr)
        src = chrome_driver.page_source or ""
        print(f"Page source (first 3000 chars):\n{src[:3000]}", file=sys.stderr)
        print("--- end page dump ---\n", file=sys.stderr)
    assert chrome_driver.title == PLANTTRACER_TITLE, (
        f"expected title {PLANTTRACER_TITLE!r}, got {chrome_driver.title!r} at {chrome_driver.current_url}"
    )
