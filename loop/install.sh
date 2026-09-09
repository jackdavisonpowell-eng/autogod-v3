#!/usr/bin/env bash
# loop/install.sh — install the lane units as SYSTEM units (sudo). Does not
# enable the timers: the fleet layout daemon starts/stops them as the rack's
# "auto"/"chat" mode (layout.py ROLES[...]["with"]). `./loop/install.sh` then
# `swarm rack default` (or deepwork) and the lane runs.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for L in a b; do
    sudo -n cp "$HERE/systemd/autogod-v3-$L.service" "$HERE/systemd/autogod-v3-$L.timer" /etc/systemd/system/
done
sudo -n systemctl daemon-reload
systemctl list-unit-files 'autogod-v3-*' --no-legend
