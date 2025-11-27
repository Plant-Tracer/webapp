# Testing canvas_movie_controller.js with Selenium and Chromium

This document describes how to test the `canvas_movie_controller.js` functionality using Selenium with Chromium browser.

## Overview

After removing jQuery from `canvas_movie_controller.js`, it's important to verify that the movie controller still works correctly in a real browser environment. These tests use Selenium with Chromium to automate browser testing with a live Flask server running in a background thread.

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
6. **Console Output**: Verifies that methods work without producing severe console errors

## Key Features

- **Automatic Server**: Tests start Flask server in background thread automatically
- **No Connection Refused**: Uses embedded server, not external localhost connection
- **Clean Output**: Minimal logging, only shows failures
- **Graceful Degradation**: Skips tests if Chrome/Chromium not available

## Test Pages

The tests use the following demo pages:

- `/demo/tracer1` - Basic tracer demo with canvas movie controller
- `/demo/tracer2` - Advanced tracer demo
- `/demo/tracer3` - Another tracer variant

## Debugging

### View Browser Console Logs

To see all browser console logs, run with verbose output:

```bash
pytest -v tests/canvas_movie_controller_test.py -s
```

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

### Port Already in Use

If port 8765 (used by test server) is already in use, the tests will fail. The port is automatically selected to avoid conflicts with the default development server (8080).

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
