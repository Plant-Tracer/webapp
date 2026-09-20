"""Check navigation overflow in a real browser."""

import pytest
from selenium.webdriver.common.by import By

from app.odb import API_KEY
from .selenium_utils import authenticate_browser


@pytest.mark.selenium
@pytest.mark.parametrize('width', [390, 1280])
def test_navigation_scroll_is_contained(chrome_driver, live_server, new_course, width):
    """All menu links remain reachable without horizontal document overflow."""
    driver = chrome_driver
    try:
        driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
            'width': width, 'height': 844, 'deviceScaleFactor': 1, 'mobile': width == 390,
        })
        authenticate_browser(driver, live_server, new_course[API_KEY])
        driver.get(live_server)
        menu = driver.find_element(By.CSS_SELECTOR, 'header .pure-menu-horizontal')
        assert driver.execute_script('return window.innerWidth;') == width
        assert driver.execute_script('''
            return document.documentElement.scrollWidth <= window.innerWidth;
        ''')
        if width == 390:
            assert driver.execute_script('return arguments[0].scrollWidth > arguments[0].clientWidth;', menu)
        driver.execute_script('arguments[0].scrollLeft = arguments[0].scrollWidth;', menu)
        assert driver.execute_script('''
            const menu = arguments[0];
            const last = menu.querySelector('li:last-child a').getBoundingClientRect();
            const bounds = menu.getBoundingClientRect();
            return last.left >= bounds.left && last.right <= bounds.right + 1 && window.scrollX === 0;
        ''', menu)
    finally:
        driver.execute_cdp_cmd('Emulation.clearDeviceMetricsOverride', {})
