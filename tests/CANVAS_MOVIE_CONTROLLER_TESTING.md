# Testing canvas_movie_controller.js with Local Server and Chromium

This document describes how to test the `canvas_movie_controller.js` functionality using a local Flask server and Chromium browser.

## Overview

After removing jQuery from `canvas_movie_controller.js`, it's important to verify that the movie controller still works correctly in a real browser environment. These tests use Selenium with Chromium to automate browser testing.

## Prerequisites

1. Python 3.x with pip
2. Chromium or Chrome browser installed
3. Selenium Python package
4. Local development environment (DynamoDB Local and Minio)

## Quick Start

### Option 1: Automated Test (Recommended)

Run the comprehensive test suite:

```bash
# Install dependencies (if not already installed)
pip install --user selenium requests

# Run the canvas movie controller tests
pytest -v tests/canvas_movie_controller_test.py -s
```

### Option 2: Manual Integration Test with Local Server

For the most thorough testing, run the integration test with a real local server:

1. **Set up local services:**
   ```bash
   make wipe-local
   make make-local-demo
   ```

2. **Start the local Flask server** (in a separate terminal):
   ```bash
   make run-local-demo-debug
   ```
   
   This starts the server at `http://localhost:8080`

3. **Run the integration test:**
   ```bash
   pytest -v tests/canvas_movie_controller_test.py::test_canvas_movie_controller_with_running_server -s
   ```

## What is Tested

The test suite verifies:

1. **Page Loading**: Pages using `canvas_movie_controller.js` load without errors
2. **Canvas Initialization**: The canvas element is created and accessible
3. **Movie Controller Initialization**: The MovieController class initializes correctly
4. **Frame Navigation**: Movie control buttons are present and functional
5. **JavaScript Errors**: No severe JavaScript errors occur during page load and interaction
6. **Console Output**: Verifies that methods like `add_frame_objects()` and `play()` are called

## Test Pages

The tests use the following demo pages:

- `/demo/tracer1` - Basic tracer demo with canvas movie controller
- `/demo/tracer2` - Advanced tracer demo
- `/demo/tracer3` - Another tracer variant

## Debugging

### View Console Logs

To see all browser console logs (including `console.log` statements), run with verbose output:

```bash
pytest -v tests/canvas_movie_controller_test.py -s --log-cli-level=INFO
```

### Take Screenshots

The integration test automatically saves screenshots to `/tmp/canvas_movie_controller_test.png` for visual verification.

### Check for JavaScript Errors

The tests check for severe JavaScript errors in the browser console. If errors are found, they will be displayed in the test output.

## Common Issues

### Chromium Not Found

If you get an error about Chromium not being found:

```bash
# On Ubuntu/Debian
sudo apt-get install chromium-browser

# On macOS
brew install chromium --no-quarantine
```

### Server Not Running

If the integration test is skipped because the server isn't running:

1. Make sure DynamoDB Local and Minio are running
2. Start the Flask server with `make run-local-demo-debug`
3. Verify the server is accessible at `http://localhost:8080`

### Port Already in Use

If port 8080 is already in use, you can change the port:

```bash
# Set a custom port
LOCAL_HTTP_PORT=8081 make run-local-demo-debug
```

Then update the test fixture in `canvas_movie_controller_test.py` to use port 8081.

## CI/CD Integration

These tests are designed to work in CI/CD pipelines:

- Use headless Chromium (`--headless` flag)
- Automatically skip tests if the server isn't available
- Can be run with or without a local server

## Manual Browser Testing

For manual testing without Selenium:

1. Start the local server: `make run-local-demo-debug`
2. Open Chromium: `chromium http://localhost:8080/demo/tracer1`
3. Open DevTools (F12) and check the Console tab
4. Verify:
   - Canvas element is visible
   - No JavaScript errors in console
   - Movie controls (play, pause, next, prev) are present
   - `console.log` messages from `add_frame_objects()` and `play()` appear when interacting

## Additional Resources

- [Selenium Python Documentation](https://selenium-python.readthedocs.io/)
- [Chrome DevTools](https://developer.chrome.com/docs/devtools/)
- [Plant Tracer Development Guide](../README.md)
