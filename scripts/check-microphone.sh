#!/usr/bin/env bash
set -Eeuo pipefail

echo "USB devices:"
lsusb
echo
echo "ALSA capture devices:"
arecord -l
echo

mic_device=""
for card_path in /sys/class/sound/card[0-9]*; do
  [[ -e "$card_path" ]] || continue
  card_number="${card_path##*card}"
  resolved="$(readlink -f "$card_path/device" 2>/dev/null || true)"
  [[ "$resolved" == *"/usb"* ]] || continue
  card_id="$(cat "/proc/asound/card${card_number}/id")"
  device_number="$(arecord -l | sed -n "s/^card ${card_number}:.*device \([0-9][0-9]*\):.*/\1/p" | head -1)"
  [[ -n "$device_number" ]] || continue
  mic_device="plughw:CARD=${card_id},DEV=${device_number}"
  break
done

if [[ -z "$mic_device" ]]; then
  echo "ERROR: No USB microphone/audio adapter is detected."
  echo "Reconnect the Movo USB adapter to a data-capable port on the powered USB-C hub."
  exit 1
fi

echo "Detected microphone: $mic_device"
if [[ "${1:-}" == "--watch" ]]; then
  echo "Watching Alfred's live recognizer. Say: Alfred, Computer, or Jarvis."
  echo "Press Ctrl+C to stop watching; Alfred itself keeps listening."
  exec watch -n 0.5 -t curl -fsS http://127.0.0.1:8080/api/voice/status
fi
if [[ "${1:-}" != "--record" ]]; then
  echo "Detection passed. Run '$0 --watch' to see live wake-word recognition."
  echo "The --record test requires stopping Alfred first because its listener owns the mic."
  exit 0
fi

recording="$(mktemp --suffix=.wav /tmp/alfred-mic-test.XXXXXX)"
trap 'rm -f -- "$recording"' EXIT
echo "Speak normally for five seconds..."
arecord -q -D "$mic_device" -t wav -f S16_LE -r 16000 -c 1 -d 5 "$recording"
echo "Playing the recording through the TV..."
pw-play "$recording"
echo "Microphone record/playback test complete."
