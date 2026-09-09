#!/usr/bin/env bash
# loop/pass.sh — one pass on one lane: check the brain is up, take the lane
# lock, run exactly one stage iteration. Exit 0 always (a bad pass must never
# wedge the timer). AUTOGOD_LANE=a|b picks the brain (see env.sh).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export AUTOGOD_ROOT="${AUTOGOD_ROOT:-$(cd "$HERE/.." && pwd)}"
export AUTOGOD_LANE="${AUTOGOD_LANE:-a}"
# shellcheck source=env.sh
source "$HERE/env.sh"
mkdir -p "$AUTOGOD_STATE_DIR"
LOG="$AUTOGOD_STATE_DIR/pass-$AUTOGOD_LANE.log"
ts() { date '+%F %T'; }

# The lesson of 2026-09-08: never spin on a brain that is not there.
if ! curl -s -m 5 "$AUTOGOD_BRAIN_URL/health" | grep -q '"ok"'; then
    echo "$(ts) [$AUTOGOD_LANE] brain $AUTOGOD_BRAIN_URL not up — skip" >> "$LOG"
    exit 0
fi
if ! curl -s -m 5 -o /dev/null -w '%{http_code}' "$ANTHROPIC_BASE_URL/v1/messages" | grep -qE '^(4|2)'; then
    echo "$(ts) [$AUTOGOD_LANE] proxy $ANTHROPIC_BASE_URL not up — skip" >> "$LOG"
    exit 0
fi

exec 9>"$AUTOGOD_STATE_DIR/lock-$AUTOGOD_LANE"
if ! flock -n 9; then
    echo "$(ts) [$AUTOGOD_LANE] pass already running — skip" >> "$LOG"
    exit 0
fi

echo "$(ts) [$AUTOGOD_LANE] pass start (scale $AUTOGOD_BUDGET_SCALE night=${AUTOGOD_NIGHT:-0})" >> "$LOG"
python3 "$HERE/stage.py" --lane "$AUTOGOD_LANE" --driver "${AUTOGOD_DRIVER:-claude_code}" >> "$LOG" 2>&1
echo "$(ts) [$AUTOGOD_LANE] pass end rc=$?" >> "$LOG"
exit 0
