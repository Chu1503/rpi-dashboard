#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
START_SCRIPT="$SCRIPT_DIR/start-dashboard.sh"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/alfred.desktop"

if [[ ! -f "$START_SCRIPT" ]]; then
  echo "Missing $START_SCRIPT"
  exit 1
fi

chmod +x "$START_SCRIPT"
mkdir -p "$AUTOSTART_DIR"

printf '%s\n' \
  '[Desktop Entry]' \
  'Type=Application' \
  'Name=Alfred Dashboard' \
  'Comment=Start Alfred in Chromium kiosk mode' \
  "Exec=\"$START_SCRIPT\"" \
  "Path=$SCRIPT_DIR" \
  'Terminal=false' \
  'X-GNOME-Autostart-enabled=true' \
  'X-GNOME-Autostart-Delay=8' \
  > "$DESKTOP_FILE"

chmod 600 "$DESKTOP_FILE"
echo "Installed $DESKTOP_FILE"
echo "Alfred will start after your graphical desktop login. Log out and back in, or reboot, to test it."
