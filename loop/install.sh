#!/usr/bin/env bash
# loop/install.sh — install + enable the lane timers as systemd --user units on THIS box.
#   ./loop/install.sh        both lanes
#   ./loop/install.sh a      one lane
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"; mkdir -p "$UNIT_DIR"
LANES="${1:-a b}"
for L in $LANES; do
    cp "$HERE/systemd/autogod-v3-$L.service" "$HERE/systemd/autogod-v3-$L.timer" "$UNIT_DIR/"
done
systemctl --user daemon-reload
for L in $LANES; do systemctl --user enable --now "autogod-v3-$L.timer"; done
systemctl --user list-timers | grep autogod-v3 || true
