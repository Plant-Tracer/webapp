"""
Test functions to verify the title of the Plant Tracer webapp home/index page

This module also serves to illustrate how to use Selenium and Pytest together.

The two tests here test the same thing, but one uses the pytest-selenium
package and the other uses the selenium package directly.
"""

import pytest
import pytest_selenium

# not needed for using pytest-selenium, just for using selenium directly
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PLANTTRACER_TITLE = 'Plant Tracer Plant Tracer'

# test function illustrating the use of selenium package directly
def test_sitetitle_just_selenium(http_endpoint):
    options = Options()
    options.headless = True
    browser_driver = webdriver.Chrome(options = options) # TODO: externalize browser type, if possible
    browser_driver.get(http_endpoint)
    assert browser_driver.title == PLANTTRACER_TITLE
    browser_driver.close()

# test function illustrating the use of pytest-selenium package
# pytest-selenium itself uses the selenium package
#
# Using pytest-selenium requires the --driver command line argument to pytest
# --driver may be specified in pytest.ini using addopts Configuration option
#
# TODO: test should probably be headless, or at least clean up their browser processes
def test_sitetitle_pytest_selenium(http_endpoint, chrome_options, selenium):
    selenium.get(http_endpoint) # TODO: externalize site URL
    assert selenium.title == PLANTTRACER_TITLE