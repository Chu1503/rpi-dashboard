#!/usr/bin/env bash
set -u

# The USB microphone adapter also exposes a speaker output and WirePlumber may
# make it the default. Find the TV's HDMI sink explicitly, make it the default,
# and keep it at full PipeWire volume. The USB device remains available for
# capture, but can no longer steal Alfred/Chromium speech.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

if ! command -v wpctl >/dev/null 2>&1; then
  exit 0
fi

for _ in $(seq 1 30); do
  hdmi_sink="$({ wpctl status 2>/dev/null || true; } | awk '
    /HDMI Digital Stereo Output/ {
      for (field = 1; field <= NF; field++) {
        if ($field ~ /^[0-9]+\.$/) {
          sub(/\.$/, "", $field)
          print $field
          exit
        }
      }
    }
  ')"
  if [[ -n "$hdmi_sink" ]]; then
    wpctl set-default "$hdmi_sink"
    wpctl set-mute "$hdmi_sink" 0
    wpctl set-volume "$hdmi_sink" 1.0

    # Existing Chromium streams can stay attached to the USB adapter even
    # after the default changes. Move those streams immediately when wpctl
    # supports it; new streams already follow the default HDMI sink.
    if wpctl --help 2>&1 | grep -qE '(^|[[:space:]])move([[:space:]]|$)'; then
      wpctl status 2>/dev/null | awk '
        /[0-9]+\. Chromium[[:space:]]*$/ {
          for (field = 1; field <= NF; field++) {
            if ($field ~ /^[0-9]+\.$/) {
              sub(/\.$/, "", $field)
              print $field
              break
            }
          }
        }
      ' | while read -r stream; do
        wpctl move "$stream" "$hdmi_sink" 2>/dev/null || true
      done
    fi
    exit 0
  fi
  sleep 1
done

exit 0
