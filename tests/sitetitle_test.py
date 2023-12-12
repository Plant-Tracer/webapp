import pytest
import pytest_selenium

# not needed for using pytest-selenium, just for using selenium directly
from selenium import webdriver

PLANTTRACER_TITLE = 'Plant Tracer Plant Tracer' # TODO: this is not the title we want. Should just be 'Plant Tracer'
#PLANTTRACER_TITLE = 'Plant Tracer' # this is the desired title

# test function illustraing the use of selenium package directly
def test_sitetitle_just_selenium(http_endpoint):
    browser_driver = webdriver.Chrome() # TODO: externalize browser type, if possible
    browser_driver.get(http_endpoint)
    assert browser_driver.title == PLANTTRACER_TITLE

# test function illustrating the use of pytest-selenium package
# pytest-selenium itself uses the selenium package
def test_sitetitle_pytest_selenium(http_endpoint, selenium):
    selenium.get(http_endpoint) # TODO: externalize site URL
    assert selenium.title == PLANTTRACER_TITLE