#!/bin/bash
# Prevents your computer from sleeping by simulating a tiny keystroke every 60 seconds.
# Usage: bash nosleep.sh
# To stop: Ctrl+C

echo "Keeping your computer awake... Press Ctrl+C to stop."

while true; do
    sleep 60
    xdotool key shift
done
