"""Browser test for a portable analysis-MP4 player bundle."""

from functools import partial
from http.server import ThreadingHTTPServer
import threading
import shutil
from pathlib import Path

import numpy as np
import pytest
from selenium.webdriver.common.by import By

from resize_app.analysis_mp4 import AnalysisMp4Options, create_analysis_bundle, encode_analysis_mp4
from resize_app.video_writer import H264Writer
from browser_tests.static_server import JavaScriptModuleHandler
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
    long_source = tmp_path / 'long.mp4'
    writer = H264Writer(long_source, fps=15)
    try:
        for index in range(64):
            writer.append_data(np.full((96, 128, 3), FRAME_COLORS[index % 4], dtype=np.uint8))
    finally:
        writer.close()
    encode_analysis_mp4(source_path=long_source, output_path=bundle_path / 'long_scaled.mp4',
                        options=AnalysisMp4Options())
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / 'src/app/static', bundle_path / 'src/app/static')
    shutil.copyfile(root / 'browser_tests/player_harness.html', bundle_path / 'analyzer.html')
    handler = partial(JavaScriptModuleHandler, directory=bundle_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()


def canvas_sample(driver) -> list[int]:
    """Read a canvas pixel away from the burned-in frame number."""
    return driver.execute_script(
        "const canvas = document.getElementById('movie-canvas');"
        "return Array.from(canvas.getContext('2d').getImageData("
        "Math.floor(canvas.width / 4), Math.floor(canvas.height * 3 / 4), 1, 1).data);"
    )


@pytest.mark.selenium
def test_generated_bundle_steps_all_frames_forward_then_reverse(chrome_driver, analysis_bundle_server):
    """The portable bundle uses its local player assets and MP4 without Flask."""
    chrome_driver.get(f"{analysis_bundle_server}/index.html")
    status = wait_for_decoded_frames(chrome_driver)
    assert status.startswith("Decoded 4 frames"), status
    samples = [canvas_sample(chrome_driver)]
    for button_id in ("next-frame-button",) * 3 + ("previous-frame-button",) * 3:
        chrome_driver.find_element(By.ID, button_id).click()
        samples.append(canvas_sample(chrome_driver))
    samples.insert(4, samples[3])
    for sample, frame_index in zip(samples, FRAME_SEQUENCE):
        assert matches_color(sample, FRAME_COLORS[frame_index]), (
            f"expected {FRAME_COLORS[frame_index]}, got {sample}"
        )


@pytest.mark.selenium
def test_generated_analysis_mp4_uses_production_analyzer(chrome_driver, analysis_bundle_server):
    """The shared encoder output plays in the actual analyzer before any tracing."""
    chrome_driver.get(f"{analysis_bundle_server}/analyzer.html?src=source_scaled.mp4")
    assert wait_for_decoded_frames(chrome_driver).startswith('Decoded 4 frames')
    for index in FRAME_SEQUENCE:
        outcome = chrome_driver.execute_async_script(
            "const done=arguments[arguments.length-1];"
            "window.playerController.goto_frame(arguments[0]).then(() => requestAnimationFrame(() => done(true)))"
            ".catch(e=>done(e.message));", index)
        assert outcome is True
        sample = chrome_driver.execute_script(
            "const c=document.getElementById('canvas-id'); return Array.from(c.getContext('2d')"
            ".getImageData(Math.floor(c.width/4),Math.floor(c.height*3/4),1,1).data);")
        assert matches_color(sample, FRAME_COLORS[index]), (index, sample)
    assert chrome_driver.execute_script('return window.playerController.mp4_player.frames.size') <= 30
    chrome_driver.execute_script('window.playerController.mp4_player.close();')
    assert chrome_driver.execute_script('return window.playerController.mp4_player.frames.size') == 0
    outcome = chrome_driver.execute_async_script(
        "const done=arguments[0]; window.playerController.mp4_player.getFrame(0)"
        ".then(()=>done('unexpected success')).catch(e=>done(e.message));")
    assert 'closed' in outcome


@pytest.mark.selenium
def test_production_player_redecodes_distant_frames_with_bounded_storage(chrome_driver, analysis_bundle_server):
    """Arbitrary forward/reverse jumps retain exact frame order without caching the movie."""
    chrome_driver.get(f"{analysis_bundle_server}/analyzer.html?src=long_scaled.mp4")
    assert wait_for_decoded_frames(chrome_driver).startswith('Decoded 64 frames')
    for index in (0, 29, 30, 31, 63, 32, 30, 29, 0):
        outcome = chrome_driver.execute_async_script(
            "const done=arguments[arguments.length-1]; window.playerController.goto_frame(arguments[0])"
            ".then(()=>requestAnimationFrame(()=>done(true))).catch(e=>done(e.message));", index)
        assert outcome is True
        sample = chrome_driver.execute_script(
            "return Array.from(document.getElementById('canvas-id').getContext('2d')"
            ".getImageData(32,72,1,1).data);")
        assert matches_color(sample, FRAME_COLORS[index % 4]), (index, sample)
        assert chrome_driver.execute_script('return window.playerController.mp4_player.frames.size') <= 30
    for index in (-1, 64):
        outcome = chrome_driver.execute_async_script(
            "const done=arguments[arguments.length-1]; window.playerController.mp4_player.getFrame(arguments[0])"
            ".then(()=>done('unexpected success')).catch(e=>done(e.name));", index)
        assert outcome == 'RangeError'
