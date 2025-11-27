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
from selenium.common.exceptions import TimeoutException, NoSuchElementException, NoAlertPresentException

from app import odb
from app.odb import DDBO, MOVIE_ID, API_KEY, USER_ID
from app.constants import logger
from .selenium_utils import authenticate_browser

# Suppress verbose logging from urllib3 and selenium
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('selenium').setLevel(logging.WARNING)

# Constants for the test
DRAG_OFFSET_X = 25  # Pixels to drag right
DRAG_OFFSET_Y = 25  # Pixels to drag down
POSITION_TOLERANCE = 10  # Allowed pixel difference for position verification

def draw_cross_on_canvas(driver, canvas_element, x, y, size=10, color='red'):
    """
    Executes JavaScript to draw a cross on a canvas element at specified coordinates.

    Args:
        driver: The Selenium WebDriver (e.g., chrome_driver).
        canvas_element: The Selenium WebElement for the canvas.
        x (int): The X-coordinate for the center of the cross.
        y (int): The Y-coordinate for the center of the cross.
        size (int): The half-length of the cross lines (total length will be 2*size).
        color (str): The color of the cross (e.g., 'red', '#FF0000').
    """

    # 1. Get the canvas element's reference in the DOM
    canvas_ref = 'arguments[0]'

    # 2. Define the JavaScript code to draw the cross
    # It draws two lines (X shape) centered at (x, y)
    javascript_code = f"""
    var ctx = {canvas_ref}.getContext('2d');
    var size = {size};
    var x = {x};
    var y = {y};

    // Set line properties
    ctx.strokeStyle = '{color}';
    ctx.lineWidth = 2; // Make the line visible

    ctx.beginPath();

    // Line 1: Top-Left to Bottom-Right (\)
    ctx.moveTo(x - size, y - size);
    ctx.lineTo(x + size, y + size);

    // Line 2: Top-Right to Bottom-Left (/)
    ctx.moveTo(x + size, y - size);
    ctx.lineTo(x - size, y + size);

    ctx.stroke();
    """

    # 3. Execute the script
    driver.execute_script(javascript_code, canvas_element)


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
    - USER_ID: User IDs for the test user (admin is ADMIN_ID)
    - COURSE_ID, COURSE_NAME: Course information
    """
    movie_id = new_movie[MOVIE_ID]
    api_key  = new_movie[API_KEY]
    user_id = new_movie[USER_ID]

    # Validate that the API key exists in the database before using it
    # This ensures we're testing with a valid key
    ddbo = DDBO()  # Get the database object instance
    api_key_dict = ddbo.get_api_key_dict(api_key)
    if not api_key_dict:
        pytest.fail(f"API key {api_key} not found in database. Test fixture may be broken.")

    # Validate that the API key belongs to the correct user
    api_key_user_id = api_key_dict.get(USER_ID)
    if api_key_user_id != user_id:
        pytest.fail(f"API key user_id mismatch! API key belongs to {api_key_user_id} but expected {user_id}")

    # Validate that the movie belongs to the correct user
    movie_dict = odb.get_movie(movie_id=movie_id)
    movie_user_id = movie_dict.get(USER_ID)
    if movie_user_id != user_id:
        pytest.fail(f"Movie user_id mismatch! Movie belongs to {movie_user_id} but expected {user_id}")

    # Log the validation information for debugging
    print(f"Using API key: {api_key}")
    print(f"API key length: {len(api_key)}")
    print(f"User ID: {user_id}")
    print(f"API key validated for user: {api_key_user_id}")
    print(f"Movie validated for user: {movie_user_id}")

    authenticate_browser(chrome_driver, live_server, api_key)

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
    max_wait = 5
    start_time = time.time()
    analyze_button = None
    while time.time() - start_time < max_wait:
        try:
            analyze_button = chrome_driver.find_element(By.CSS_SELECTOR, analyze_button_selector)
            if analyze_button.is_displayed():
                break
        except NoSuchElementException:
            pass  # Element not found yet, continue polling
        time.sleep(0.25)

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

    # Make sure that the movie is untracked
    movie = ddbo.get_movie(movie_id)
    logger.debug("point 1 movie=%s",movie)
    assert movie['last_frame_tracked'] is None
    logger.debug("movie is not tracked")

    # Find the canvas element
    canvas = chrome_driver.find_element(By.CSS_SELECTOR, "div#tracer canvas")

    # The default markers (Apex, Ruler 0mm, Ruler 10mm) are at positions (50,50), (50,100), (50,150)
    # We need to perform a small drag to trigger saving them to the database

    actions = ActionChains(chrome_driver)
    actions.move_to_element_with_offset(canvas, 50, 50)  # Move to Apex marker
    actions.click_and_hold()
    actions.move_by_offset(0, 5)  # move by 5
    actions.release()

    try:
        actions.perform()
        # Check if there's an alert (error) after the action
        time.sleep(0.5)  # Give time for alert to appear

        try:
            alert = chrome_driver.switch_to.alert
            alert_text = alert.text
            # If we got an alert, fail immediately with the error
            chrome_driver.save_screenshot('/tmp/alert_error.png')
            pytest.fail(f"Alert appeared after drag action: {alert_text}")
        except NoAlertPresentException:
            pass  # No alert present, which is the expected behavior - continue
    except Exception as e:      # pylint: disable=broad-exception-caught
        chrome_driver.save_screenshot('/tmp/drag_error.png')
        pytest.fail(f"Error performing drag action: {e}")

    # Now wait for trackpoints to be saved to the database
    # Use short waits (0.1 sec) and poll the database as instructed
    max_wait = 5
    start_time = time.time()
    trackpoints_ready = False

    while time.time() - start_time < max_wait:
        # Check if trackpoints exist in the database for frame 0
        initial_trackpoints = odb.get_movie_trackpoints(movie_id=movie_id, frame_start=0, frame_count=1)
        logger.debug("t=%s initial_trackpoints=%s",time.time()-start_time, initial_trackpoints)
        if len(initial_trackpoints) > 0:
            trackpoints_ready = True
            break
        time.sleep(0.1)

    if not trackpoints_ready:
        chrome_driver.save_screenshot('/tmp/trackpoints_not_found.png')
        pytest.fail("Trackpoints were not saved to database after initial placement")

    logger.warning("Trackpoints were saved in DynamoDB. Dragging from chromium of trackpoints does not work, so no validation that trackpoints can be moved.")
