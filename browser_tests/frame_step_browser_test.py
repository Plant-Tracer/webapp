"""Browser conformance test for deterministic single-frame video stepping."""

import base64
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import threading
from urllib.parse import quote

import pytest
from selenium.webdriver.common.by import By
from browser_tests.video_probe import FRAME_SEQUENCE, matches_color, wait_for_decoded_frames


FIXTURE_DIR = Path(__file__).with_name("fixtures") / "frame_step"
FRAME_PATHS = tuple(FIXTURE_DIR / f"frame_{index}.ppm" for index in range(1, 5))
MOVIE_PATH = FIXTURE_DIR / "four-frame-probe.mp4"


@pytest.fixture
def frame_step_server() -> str:
    """Serve the static demo without requiring application services."""
    static_root = Path(__file__).resolve().parents[1] / "src" / "app" / "static"
    handler = partial(SimpleHTTPRequestHandler, directory=static_root)
    server = ThreadingHTTPServer(("0.0.0.0", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = "10.0.2.2" if os.environ.get("CHROME_ANDROID_SERIAL") else "127.0.0.1"
    yield f"http://{host}:{server.server_port}"
    server.shutdown()
    thread.join()


def _ppm_center_color(path: Path) -> tuple[int, int, int]:
    """Read the center RGB pixel from a committed binary PPM fixture."""
    magic, dimensions, maximum, pixels = path.read_bytes().split(b"\n", 3)
    width, height = (int(value) for value in dimensions.split())
    assert magic == b"P6" and maximum == b"255" and (width, height) == (64, 64)
    offset = ((height // 2) * width + (width // 2)) * 3
    return pixels[offset], pixels[offset + 1], pixels[offset + 2]


def _canvas_sample(driver) -> list[int]:
    """Read the center pixel from the WebCodecs player's rendered canvas."""
    return driver.execute_script(
        "return Array.from(document.getElementById('movie-canvas').getContext('2d')"
        ".getImageData(32, 32, 1, 1).data);"
    )


@pytest.mark.selenium
def test_single_frame_stepping_recovers_forward_then_reverse_order(chrome_driver, frame_step_server):
    """Exercise the WebCodecs player's +1/-1 controls against a B-frame MP4."""
    frame_colors = tuple(_ppm_center_color(path) for path in FRAME_PATHS)
    encoded = base64.b64encode(MOVIE_PATH.read_bytes()).decode("ascii")
    data_url = f"data:video/mp4;base64,{encoded}"
    chrome_driver.get(f"{frame_step_server}/mp4player-demo3.html?src={quote(data_url, safe='')}")
    status = wait_for_decoded_frames(chrome_driver)
    assert status.startswith("Decoded 4 frames"), status
    samples = [_canvas_sample(chrome_driver)]
    for button_id in ("next-frame-button",) * 3 + ("previous-frame-button",) * 3:
        chrome_driver.find_element(By.ID, button_id).click()
        samples.append(_canvas_sample(chrome_driver))
    samples.insert(4, samples[3])
    assert len(samples) == len(FRAME_SEQUENCE)
    for sample, frame_index in zip(samples, FRAME_SEQUENCE):
        assert matches_color(sample, frame_colors[frame_index]), (
            f"expected frame {frame_index + 1} {frame_colors[frame_index]}, got {sample}"
        )


@pytest.mark.selenium
def test_external_movie_url_requires_explicit_load(chrome_driver, frame_step_server):
    """Opening the public demo must not automatically contact an external movie host."""
    external_url = quote("https://example.invalid/plant.mp4", safe="")
    chrome_driver.get(f"{frame_step_server}/mp4player-demo3.html?src={external_url}")

    assert wait_for_decoded_frames(chrome_driver) == "Click Load URL or choose a local MP4 file."
