"""Utilities for collecting V8 JavaScript coverage from Chromium via Selenium.

This module uses the Chrome DevTools Protocol (CDP) through Selenium's
``execute_cdp_cmd`` method to collect precise V8 coverage for scripts loaded in
Selenium-driven Chromium sessions.

Usage pattern (wired via pytest fixtures in ``conftest.py``):

* For each WebDriver instance, call ``collector.start(driver)`` after it is
  created.
* Before quitting the driver, call ``collector.stop_and_record(driver)`` to
  retrieve V8 coverage and merge it into the in-memory store.
* At the end of the pytest session, call ``collector.write_json(...)`` to write
  a consolidated JSON file under ``coverage/``.

Collection is enabled only when the environment variable ``COLLECT_JS_COVERAGE``
is set to a truthy value ("1", "true", "yes"). When disabled, all methods are
no-ops so test behavior is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from selenium.webdriver.remote.webdriver import WebDriver


_TRUTHY = {"1", "true", "yes"}


@dataclass
class V8CoverageCollector:
    """Collect V8 coverage from one or more Chromium WebDriver sessions.

    This class is intentionally tolerant of runtime failures: if CDP commands
    are not supported in the current environment, collection is silently
    disabled rather than breaking tests.
    """

    enabled: bool = field(init=False)
    _results: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        env_value = os.getenv("COLLECT_JS_COVERAGE", "").strip().lower()
        self.enabled = env_value in _TRUTHY

    def start(self, driver: WebDriver) -> None:
        """Enable precise V8 coverage for a given driver.

        Safe to call multiple times; if coverage is disabled or CDP is
        unavailable, this becomes a no-op.
        """

        if not self.enabled:
            return

        try:
            driver.execute_cdp_cmd("Profiler.enable", {})
            driver.execute_cdp_cmd(
                "Profiler.startPreciseCoverage",
                {"callCount": True, "detailed": True},
            )
        except Exception:
            # If CDP coverage cannot be started, disable collection for the
            # remainder of the session rather than failing tests.
            self.enabled = False

    def take_snapshot(self, driver: WebDriver) -> None:
        """Take a snapshot of coverage data without stopping collection.

        This should be called BEFORE navigating to a new page, as navigation
        destroys the current JavaScript context and loses coverage data.
        Coverage collection continues after taking the snapshot.
        """

        if not self.enabled:
            return

        try:
            result: Dict[str, Any] = driver.execute_cdp_cmd(
                "Profiler.takePreciseCoverage", {}
            )
        except Exception:
            # Best-effort: if we cannot retrieve coverage, skip quietly.
            return

        entries = result.get("result", [])
        if not isinstance(entries, list):
            return

        self._results.extend(entries)

    def stop_and_record(self, driver: WebDriver) -> None:
        """Stop coverage collection for this driver and merge its results.

        Should be called before the WebDriver is quit.
        """

        if not self.enabled:
            return

        try:
            result: Dict[str, Any] = driver.execute_cdp_cmd(
                "Profiler.takePreciseCoverage", {}
            )
            driver.execute_cdp_cmd("Profiler.stopPreciseCoverage", {})
        except Exception:
            # Best-effort: if we cannot retrieve coverage, skip quietly.
            return

        entries = result.get("result", [])
        if not isinstance(entries, list):
            return

        self._results.extend(entries)

    def write_json(self, output_path: Path) -> None:
        """Write consolidated V8 coverage JSON to ``output_path``.

        If coverage is disabled or no results were collected, this is a no-op.
        """

        if not self.enabled or not self._results:
            return

        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload: Dict[str, Any] = {"result": self._results}
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)


# Singleton collector used by pytest fixtures.
collector = V8CoverageCollector()
