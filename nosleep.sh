#!/bin/bash
# Prevents your computer from sleeping by resetting the idle timer every 59 seconds.
# No extra installs needed — uses xset which is already on your system.
# Usage: bash nosleep.sh
# To stop: Ctrl+C

echo "Keeping your computer awake... Press Ctrl+C to stop."

while true; do
    xset s reset
    sleep 59
done
