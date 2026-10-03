#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -d .venv ]]; then
  echo "Missing .venv. Follow the Debian/UNO Q setup steps in README.md first."
  exit 1
fi

source .venv/bin/activate
mkdir -p data/logs

CONFIGURED_HOST="$(python -c 'from config import settings; print(settings.host)')"
ALFRED_HOST="${ALFRED_HOST:-$CONFIGURED_HOST}"
CONFIGURED_PORT="$(python -c 'from config import settings; print(settings.port)')"
ALFRED_PORT="${ALFRED_PORT:-$CONFIGURED_PORT}"
export ALFRED_HOST ALFRED_PORT

READY_URL="http://127.0.0.1:${ALFRED_PORT}/healthz"
SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if curl --fail --silent "$READY_URL" >/dev/null 2>&1; then
  echo "Alfred is already running at http://127.0.0.1:${ALFRED_PORT}"
else
  python -m waitress --listen="${ALFRED_HOST}:${ALFRED_PORT}" app:app >>data/logs/alfred.log 2>&1 &
  SERVER_PID=$!

  for _ in {1..80}; do
    if curl --fail --silent "$READY_URL" >/dev/null; then
      break
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "Alfred failed to start. Check data/logs/alfred.log."
      exit 1
    fi
    sleep 0.25
  done
fi

if ! curl --fail --silent "$READY_URL" >/dev/null; then
  echo "Alfred did not become ready. Check data/logs/alfred.log."
  exit 1
fi

"$SCRIPT_DIR/scripts/configure-tv-display.sh" || true
# Select HDMI before Chromium opens its persistent audio stream. If Chromium
# starts while the USB microphone adapter is default, that stream remains on
# the adapter even after PipeWire's default is corrected.
"$SCRIPT_DIR/scripts/configure-tv-audio.sh" || true
# RustDesk can restore a prior remote-session mode shortly after login. Reapply
# the physical TV mode once all desktop autostart programs have settled.
(
  sleep 8
  "$SCRIPT_DIR/scripts/configure-tv-display.sh" || true
  "$SCRIPT_DIR/scripts/configure-tv-audio.sh" &
) &

if command -v chromium >/dev/null 2>&1; then
  CHROMIUM_BIN="chromium"
elif command -v chromium-browser >/dev/null 2>&1; then
  CHROMIUM_BIN="chromium-browser"
else
  echo "Chromium is not installed or not on PATH. Alfred is running at http://127.0.0.1:${ALFRED_PORT}"
  if [[ -n "$SERVER_PID" ]]; then
    wait "$SERVER_PID"
  fi
  exit 0
fi

"$CHROMIUM_BIN" \
  --kiosk \
  --no-first-run \
  --disable-session-crashed-bubble \
  --disable-infobars \
  --autoplay-policy=no-user-gesture-required \
  --force-device-scale-factor=1 \
  --window-position=0,0 \
  --window-size=1360,768 \
  "http://127.0.0.1:${ALFRED_PORT}"
