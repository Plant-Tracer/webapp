#!/bin/bash
# Manual Browser Testing Script for canvas_movie_controller.js
#
# This script helps you manually test the canvas movie controller
# with a local server and Chromium browser.
#
# Usage: bash tests/manual_browser_test.sh

set -e

echo "=================================="
echo "Canvas Movie Controller Manual Test"
echo "=================================="
echo

# Check if chromium is installed
if command -v chromium &> /dev/null; then
    BROWSER="chromium"
elif command -v chromium-browser &> /dev/null; then
    BROWSER="chromium-browser"
elif command -v google-chrome &> /dev/null; then
    BROWSER="google-chrome"
else
    echo "❌ Error: Chromium or Chrome not found!"
    echo "   Please install chromium:"
    echo "   - Ubuntu/Debian: sudo apt-get install chromium-browser"
    echo "   - macOS: brew install chromium --no-quarantine"
    exit 1
fi

echo "✓ Found browser: $BROWSER"
echo

# Check if server is running
if curl -s http://localhost:8080 > /dev/null 2>&1; then
    echo "✓ Local server is running at http://localhost:8080"
else
    echo "❌ Local server is NOT running!"
    echo
    echo "To start the server:"
    echo "  1. Set up local services:"
    echo "     make wipe-local"
    echo "     make make-local-demo"
    echo
    echo "  2. Start the Flask server:"
    echo "     make run-local-demo-debug"
    echo
    echo "  3. Run this script again"
    exit 1
fi

echo
echo "Opening test pages in Chromium..."
echo
echo "Testing pages:"
echo "  - /demo/tracer1"
echo "  - /demo/tracer2"
echo "  - /demo/tracer3"
echo
echo "What to check:"
echo "  1. Canvas element is visible"
echo "  2. No JavaScript errors in console (F12 → Console tab)"
echo "  3. Movie control buttons are present"
echo "  4. console.log messages appear when interacting:"
echo "     - 'add_frame_objects(frame)' when frames load"
echo "     - 'play(delta)' when play buttons are clicked"
echo
echo "Press Enter to open /demo/tracer1 in browser..."
read

# Open the browser
$BROWSER http://localhost:8080/demo/tracer1 &

echo
echo "✓ Browser opened!"
echo
echo "Manual testing instructions:"
echo "  1. Open DevTools (press F12)"
echo "  2. Go to Console tab"
echo "  3. Look for any errors (red text)"
echo "  4. Try clicking movie control buttons"
echo "  5. Verify console.log messages appear"
echo
echo "Press Enter when done to exit..."
read

echo
echo "Test completed!"
echo
echo "If you found any issues, please report them."
echo "=================================="
