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
import logging
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from app import odb
from app.odb import MOVIE_ID, API_KEY

# Suppress verbose logging from urllib3 and selenium
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('selenium').setLevel(logging.WARNING)

# Constants for the test
DRAG_OFFSET_X = 50  # Pixels to drag right
DRAG_OFFSET_Y = 30  # Pixels to drag down
POSITION_TOLERANCE = 10  # Allowed pixel difference for position verification


def test_trackpoint_drag_and_database_update(chrome_driver, live_server, new_movie):
    """
    Test that dragging a trackpoint in the browser updates the database.

    This test:
    1. Creates a movie using the new_movie fixture
    2. Navigates to the movie list page (with api_key for authentication)
    3. Clicks the "analyze" button for the movie
    4. Waits for the first frame to be extracted (if necessary)
    5. Waits for trackpoints to be placed
    6. Drags a trackpoint to a new location
    7. Polls the database to verify the trackpoint was updated

    Note: The new_movie fixture provides:
    - MOVIE_ID: The movie ID to test
    - API_KEY: The api key for authentication (required for /list page)
    - ADMIN_ID, USER_ID: User IDs for the test users
    - COURSE_ID, COURSE_NAME: Course information
    """
    movie_id = new_movie[MOVIE_ID]
    api_key = new_movie[API_KEY]

    # First, navigate to the server to set the domain for the cookie
    chrome_driver.get(live_server)
    
    # Set the api_key cookie directly in the browser
    # The cookie name is 'api_key' as defined in constants.py API_KEY_COOKIE_BASE
    chrome_driver.add_cookie({
        'name': 'api_key',
        'value': api_key,
        'path': '/',
        'domain': '127.0.0.1'
    })

    # Navigate to the list page (authentication will use the cookie)
    url = f"{live_server}/list"
    chrome_driver.get(url)

    # Wait for the page to load
    try:
        WebDriverWait(chrome_driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except TimeoutException:
        pytest.fail("List page failed to load")

    # Verify the movie appears in the list by checking for the analyze button
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

    # Navigate directly to the analyze page with movie_id
    # The api_key cookie is already set and will be used for authentication
    analyze_url = f"{live_server}/analyze?movie_id={movie_id}"
    chrome_driver.get(analyze_url)

    # Wait for the analyze page to load
    try:
        WebDriverWait(chrome_driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "canvas"))
        )
    except TimeoutException:
        pytest.fail("Analyze page failed to load canvas element")

    # Wait for the page to be ready - wait for the movie controller to initialize
    # The default markers are loaded into JavaScript but NOT saved to database initially
    # They are only saved when user interacts with them
    time.sleep(2)  # Give time for JavaScript to initialize and render markers

    # Find the canvas element
    canvas = chrome_driver.find_element(By.CSS_SELECTOR, "div#tracer canvas")

    # The default markers (Apex, Ruler 0mm, Ruler 10mm) are at positions (50,50), (50,100), (50,150)
    # We need to perform a small drag to trigger saving them to the database
    # This simulates the user placing/adjusting the initial markers
    actions = ActionChains(chrome_driver)
    actions.move_to_element_with_offset(canvas, 50, 50)  # Move to Apex marker
    actions.click_and_hold()
    actions.move_by_offset(1, 1)  # Tiny movement to trigger save
    actions.release()
    actions.perform()

    # Now wait for trackpoints to be saved to the database
    # Use short waits (0.1 sec) and poll the database as instructed
    max_wait = 10
    start_time = time.time()
    trackpoints_ready = False

    while time.time() - start_time < max_wait:
        # Check if trackpoints exist in the database for frame 0
        trackpoints = odb.get_movie_trackpoints(movie_id=movie_id, frame_start=0, frame_count=1)
        if len(trackpoints) > 0:
            trackpoints_ready = True
            break
        time.sleep(0.1)

    if not trackpoints_ready:
        chrome_driver.save_screenshot('/tmp/trackpoints_not_found.png')
        pytest.fail("Trackpoints were not saved to database after initial placement")

    # Get initial trackpoint positions (after the small adjustment)
    initial_trackpoints = odb.get_movie_trackpoints(movie_id=movie_id, frame_start=0, frame_count=1)
    assert len(initial_trackpoints) > 0, "No trackpoints found in database"

    # Find a trackpoint to drag (we'll drag the first one)
    initial_trackpoint = initial_trackpoints[0]
    initial_x = initial_trackpoint['x']
    initial_y = initial_trackpoint['y']
    label = initial_trackpoint['label']

    # Perform the drag operation using Selenium ActionChains
    # This simulates a user clicking, dragging, and releasing a trackpoint
    # The offsets are relative to the canvas element
    actions = ActionChains(chrome_driver)

    # Move to the initial trackpoint position (relative to canvas top-left)
    actions.move_to_element_with_offset(canvas, initial_x, initial_y)
    actions.click_and_hold()
    actions.move_by_offset(DRAG_OFFSET_X, DRAG_OFFSET_Y)
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

                    # Verify the change is approximately what we expected
                    expected_x = initial_x + DRAG_OFFSET_X
                    expected_y = initial_y + DRAG_OFFSET_Y

                    # Verify within tolerance due to rounding and coordinate transformations
                    assert abs(final_x - expected_x) < POSITION_TOLERANCE, \
                        f"X coordinate mismatch: expected ~{expected_x}, got {final_x}"
                    assert abs(final_y - expected_y) < POSITION_TOLERANCE, \
                        f"Y coordinate mismatch: expected ~{expected_y}, got {final_y}"

                    break

        if trackpoint_updated:
            break

        time.sleep(0.1)

    if not trackpoint_updated:
        chrome_driver.save_screenshot('/tmp/trackpoint_not_updated.png')
        assert False, \
            f"Trackpoint '{label}' was not updated in the database after drag. " \
            f"Initial: ({initial_x}, {initial_y}), Final: ({final_x}, {final_y})"
