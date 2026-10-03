#!/usr/bin/env bash
set -u

if ! command -v xrandr >/dev/null 2>&1 || [[ -z "${DISPLAY:-}" ]]; then
  exit 0
fi

output="$(xrandr --query | awk '$2 == "connected" { print $1; exit }')"
if [[ -z "$output" ]]; then
  exit 0
fi

mode="1360x768_60.00"
xrandr --newmode "$mode" 84.75 1360 1432 1568 1776 768 771 781 798 -hsync +vsync 2>/dev/null || true
xrandr --addmode "$output" "$mode" 2>/dev/null || true
xrandr --dpi 96 --output "$output" --mode "$mode"
