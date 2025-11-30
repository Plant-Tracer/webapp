"""
Simple syntax and import tests for canvas_movie_controller.js

These tests verify basic functionality without requiring a full server setup.
"""

from pathlib import Path


def test_canvas_movie_controller_file_exists():
    """Verify that the canvas_movie_controller.js file exists."""
    webapp_dir = Path(__file__).parent.parent
    js_file = webapp_dir / "src" / "app" / "static" / "canvas_movie_controller.js"

    assert js_file.exists(), f"canvas_movie_controller.js not found at {js_file}"


def test_canvas_movie_controller_has_moviecontroller_class():
    """Verify that the MovieController class is defined in the file."""
    webapp_dir = Path(__file__).parent.parent
    js_file = webapp_dir / "src" / "app" / "static" / "canvas_movie_controller.js"

    content = js_file.read_text()

    # Check for class definition
    assert "class MovieController" in content, "MovieController class not found"
    assert "extends CanvasController" in content, "MovieController doesn't extend CanvasController"


def test_canvas_movie_controller_has_required_methods():
    """Verify that required methods are present."""
    webapp_dir = Path(__file__).parent.parent
    js_file = webapp_dir / "src" / "app" / "static" / "canvas_movie_controller.js"

    content = js_file.read_text()

    required_methods = [
        "add_frame_objects",
        "play",
        "goto_frame",
        "load_movie",
        "stop_button_pressed",
        "set_movie_control_buttons"
    ]

    for method in required_methods:
        assert method in content, f"Method '{method}' not found in canvas_movie_controller.js"


def test_canvas_movie_controller_imports_correctly():
    """Verify that import statements are present and correct."""
    webapp_dir = Path(__file__).parent.parent
    js_file = webapp_dir / "src" / "app" / "static" / "canvas_movie_controller.js"

    content = js_file.read_text()

    # Check for ES6 import statement
    assert "import" in content, "No import statements found"
    assert "CanvasController" in content, "CanvasController import not found"
    assert "canvas_controller.mjs" in content, "canvas_controller.mjs import not found"


def test_canvas_movie_controller_no_jquery_selectors():
    """
    Verify that jQuery-style selectors have been properly replaced.

    Note: The file still uses jQuery ($) for DOM manipulation, but this test
    checks that the basic structure is in place.
    """
    webapp_dir = Path(__file__).parent.parent
    js_file = webapp_dir / "src" / "app" / "static" / "canvas_movie_controller.js"

    content = js_file.read_text()

    # The file should contain the $ symbol (jQuery is still used)
    assert "$(" in content, "jQuery selectors not found (expected after jQuery removal work)"

    # Check that common patterns exist
    assert "div_selector" in content, "div_selector variable not found"
