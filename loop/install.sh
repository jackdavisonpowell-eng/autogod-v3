#!/usr/bin/env bash
# loop/install.sh — install the lane units as SYSTEM units (sudo). Does not
# start them: the fleet layout daemon starts/stops them as the rack's
# "auto"/"chat" mode (layout.py ROLES[...]["with"]). `./loop/install.sh` then
# `swarm rack default` (or deepwork) and the lane runs. There is no timer —
# each unit is the persistent loop itself (pass.sh loops on its own).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for L in a b; do
    sudo -n cp "$HERE/systemd/autogod-v3-$L.service" /etc/systemd/system/
    # old installs may still have a lane timer around; it is retired
    sudo -n rm -f "/etc/systemd/system/autogod-v3-$L.timer"
done
sudo -n systemctl daemon-reload
systemctl list-unit-files 'autogod-v3-*' --no-legend
