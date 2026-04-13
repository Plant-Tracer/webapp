#!/bin/bash

set -euo pipefail

CWD="${1:?working directory required}"
CMD="${2:?command required}"

escape_for_applescript() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

SCRIPT_CMD="cd $(printf '%q' "$CWD") && $CMD"
SCRIPT_CMD_ESCAPED="$(escape_for_applescript "$SCRIPT_CMD")"

if command -v osascript >/dev/null 2>&1; then
  if osascript -e 'id of application "iTerm"' >/dev/null 2>&1; then
    osascript <<EOF
tell application "iTerm"
  activate
  create window with default profile
  tell current session of current window
    write text "$SCRIPT_CMD_ESCAPED"
  end tell
end tell
EOF
    exit 0
  fi

  osascript <<EOF
tell application "Terminal"
  activate
  do script "$SCRIPT_CMD_ESCAPED"
end tell
EOF
  exit 0
fi

echo "Unable to open a macOS terminal window automatically."
echo "Please run this in another terminal:"
echo "  $SCRIPT_CMD"
exit 1
