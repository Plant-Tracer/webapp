"""
Test trackpoint dragging functionality using Selenium and Chromium.

This test verifies that trackpoints can be dragged in the browser and that
the changes are properly saved to DynamoDB.

This test covers the following sequence:
1. The user clicks on a trackpoint.
2. The user drags the trackpoint to a new position.
3. The user releases the trackpoint.
4. The location of the trackpoint gets updated in DynamoDB.

This test uses the fixtures from local_aws (local_ddb and local_s3) and
the new_movie fixture to create a movie in the database.
"""

import time
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from app import odb
from app.odb import MOVIE_ID


def test_trackpoint_drag_and_database_update(chrome_driver, live_server, new_movie):
    """
    Test that dragging a trackpoint in the browser updates the database.

    This test:
    1. Creates a movie using the new_movie fixture
    2. Navigates to the movie list page
    3. Clicks the "analyze" button for the movie
    4. Waits for the first frame to be extracted (if necessary)
    5. Waits for trackpoints to be placed
    6. Drags a trackpoint to a new location
    7. Polls the database to verify the trackpoint was updated
    """
    movie_id = new_movie[MOVIE_ID]

    # Navigate to the list page
    url = f"{live_server}/list"
    chrome_driver.get(url)

    # Wait for the page to load
    try:
        WebDriverWait(chrome_driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except TimeoutException:
        pytest.fail("List page failed to load")

    # Find and click the analyze button for our movie
    # The button has class 'analyze' and x-movie_id attribute
    analyze_button_selector = f"input.analyze[x-movie_id='{movie_id}']"

    # Poll for the analyze button to appear (movie list is loaded via JavaScript)
    # Use short waits (0.1 sec) and poll as instructed
    max_wait = 10
    start_time = time.time()
    analyze_button = None
    while time.time() - start_time < max_wait:
        try:
            analyze_button = chrome_driver.find_element(By.CSS_SELECTOR, analyze_button_selector)
            if analyze_button.is_displayed():
                break
        except NoSuchElementException:
            pass
        time.sleep(0.1)

    if not analyze_button or not analyze_button.is_displayed():
        # Take screenshot for debugging
        chrome_driver.save_screenshot('/tmp/analyze_button_not_found.png')
        page_source = chrome_driver.page_source
        pytest.fail(f"Analyze button not found for movie {movie_id}. Page has {len(page_source)} chars")

    # Click the analyze button
    analyze_button.click()

    # Wait for the analyze page to load
    try:
        WebDriverWait(chrome_driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "canvas"))
        )
    except TimeoutException:
        pytest.fail("Analyze page failed to load canvas element")

    # Wait for the canvas and movie to be ready
    # Poll for trackpoints to be visible on the canvas
    # Trackpoints are drawn as circles with the Marker class
    # Use short waits (0.1 sec) and poll the database as instructed
    max_wait = 30
    start_time = time.time()
    trackpoints_ready = False

    while time.time() - start_time < max_wait:
        # Check if trackpoints exist in the database for frame 0
        try:
            trackpoints = odb.get_movie_trackpoints(movie_id=movie_id, frame_start=0, frame_count=1)
            if len(trackpoints) > 0:
                trackpoints_ready = True
                print(f"Found {len(trackpoints)} trackpoints in database")
                break
        except Exception as e:
            print(f"Error checking trackpoints: {e}")
        time.sleep(0.1)

    if not trackpoints_ready:
        chrome_driver.save_screenshot('/tmp/trackpoints_not_found.png')
        pytest.fail("Trackpoints were not placed on frame 0 within 30 seconds")

    # Get initial trackpoint positions
    initial_trackpoints = odb.get_movie_trackpoints(movie_id=movie_id, frame_start=0, frame_count=1)
    assert len(initial_trackpoints) > 0, "No trackpoints found in database"

    # Find a trackpoint to drag (we'll drag the first one)
    initial_trackpoint = initial_trackpoints[0]
    initial_x = initial_trackpoint['x']
    initial_y = initial_trackpoint['y']
    label = initial_trackpoint['label']

    print(f"Initial trackpoint '{label}': x={initial_x}, y={initial_y}")

    # Find the canvas element
    canvas = chrome_driver.find_element(By.CSS_SELECTOR, "div#tracer canvas")

    # Calculate the drag offset (drag 50 pixels to the right and 30 pixels down)
    drag_offset_x = 50
    drag_offset_y = 30

    # We need to account for the zoom factor (default is 1.0)
    # The canvas coordinates are at (initial_x, initial_y)
    # We need to convert to screen coordinates

    # Perform the drag operation
    # Start at the trackpoint location on the canvas
    actions = ActionChains(chrome_driver)

    # Move to the initial trackpoint position (relative to canvas top-left)
    actions.move_to_element_with_offset(canvas, initial_x, initial_y)
    actions.click_and_hold()
    actions.move_by_offset(drag_offset_x, drag_offset_y)
    actions.release()
    actions.perform()

    # Give the browser time to process the drag and send the update to the server
    time.sleep(0.5)

    # Poll the database to verify the trackpoint was updated
    # Use short waits (0.1 sec) and poll as instructed
    max_wait = 10
    start_time = time.time()
    trackpoint_updated = False
    final_trackpoints = None
    final_x = initial_x
    final_y = initial_y

    while time.time() - start_time < max_wait:
        try:
            final_trackpoints = odb.get_movie_trackpoints(movie_id=movie_id, frame_start=0, frame_count=1)

            # Find the trackpoint with the same label
            for tp in final_trackpoints:
                if tp['label'] == label:
                    final_x = tp['x']
                    final_y = tp['y']

                    # Check if the position changed
                    # Allow some tolerance for rounding
                    if abs(final_x - initial_x) > 5 or abs(final_y - initial_y) > 5:
                        trackpoint_updated = True
                        print(f"Updated trackpoint '{label}': x={final_x}, y={final_y} " +
                              f"(changed from {initial_x}, {initial_y})")

                        # Verify the change is approximately what we expected
                        expected_x = initial_x + drag_offset_x
                        expected_y = initial_y + drag_offset_y

                        # Allow tolerance of 10 pixels due to rounding and coordinate transformations
                        assert abs(final_x - expected_x) < 10, \
                            f"X coordinate mismatch: expected ~{expected_x}, got {final_x}"
                        assert abs(final_y - expected_y) < 10, \
                            f"Y coordinate mismatch: expected ~{expected_y}, got {final_y}"

                        break

            if trackpoint_updated:
                break
        except Exception as e:
            print(f"Error polling trackpoints: {e}")

        time.sleep(0.1)

    if not trackpoint_updated:
        chrome_driver.save_screenshot('/tmp/trackpoint_not_updated.png')
        assert False, \
            f"Trackpoint '{label}' was not updated in the database after drag. " \
            f"Initial: ({initial_x}, {initial_y}), Final: ({final_x}, {final_y})"
