#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer with: sudo /home/arduino/Alfred/scripts/install-after-reflash.sh" >&2
  exit 1
fi

project_dir="/home/arduino/Alfred"
user_home="/home/arduino"
target_user="arduino"
target_group="arduino"

if [[ ! -x "$project_dir/.venv/bin/python" || ! -f "$project_dir/.env" ]]; then
  echo "Alfred must be deployed and its credentials restored before this installer runs." >&2
  exit 1
fi

install -D -m 0644 "$project_dir/systemd/alfred.service" /etc/systemd/system/alfred.service
install -d -o "$target_user" -g "$target_group" -m 0700 "$user_home/.config/autostart"
install -d -o "$target_user" -g "$target_group" -m 0755 "$user_home/.local/bin"
install -o "$target_user" -g "$target_group" -m 0755 \
  "$project_dir/scripts/never-lock-display.sh" "$user_home/.local/bin/never-lock-display.sh"

for desktop_file in "$project_dir"/config/autostart/*.desktop; do
  install -o "$target_user" -g "$target_group" -m 0600 \
    "$desktop_file" "$user_home/.config/autostart/$(basename "$desktop_file")"
done

runuser -u "$target_user" -- env HOME="$user_home" "$project_dir/install-kiosk-autostart.sh"
pkill -u "$target_user" -x xfce4-screensaver 2>/dev/null || true
pkill -u "$target_user" -x light-locker 2>/dev/null || true
pkill -u "$target_user" -x xscreensaver 2>/dev/null || true

wifi_connection="$(nmcli -t -f NAME,TYPE connection show --active 2>/dev/null | awk -F: '$NF == "802-11-wireless" {sub(/:802-11-wireless$/, ""); print; exit}')"
if [[ -n "$wifi_connection" ]]; then
  nmcli connection modify "$wifi_connection" 802-11-wireless.powersave 2 || true
fi

chmod +x "$project_dir/start-dashboard.sh" "$project_dir/scripts/"*.sh
systemctl daemon-reload
systemctl enable alfred.service
systemctl restart arduino-router.service || true
systemctl restart alfred.service

for _ in {1..40}; do
  if curl --fail --silent http://127.0.0.1:8080/healthz >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl --fail --silent http://127.0.0.1:8080/healthz >/dev/null; then
  echo "Alfred was installed but did not become healthy. Check: journalctl -u alfred.service -n 50" >&2
  exit 1
fi

runuser -u "$target_user" -- env HOME="$user_home" XDG_RUNTIME_DIR=/run/user/1000 \
  "$project_dir/scripts/configure-tv-audio.sh" || true

echo "Alfred system service, kiosk, no-lock behavior, and Wi-Fi settings are restored."
echo "No Linux reboot was performed. Log out and back in once to start the kiosk autostart."
