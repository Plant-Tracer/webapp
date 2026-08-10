"""Browser test for a portable analysis-MP4 player bundle."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest
from selenium.webdriver.common.by import By

from resize_app.analysis_mp4 import AnalysisMp4Options, create_analysis_bundle
from browser_tests.video_probe import FRAME_SEQUENCE, matches_color, wait_for_decoded_frames
from tests.fixtures.analysis_mp4_fixture import FRAME_COLORS, write_four_color_movie


@pytest.fixture
def analysis_bundle_server(tmp_path) -> str:
    """Serve a real generated portable bundle over HTTP."""
    source_path = tmp_path / "source.mp4"
    bundle_path = tmp_path / "bundle"
    write_four_color_movie(source_path)
    create_analysis_bundle(
        source_path=source_path,
        output_dir=bundle_path,
        options=AnalysisMp4Options(rotation=90, max_width=64, max_height=48),
    )
    handler = partial(SimpleHTTPRequestHandler, directory=bundle_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()


def canvas_center(driver) -> list[int]:
    """Read the current canvas center pixel regardless of derivative dimensions."""
    return driver.execute_script(
        "const canvas = document.getElementById('movie-canvas');"
        "return Array.from(canvas.getContext('2d').getImageData("
        "Math.floor(canvas.width / 2), Math.floor(canvas.height / 2), 1, 1).data);"
    )


@pytest.mark.selenium
def test_generated_bundle_steps_all_frames_forward_then_reverse(chrome_driver, analysis_bundle_server):
    """The portable bundle uses its local player assets and MP4 without Flask."""
    chrome_driver.get(f"{analysis_bundle_server}/index.html")
    status = wait_for_decoded_frames(chrome_driver)
    assert status.startswith("Decoded 4 frames"), status
    samples = [canvas_center(chrome_driver)]
    for button_id in ("next-frame-button",) * 3 + ("previous-frame-button",) * 3:
        chrome_driver.find_element(By.ID, button_id).click()
        samples.append(canvas_center(chrome_driver))
    samples.insert(4, samples[3])
    for sample, frame_index in zip(samples, FRAME_SEQUENCE):
        assert matches_color(sample, FRAME_COLORS[frame_index]), (
            f"expected {FRAME_COLORS[frame_index]}, got {sample}"
        )
