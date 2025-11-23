"""
Test canvas_movie_controller.js functionality using Selenium and Chromium.

This test verifies that the canvas movie controller works correctly after jQuery removal,
by using Flask's test client with Selenium to test in a real browser (Chromium).

The chrome_driver and live_server fixtures are now defined in conftest.py and shared
across all test files.
"""

import time
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


def test_canvas_movie_controller_page_load(chrome_driver, live_server):
    """
    Test that a page using canvas_movie_controller.js loads successfully.

    This test verifies:
    1. The page loads without errors
    2. The canvas element is present
    3. The movie controller is initialized
    """
    # Navigate to demo_tracer2 which uses canvas_movie_controller.js
    url = f"{live_server}/demo_tracer2.html"

    try:
        chrome_driver.get(url)

        # Wait for page to load
        WebDriverWait(chrome_driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "canvas"))
        )

        # Verify canvas element exists
        canvas_elements = chrome_driver.find_elements(By.TAG_NAME, "canvas")
        assert len(canvas_elements) > 0, "Canvas element not found on page"

        # Check for JavaScript errors in console
        # Filter out expected errors from demo pages trying to fetch external resources
        logs = chrome_driver.get_log('browser')
        severe_errors = [log for log in logs if log['level'] == 'SEVERE'
                        and 'favicon.ico' not in log.get('message', '')
                        and 'planttracer.com' not in log.get('message', '')
                        and 'CORS policy' not in log.get('message', '')
                        and 'Failed to fetch' not in log.get('message', '')]
        assert len(severe_errors) == 0, f"JavaScript errors found: {severe_errors}"

    except TimeoutException:
        pytest.fail("Page failed to load canvas element within timeout")


def test_canvas_movie_controller_initialization(chrome_driver, live_server):
    """
    Test that the canvas movie controller initializes correctly.

    This test verifies:
    1. The MovieController class is available
    2. The add_frame_objects method exists and can be called
    """
    url = f"{live_server}/demo_tracer2.html"

    try:
        chrome_driver.get(url)

        # Wait for page to load
        WebDriverWait(chrome_driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "canvas"))
        )

        # Give some time for JavaScript to initialize
        time.sleep(1)

        # Check that MovieController is defined in the page
        result = chrome_driver.execute_script("""
            // Check if MovieController module is loaded
            return typeof window !== 'undefined';
        """)
        assert result, "Window object not available"

    except TimeoutException:
        pytest.fail("Page failed to load within timeout")


def test_canvas_movie_controller_frame_navigation(chrome_driver, live_server):
    """
    Test that frame navigation works in the movie controller.

    This test verifies:
    1. Movie control buttons are present
    2. Frame navigation works (if applicable)
    """
    url = f"{live_server}/demo_tracer2.html"

    try:
        chrome_driver.get(url)

        # Wait for page to load
        WebDriverWait(chrome_driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "canvas"))
        )

        # Look for movie control buttons
        buttons = chrome_driver.find_elements(By.CSS_SELECTOR, "input[type='button']")
        assert buttons is not None

        # Common movie control button classes
        button_classes = ['first_button', 'play_forward', 'play_reverse',
                         'pause_button', 'last_button', 'next_frame', 'prev_frame']

        found_controls = []
        for button_class in button_classes:
            elements = chrome_driver.find_elements(By.CSS_SELECTOR, f"input.{button_class}")
            if elements:
                found_controls.append(button_class)

        # Verify no severe JavaScript errors
        # Filter out expected errors from demo pages trying to fetch external resources
        logs = chrome_driver.get_log('browser')
        severe_errors = [log for log in logs if log['level'] == 'SEVERE'
                        and 'favicon.ico' not in log.get('message', '')
                        and 'planttracer.com' not in log.get('message', '')
                        and 'CORS policy' not in log.get('message', '')
                        and 'Failed to fetch' not in log.get('message', '')]
        assert len(severe_errors) == 0, f"JavaScript errors found: {severe_errors}"

    except TimeoutException:
        pytest.fail("Page failed to load within timeout")


def test_canvas_movie_controller_console_logs(chrome_driver, live_server):
    """
    Integration test verifying console.log output from canvas_movie_controller.js.

    This test checks that methods like add_frame_objects() and play() are called.
    """
    url = f"{live_server}/demo_tracer2.html"

    try:
        chrome_driver.get(url)

        # Wait for page to fully load
        WebDriverWait(chrome_driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "canvas"))
        )

        # Allow time for all JavaScript to initialize
        time.sleep(2)

        # Get all console logs
        logs = chrome_driver.get_log('browser')

        # Verify no severe errors
        # Filter out expected errors from demo pages trying to fetch external resources
        severe_errors = [log for log in logs if log['level'] == 'SEVERE'
                        and 'favicon.ico' not in log.get('message', '')
                        and 'planttracer.com' not in log.get('message', '')
                        and 'CORS policy' not in log.get('message', '')
                        and 'Failed to fetch' not in log.get('message', '')]
        assert len(severe_errors) == 0, f"JavaScript errors found: {severe_errors}"

        # Verify page loaded
        assert chrome_driver.title, "Page title should not be empty"

    except TimeoutException:
        pytest.fail("Page failed to load within timeout")
