"""
Helper utilities shared by Selenium-based end-to-end tests.
"""

from selenium.common.exceptions import WebDriverException

from app.constants import C


def authenticate_browser(driver, base_url, api_key, cookie_name=C.API_KEY_COOKIE_BASE):
    """
    Navigates to base_url and sets the api_key cookie so that
    subsequent requests are authenticated as the test user.
    """
    driver.get(base_url)

    # Remove any leftover cookies from previous tests to avoid leakage.
    driver.delete_all_cookies()

    driver.add_cookie(
        {
            "name": cookie_name,
            "value": str(api_key).strip(),
            "path": "/",
        }
    )

    stored_cookie = driver.get_cookie(cookie_name)
    if not stored_cookie:
        raise WebDriverException("Failed to set authentication cookie in browser")
    if stored_cookie["value"] != str(api_key).strip():
        raise WebDriverException("Authentication cookie value mismatch")
