"""Reusable Chrome fixture for browser-only and Flask browser tests."""

import os
from typing import Generator

import pytest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options


@pytest.fixture
def chrome_driver() -> Generator[webdriver.Chrome, None, None]:
    """Provide Chrome and fail if the requested platform cannot start it."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    android_serial = os.environ.get("CHROME_ANDROID_SERIAL")
    if android_serial:
        options.add_experimental_option("androidPackage", "com.android.chrome")
        options.add_experimental_option("androidDeviceSerial", android_serial)
    if chrome_path := os.environ.get("CHROME_PATH"):
        options.binary_location = chrome_path
    try:
        driver = webdriver.Chrome(options=options)  # pylint: disable=not-callable
    except WebDriverException as exc:
        pytest.fail(f"Chrome/Chromium is required for browser tests: {exc}")
    yield driver
    driver.quit()
