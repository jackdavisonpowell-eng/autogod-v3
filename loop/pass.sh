#!/usr/bin/env bash
# loop/pass.sh — the v3 lane loop, lane a|b (AUTOGOD_LANE). Runs as a
# persistent systemd service (Type=simple, Restart=always) — NOT a timer.
# It holds the lane lock for its whole life and loops forever: check the
# brain is up, check the proxy is up, run exactly one stage iteration, then
# go straight into the next one. The instant one iteration ends, the next
# starts — there is no schedule to wait on. It only pauses (a short poll)
# when the brain or proxy is down, so it comes back the moment they're up.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export AUTOGOD_ROOT="${AUTOGOD_ROOT:-$(cd "$HERE/.." && pwd)}"
export AUTOGOD_LANE="${AUTOGOD_LANE:-a}"
# shellcheck source=env.sh
source "$HERE/env.sh"
mkdir -p "$AUTOGOD_STATE_DIR"
LOG="$AUTOGOD_STATE_DIR/pass-$AUTOGOD_LANE.log"
ts() { date '+%F %T'; }

# Only one pass.sh per lane, ever — held for the process's whole life, not
# re-acquired per cycle. systemd already guarantees this (one service unit
# per lane), the lock is a defense against a manual second run.
exec 9>"$AUTOGOD_STATE_DIR/lock-$AUTOGOD_LANE"
if ! flock -n 9; then
    echo "$(ts) [$AUTOGOD_LANE] another pass.sh is already running this lane — exiting" >> "$LOG"
    exit 1
fi

trap 'echo "$(ts) [$AUTOGOD_LANE] loop stopping" >> "$LOG"; exit 0' TERM INT

echo "$(ts) [$AUTOGOD_LANE] loop up (scale $AUTOGOD_BUDGET_SCALE night=${AUTOGOD_NIGHT:-0})" >> "$LOG"

while true; do
    # The lesson of 2026-09-08: never spin on a brain that is not there.
    if ! curl -s -m 5 "$AUTOGOD_BRAIN_URL/health" | grep -q '"ok"'; then
        echo "$(ts) [$AUTOGOD_LANE] brain $AUTOGOD_BRAIN_URL not up — waiting" >> "$LOG"
        sleep 30
        continue
    fi
    # the adapter proxy only speaks POST (a GET gets 501); any HTTP status means it is listening
    if ! curl -s -m 5 -o /dev/null -w '%{http_code}' "$ANTHROPIC_BASE_URL/v1/messages" | grep -qE '^[1-5][0-9][0-9]$'; then
        echo "$(ts) [$AUTOGOD_LANE] proxy $ANTHROPIC_BASE_URL not up — waiting" >> "$LOG"
        sleep 30
        continue
    fi
    echo "$(ts) [$AUTOGOD_LANE] pass start" >> "$LOG"
    python3 "$HERE/stage.py" --lane "$AUTOGOD_LANE" --driver "${AUTOGOD_DRIVER:-claude_code}" >> "$LOG" 2>&1
    rc=$?
    echo "$(ts) [$AUTOGOD_LANE] pass end rc=$rc" >> "$LOG"
    # a fresh iteration begins on the very next loop turn — no delay, no
    # timer; a beat is left only so a hard-failing loop doesn't spin the CPU
    sleep 1
done
