#!/usr/bin/env bash
# Run a tau2 evaluation with the AGENT routed through a Strata gateway.
#
# Defaults are the smallest useful run: airline, task 0, 1 trial, concurrency 1.
# Override with env vars or pass extra `tau2 run` flags after `--`.
#
#   scripts/strata/run.sh                                  # smoke
#   TASK_IDS="0 1 2" NUM_TRIALS=3 MAX_CONCURRENCY=8 scripts/strata/run.sh   # load
#   scripts/strata/run.sh -- --verbose-logs                 # extra tau2 flags
#
# Requires in .env: LITELLM_PROXY_API_BASE / LITELLM_PROXY_API_KEY (user-sim and
# judges go direct to LiteLLM) and the Strata gateway up at TAU2_STRATA_BASE.
set -euo pipefail
cd "$(dirname "$0")/../.."
# Load .env with the same parser tau2 uses (plain `source` chokes on JSON values).
if [ -f .env ]; then
  eval "$(uv run python -c 'import shlex; from dotenv import dotenv_values; print("\n".join(f"export {k}={shlex.quote(v)}" for k, v in dotenv_values(".env").items() if v is not None))')"
fi

: "${TAU2_STRATA_BASE:=http://127.0.0.1:8080}"
: "${TAU2_STRATA_CALLS:=agent_response}"
: "${DOMAIN:=airline}"
: "${TASK_IDS:=0}"
: "${NUM_TRIALS:=1}"
: "${MAX_CONCURRENCY:=1}"
: "${AGENT_LLM:=litellm_proxy/aws/claude-sonnet-4-5}"
: "${USER_LLM:=litellm_proxy/aws/claude-haiku-4-5}"
: "${TAU2_LLM_NL_ASSERTIONS:=litellm_proxy/aws/claude-sonnet-4-5}"
: "${TAU2_LLM_ENV_INTERFACE:=litellm_proxy/aws/claude-sonnet-4-5}"
: "${TAU2_LLM_EVAL_USER_SIMULATOR:=litellm_proxy/aws/claude-sonnet-4-5}"
: "${SAVE_TO:=strata-${DOMAIN}-$(date +%Y%m%d-%H%M%S)}"
export TAU2_STRATA_BASE TAU2_STRATA_CALLS TAU2_LLM_NL_ASSERTIONS \
  TAU2_LLM_ENV_INTERFACE TAU2_LLM_EVAL_USER_SIMULATOR

# ── preflight ────────────────────────────────────────────────────────────
[ -n "${LITELLM_PROXY_API_BASE:-}" ] || { echo "LITELLM_PROXY_API_BASE unset (see .env.example)"; exit 1; }
curl -sf -m 5 "$TAU2_STRATA_BASE/health" >/dev/null || { echo "Strata gateway not healthy at $TAU2_STRATA_BASE"; exit 1; }
curl -sf -m 15 "$TAU2_STRATA_BASE/litellm/v1/models" -H "Authorization: Bearer ${TAU2_STRATA_API_KEY:-strata-tenant-credential}" \
  | grep -q "\"${AGENT_LLM#litellm_proxy/}\"" || { echo "$AGENT_LLM not listed via Strata → LiteLLM"; exit 1; }
[[ "$AGENT_LLM" == litellm_proxy/* ]] || { echo "AGENT_LLM must be litellm_proxy/<name> to honor api_base"; exit 1; }

echo "domain=$DOMAIN tasks=[$TASK_IDS] trials=$NUM_TRIALS concurrency=$MAX_CONCURRENCY"
echo "agent=$AGENT_LLM via $TAU2_STRATA_BASE ($TAU2_STRATA_CALLS) | user=$USER_LLM direct | save_to=$SAVE_TO"

# shellcheck disable=SC2086
uv run tau2 run \
  --domain "$DOMAIN" \
  --agent llm_agent --agent-llm "$AGENT_LLM" \
  --user-llm "$USER_LLM" \
  --task-ids $TASK_IDS --num-trials "$NUM_TRIALS" --max-concurrency "$MAX_CONCURRENCY" \
  --save-to "$SAVE_TO" "$@"

echo "results: data/simulations/$SAVE_TO/results.json"
echo "strata:  $TAU2_STRATA_BASE/api/conversations  (ids tau2-<simulation_id>)"
