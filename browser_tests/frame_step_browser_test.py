"""Browser conformance test for deterministic single-frame video stepping."""

import base64
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import threading
from urllib.parse import quote

import pytest
from selenium.webdriver.common.by import By
from browser_tests.video_probe import FRAME_SEQUENCE, matches_color, wait_for_decoded_frames


FRAME_COLORS = (
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
)


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


def _write_ppm(path: Path, color: tuple[int, int, int]) -> None:
    """Write one uncompressed, solid-color 64x64 PPM frame."""
    pixels = bytes(color) * (64 * 64)
    path.write_bytes(b"P6\n64 64\n255\n" + pixels)


def _four_frame_mpeg(tmp_path: Path) -> bytes:
    """Build the MP4 probe from four visually distinct source frames."""
    for index, color in enumerate(FRAME_COLORS, start=1):
        _write_ppm(tmp_path / f"frame_{index}.ppm", color)
    movie = tmp_path / "four-frame-probe.mp4"
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-framerate", "4", "-i", str(tmp_path / "frame_%d.ppm"),
        "-frames:v", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-g", "4", "-bf", "2", "-sc_threshold", "0",
        "-movflags", "+faststart", str(movie),
    ]
    subprocess.run(command, check=True)
    return movie.read_bytes()


def _canvas_sample(driver) -> list[int]:
    """Read the center pixel from the WebCodecs player's rendered canvas."""
    return driver.execute_script(
        "return Array.from(document.getElementById('movie-canvas').getContext('2d')"
        ".getImageData(32, 32, 1, 1).data);"
    )


@pytest.mark.selenium
def test_single_frame_stepping_recovers_forward_then_reverse_order(chrome_driver, frame_step_server, tmp_path):
    """Exercise the WebCodecs player's +1/-1 controls against a B-frame MP4."""
    encoded = base64.b64encode(_four_frame_mpeg(tmp_path)).decode("ascii")
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
        assert matches_color(sample, FRAME_COLORS[frame_index]), (
            f"expected frame {frame_index + 1} {FRAME_COLORS[frame_index]}, got {sample}"
        )


@pytest.mark.selenium
def test_external_movie_url_requires_explicit_load(chrome_driver, frame_step_server):
    """Opening the public demo must not automatically contact an external movie host."""
    external_url = quote("https://example.invalid/plant.mp4", safe="")
    chrome_driver.get(f"{frame_step_server}/mp4player-demo3.html?src={external_url}")

    assert wait_for_decoded_frames(chrome_driver) == "Click Load URL or choose a local MP4 file."
