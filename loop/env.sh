#!/usr/bin/env bash
# loop/env.sh — environment for every `claude` invocation the v3 loop makes.
# Sourced by loop/drivers/claude_code.py and loop/pass.sh, never executed.
# Values already exported by the caller win (${VAR:-default}).

export AUTOGOD_LANE="${AUTOGOD_LANE:-a}"

# Lane a = AUTOGOD 1 (autogod-brain.service :11466 — the P100 pair under `default`, the V100 under `deep work`)
#          behind the adapter proxy :11499.
# Lane b = AUTOGOD 2 (autogod-brain-2.service :11467, the P100 pair)
#          behind the adapter proxy :11498.
if [ "$AUTOGOD_LANE" = "b" ]; then
    export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-http://127.0.0.1:11498}"
    export AUTOGOD_BRAIN_URL="${AUTOGOD_BRAIN_URL:-http://127.0.0.1:11467}"
    export AUTOGOD_BUDGET_SCALE="${AUTOGOD_BUDGET_SCALE:-1.6}"
else
    export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-http://127.0.0.1:11499}"
    export AUTOGOD_BRAIN_URL="${AUTOGOD_BRAIN_URL:-http://127.0.0.1:11466}"
    export AUTOGOD_BUDGET_SCALE="${AUTOGOD_BUDGET_SCALE:-1.0}"
fi

export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-local}"
export ANTHROPIC_DEFAULT_OPUS_MODEL="${ANTHROPIC_DEFAULT_OPUS_MODEL:-autogod}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${ANTHROPIC_DEFAULT_SONNET_MODEL:-autogod}"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="${ANTHROPIC_DEFAULT_HAIKU_MODEL:-autogod}"
# Claude Code's own extended-thinking budget; the adapter proxy clamps it too.
export MAX_THINKING_TOKENS="${MAX_THINKING_TOKENS:-3072}"
export CLAUDE_CODE_ATTRIBUTION_HEADER="${CLAUDE_CODE_ATTRIBUTION_HEADER:-0}"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="${CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC:-1}"

export VAULT="${VAULT:-$HOME/vault}"
export AUTOGOD_ROOT="${AUTOGOD_ROOT:-$HOME/autogod-v3}"
export AUTOGOD_STATE_DIR="${AUTOGOD_STATE_DIR:-$AUTOGOD_ROOT/state}"
export AUTOGOD_LAB="${AUTOGOD_LAB:-$HOME/lab}"
# guard.py gates WebSearch on phase=build; every v3 stage may search.
export AUTOGOD_PHASE="${AUTOGOD_PHASE:-build}"

_nvm_bin="$(ls -d "$HOME"/.nvm/versions/node/v22*/bin 2>/dev/null | tail -1)"
[ -n "$_nvm_bin" ] && export PATH="$_nvm_bin:$PATH"
