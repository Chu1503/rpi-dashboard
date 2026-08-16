#!/bin/bash

cd "$HOME/pi-dashboard"

python3 -m http.server 8080 > /tmp/dashboard-server.log 2>&1 &

sleep 2

chromium \
    --kiosk \
    --disable-gpu \
    --no-first-run \
    --disable-session-crashed-bubble \
    http://localhost:8080