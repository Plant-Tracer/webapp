"""
End-to-end Selenium test that uploads a movie through the browser UI and
verifies the movie is stored in both S3 (MinIO) and DynamoDB.
"""

from pathlib import Path
import uuid
import hashlib
import time

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from app import odb
from app import odb_movie_data
from app.constants import logger
from .fixtures.local_aws import API_KEY
from .selenium_utils import authenticate_browser

TEST_MOVIE_PATH = Path(__file__).resolve().parent / "data" / "2019-07-12 circumnutation.mp4"


def _wait_for_movie_id(driver):
    """Helper for WebDriverWait: returns movie_id text once populated."""
    text = driver.find_element(By.ID, "movie_id").text.strip()
    return text if text else False


def _section_contains_title(driver, title):
    """Helper for WebDriverWait to confirm the uploaded title renders on /list."""
    try:
        section = driver.find_element(By.ID, "your-unpublished-movies")
        return title in section.get_attribute("innerHTML")
    except Exception:  # pylint: disable=broad-exception-caught
        return False


@pytest.mark.selenium
def test_upload_movie_end_to_end(chrome_driver, live_server, new_course):
    """
    Upload a movie via the UI and verify:
      1. The upload flow completes in the browser
      2. The movie exists in DynamoDB with the expected metadata
      3. The S3 object was written (bytes match the source file)
      4. The movie appears in the /list page rendered by client JavaScript
    """
    assert TEST_MOVIE_PATH.exists()

    api_key = new_course[API_KEY]
    authenticate_browser(chrome_driver, live_server, api_key)

    movie_id = None
    title = f"Selenium Upload {uuid.uuid4().hex[:8]}"
    description = "Uploaded via browser end-to-end test"

    wait = WebDriverWait(chrome_driver, 30)

    chrome_driver.get(f"{live_server}/upload")
    wait.until(EC.presence_of_element_located((By.ID, "movie-title")))

    chrome_driver.find_element(By.ID, "movie-title").send_keys(title)
    chrome_driver.find_element(By.ID, "movie-description").send_keys(description)
    chrome_driver.find_element(By.ID, "movie-file").send_keys(str(TEST_MOVIE_PATH))

    wait.until(EC.element_to_be_clickable((By.ID, "upload-button")))
    chrome_driver.find_element(By.ID, "upload-button").click()

    try:
        movie_id = wait.until(_wait_for_movie_id)
    except TimeoutException:
        pytest.fail("Movie ID was not displayed after upload completed")

    # Wait a bit for async operations to complete and coverage to be updated
    time.sleep(1)

    # Verify database entry
    movie = odb.get_movie(movie_id=movie_id)
    assert movie["title"] == title
    assert movie["description"] == description
    assert movie["deleted"] == 0

    # Verify MinIO object exists and matches file length
    movie_bytes = odb_movie_data.get_movie_data(movie_id=movie_id)
    assert len(movie_bytes) == TEST_MOVIE_PATH.stat().st_size

    source_hash = hashlib.sha256(TEST_MOVIE_PATH.read_bytes()).hexdigest()
    uploaded_hash = hashlib.sha256(movie_bytes).hexdigest()
    assert uploaded_hash == source_hash, "Uploaded movie content does not match source file"

    # Confirm movie shows up in the UI list (client-side render)
    chrome_driver.get(f"{live_server}/list")
    wait.until(EC.presence_of_element_located((By.ID, "your-unpublished-movies")))
    try:
        assert wait.until(lambda d: _section_contains_title(d, title))
    except TimeoutException:
        pytest.fail("Uploaded movie title never appeared in /list")

    logger.info("Successfully uploaded movie %s via browser end-to-end test", movie_id)

    # Cleanup movie data so fixtures remain isolated
    odb_movie_data.purge_movie(movie_id=movie_id)
    odb_movie_data.delete_movie(movie_id=movie_id)
