"""Browser conformance test for deterministic single-frame video stepping."""

import base64
from functools import partial
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import threading
from urllib.parse import quote

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from browser_tests.static_server import JavaScriptModuleHandler
from browser_tests.video_probe import FRAME_SEQUENCE, matches_color, wait_for_decoded_frames


FIXTURE_DIR = Path(__file__).with_name("fixtures") / "frame_step"
FRAME_PATHS = tuple(FIXTURE_DIR / f"frame_{index}.ppm" for index in range(1, 5))
MOVIE_PATH = FIXTURE_DIR / "four-frame-probe.mp4"


@pytest.fixture
def frame_step_server() -> str:
    """Serve the static demo without requiring application services."""
    static_root = Path(__file__).resolve().parents[1]
    handler = partial(JavaScriptModuleHandler, directory=static_root)
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
    chrome_driver.get(f"{frame_step_server}/src/app/static/mp4player-demo3.html?src={quote(data_url, safe='')}")
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
    chrome_driver.get(f"{frame_step_server}/src/app/static/mp4player-demo3.html?src={external_url}")

    assert wait_for_decoded_frames(chrome_driver) == "Click Load URL or choose a local MP4 file."


@pytest.mark.selenium
def test_production_analyzer_steps_b_frames_and_preserves_coordinates(chrome_driver, frame_step_server):
    """Use the real analyzer and bounded player, with no ZIP or backend service."""
    encoded = base64.b64encode(MOVIE_PATH.read_bytes()).decode("ascii")
    data_url = quote(f"data:video/mp4;base64,{encoded}", safe="")
    chrome_driver.get(f"{frame_step_server}/browser_tests/player_harness.html?src={data_url}")
    assert wait_for_decoded_frames(chrome_driver).startswith("Decoded 4 frames")
    frame_colors = tuple(_ppm_center_color(path) for path in FRAME_PATHS)
    current = 0
    for index in FRAME_SEQUENCE:
        if index != current:
            control = 'next-frame-button' if index > current else 'previous-frame-button'
            chrome_driver.find_element(By.ID, control).click()
            WebDriverWait(chrome_driver, 10).until(
                lambda browser, expected=index: browser.execute_script('return window.playerController.frame_number') == expected)
        current = index
        chrome_driver.execute_async_script(
            "const done=arguments[arguments.length-1];"
            "requestAnimationFrame(() => done(true));")
        sample = chrome_driver.execute_script(
            "return Array.from(document.getElementById('canvas-id').getContext('2d')"
            ".getImageData(32, 32, 1, 1).data);")
        assert matches_color(sample, frame_colors[index]), (index, sample)
        assert chrome_driver.execute_script('return window.playerController.frame_number') == index
    assert not chrome_driver.execute_script(
        "return performance.getEntriesByType('resource').some(r => /zip|unzip/.test(r.name));")
    # Rapid clicks count each requested step even while decoding is pending.
    chrome_driver.execute_script(
        "document.getElementById('next-frame-button').click();"
        "document.getElementById('next-frame-button').click();")
    WebDriverWait(chrome_driver, 10).until(
        lambda browser: browser.execute_script('return window.playerController.frame_number') == 2)
    point = chrome_driver.execute_script(
        "const c=window.playerController; const p={x:12,y:17,label:'Apex'};"
        "return c.canvas_marker_to_trackpoint({...c.trackpoint_to_canvas(p),name:'Apex'});")
    assert (point['x'], point['y']) == (12, 17)


@pytest.mark.selenium
def test_analyzer_carries_untraced_markers_without_creating_results(chrome_driver, frame_step_server):
    """Exercise real navigation, canvas markers, editability, and trim rendering."""
    encoded = base64.b64encode(MOVIE_PATH.read_bytes()).decode('ascii')
    source = quote(f'data:video/mp4;base64,{encoded}', safe='')
    chrome_driver.get(f'{frame_step_server}/browser_tests/player_harness.html?src={source}')
    assert wait_for_decoded_frames(chrome_driver).startswith('Decoded 4 frames')
    assert chrome_driver.find_element(By.CSS_SELECTOR, '#tracer .show_trim_controls').is_enabled()
    chrome_driver.execute_async_script("""
        const done = arguments[arguments.length - 1], c = window.playerController;
        c.movie_metadata.status = 'ready';
        c.analysis_read_only = false;
        c.frames[0].markers = [
            {label:'Apex', x:12, y:17, color:'#ff0000'},
            {label:'Ruler 0mm', x:5, y:5, undeletable:true},
            {label:'Ruler 10mm', x:5, y:25, undeletable:true}
        ];
        c.invalidateMarkerSeeds();
        c.goto_frame(0).then(() => done(true));
    """)
    for control, frame in [('next-frame-button', 1), ('last-frame-button', 3),
                           ('previous-frame-button', 2)]:
        chrome_driver.find_element(By.ID, control).click()
        WebDriverWait(chrome_driver, 10).until(
            lambda browser, expected=frame: browser.execute_script(
                'return window.playerController.frame_number') == expected)
        points = chrome_driver.execute_script('return window.playerController.get_markers();')
        assert [(point['label'], point['x'], point['y']) for point in points] == [
            ('Apex', 12, 17), ('Ruler 0mm', 5, 5), ('Ruler 10mm', 5, 25)]
        assert chrome_driver.find_element(By.CSS_SELECTOR, '#tracer .track_button').is_enabled()
        assert chrome_driver.execute_script("""
            const c = window.playerController;
            return c.frames.slice(1).every(frame => frame.markers.length === 0)
                && c.frames_for_graph().slice(1).every(frame => frame.markers.length === 0)
                && c.last_tracked_frame === -1
                && !c.objects.some(obj => obj.constructor.name === 'Line');
        """)
    # Earlier frames retain their own inherited positions independently of trim.
    chrome_driver.execute_async_script("""
        const done = arguments[arguments.length - 1], c = window.playerController;
        c.movie_metadata.status = 'tracing completed';
        c.last_tracked_frame = 0;
        c.goto_frame(1).then(() => done(true));
    """)
    assert len(chrome_driver.execute_script('return window.playerController.get_markers();')) == 3
    assert chrome_driver.find_element(By.CSS_SELECTOR, '#tracer .track_button').is_enabled()
    assert chrome_driver.execute_script(
        'return window.playerController.get_markers().every(marker => marker.frame_number === 1);')
    assert chrome_driver.execute_script("""
        const c = window.playerController;
        return c.frames[1].markers.length === 0 && c.frames_for_graph()[1].markers.length === 0
            && !c.objects.some(obj => obj.constructor.name === 'Line');
    """)
    chrome_driver.execute_script("""
        const c = window.playerController;
        c.movie_metadata.status = 'ready';
        c.last_tracked_frame = -1;
        c.frames[1].markers = [];
        c.frames[1].marker_seed_boundary = false;
        delete c.frames[1].trim_seed_markers;
        c.invalidateMarkerSeeds();
    """)
    # A saved explicit edit takes precedence; later empty frames inherit that edit.
    chrome_driver.execute_async_script("""
        const done = arguments[arguments.length - 1], c = window.playerController;
        c.updateCurrentFrameMarkers([{label:'Apex', x:30, y:17}], 2);
        c.last_tracked_frame = 2; // Metadata can include a manual seed before tracing.
        c.movie_metadata.trim_start_frame = 1;
        c.movie_metadata.trim_end_frame = 2;
        c.trim_start_frame_missing = false;
        c.trim_end_frame_missing = false;
        c.ensure_trim_defaults();
        c.goto_frame(0).then(() => done(true));
    """)
    assert chrome_driver.execute_script('return window.playerController.get_markers();') == []
    assert not chrome_driver.find_element(By.CSS_SELECTOR, '#tracer .track_button').is_enabled()
    chrome_driver.execute_async_script("""
        const done = arguments[arguments.length - 1], c = window.playerController;
        c.goto_frame(1).then(() => done(true));
    """)
    assert len(chrome_driver.execute_script('return window.playerController.get_markers();')) == 3
    chrome_driver.execute_async_script("""
        const done = arguments[arguments.length - 1], c = window.playerController;
        c.movie_metadata.trim_end_frame = 3;
        c.ensure_trim_defaults();
        c.goto_frame(3).then(() => done(true));
    """)
    assert chrome_driver.execute_script('return window.playerController.get_markers()[0].x;') == 30
    # A movie-wide frontier must not hide a valid earlier display seed.
    chrome_driver.execute_async_script("""
        const done = arguments[arguments.length - 1], c = window.playerController;
        c.movie_metadata.status = 'tracing completed';
        c.last_tracked_frame = 2;
        c.goto_frame(1).then(() => done(true));
    """)
    assert len(chrome_driver.execute_script('return window.playerController.get_markers();')) == 3
    assert chrome_driver.execute_script('return window.playerController.frames[1].markers;') == []
    # Explicitly clearing annotations stops seed propagation across that frame.
    chrome_driver.execute_async_script("""
        const done = arguments[arguments.length - 1], c = window.playerController;
        c.movie_metadata.status = 'ready';
        c.updateCurrentFrameMarkers([], 2);
        c.goto_frame(2).then(() => done(true));
    """)
    assert chrome_driver.execute_script('return window.playerController.get_markers();') == []
    chrome_driver.execute_async_script("""
        const done = arguments[arguments.length - 1], c = window.playerController;
        c.goto_frame(3).then(() => done(true));
    """)
    assert chrome_driver.execute_script('return window.playerController.get_markers();') == []
    # An empty boundary on frame 2 cannot erase earlier frame 1.
    chrome_driver.execute_async_script("""
        const done = arguments[arguments.length - 1], c = window.playerController;
        c.goto_frame(1).then(() => done(true));
    """)
    assert len(chrome_driver.execute_script('return window.playerController.get_markers();')) == 3
    assert chrome_driver.execute_script('return window.playerController.frames[1].markers;') == []
    assert not chrome_driver.execute_script('return window.playerController.frames[1].marker_seed_boundary;')
    assert chrome_driver.find_element(By.CSS_SELECTOR, '#tracer .track_button').is_enabled()
    # Reload can preserve empty boundaries when supplied as explicit frame entries.
    chrome_driver.execute_async_script("""
        const done = arguments[arguments.length - 1];
        import('/src/app/static/canvas_tracer_controller.mjs').then(async module => {
            window.playerController = await module.trace_movie_frames('div#tracer', {
                movie_id:'probe', total_frames:4, frame_height_px:64, width:64, height:64,
                uploaded_at:1, trackpoint_origin:'bottom-left', analysis_read_only:true,
                status:'ready', last_frame_tracked:0
            }, new URLSearchParams(location.search).get('src'), {
                0:{markers:[{label:'Apex', x:12, y:17}]}, 1:{markers:[]}, 2:{markers:[]}
            }, '', false, {initialFrame:1});
            window.emptyBoundaryReloadPreserved = window.playerController.get_markers().length === 0;
            await window.playerController.goto_frame(3);
            window.emptyBoundaryReloadPreserved &&= window.playerController.get_markers().length === 0;
            window.playerController = await module.trace_movie_frames('div#tracer', {
                movie_id:'probe', total_frames:4, frame_height_px:64, width:64, height:64,
                uploaded_at:1, trackpoint_origin:'bottom-left', analysis_read_only:true,
                status:'ready', last_frame_tracked:-1
            }, new URLSearchParams(location.search).get('src'), {0:{markers:[]}}, '', false);
            window.emptyFirstFramePreserved = window.playerController.get_markers().length === 0;
            await window.playerController.goto_frame(3);
            done(true);
        }).catch(error => done(error.message));
    """)
    assert chrome_driver.execute_script('return window.playerController.frame_number;') == 3
    assert chrome_driver.execute_script(
        'return window.emptyBoundaryReloadPreserved && window.emptyFirstFramePreserved;')
    assert chrome_driver.execute_script('return window.playerController.get_markers();') == []
    # A tracking frontier alone does not make a one-frame player trimmable.
    chrome_driver.execute_script("""
        const c = window.playerController;
        c.frames = c.frames.slice(0, 1);
        c.last_tracked_frame = 3;
        c.refreshTrimControls();
    """)
    assert not chrome_driver.find_element(By.CSS_SELECTOR, '#tracer .show_trim_controls').is_enabled()
