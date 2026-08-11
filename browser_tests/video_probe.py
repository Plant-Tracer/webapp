"""Shared assertions for browser video-frame probes."""

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


FRAME_SEQUENCE = (0, 1, 2, 3, 3, 2, 1, 0)


def wait_for_decoded_frames(driver) -> str:
    """Wait until the player reaches a terminal decode status."""
    return WebDriverWait(driver, 30).until(
        lambda browser: (
            value if not value.startswith(("Loading", "Fetching", "Decoding")) else False
        )
        if (value := browser.find_element(By.ID, "status-output").get_attribute("value"))
        else False
    )


def matches_color(sample: list[int], expected: tuple[int, int, int]) -> bool:
    """Accept normal H.264 YUV conversion variance, but not another probe frame."""
    return all(
        actual >= 128 if wanted else actual <= 64
        for actual, wanted in zip(sample[:3], expected)
    )
