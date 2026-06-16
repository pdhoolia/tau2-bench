#!/usr/bin/env bash
#
# run_eval.sh — run tau2-bench evaluations through a LiteLLM gateway.
#
# Runs the standard `llm_agent` baseline and/or the `claude_harness` (domain-specific
# higher-order harness) agent, exactly as described in harnesses/playbook.md.
#
# Usage:
#   harnesses/run_eval.sh <domain> <smoke|full> [baseline|harness|both]
#
#   <domain>          retail | legal | airline | telecom | mock | ...
#                     (harness plugins exist for: retail, legal)
#   <smoke|full>      smoke = 1 task (fast wiring check); full = the whole split
#   [target]          which agent(s) to run (default: both)
#
# Model selection (bare gateway PUBLIC names; SDK paths get the litellm_proxy/ prefix):
#   TAU2_AGENT_MODEL          default: aws/claude-sonnet-4-5
#   TAU2_USER_MODEL           default: aws/claude-sonnet-4-5
# Run sizing (full mode only):
#   TAU2_NUM_TRIALS           default: 1   (use >1 for pass^k)
#   TAU2_BASELINE_CONCURRENCY default: 4
#   TAU2_HARNESS_CONCURRENCY  default: 2   (each harness task spawns an MCP server + claude)
#
# Gateway config (secret + base URL) lives in .env — see AGENTS.md "LiteLLM gateway".
# The judge/evaluator models are set there too (TAU2_LLM_*), not here.
set -euo pipefail

DOMAIN="${1:-}"
MODE="${2:-}"
TARGET="${3:-both}"

usage() {
  sed -n '3,33p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 1
}

[[ -z "$DOMAIN" || -z "$MODE" ]] && usage
case "$MODE" in smoke | full) ;; *) echo "ERROR: mode must be 'smoke' or 'full'"; usage ;; esac
case "$TARGET" in baseline | harness | both) ;; *) echo "ERROR: target must be baseline|harness|both"; usage ;; esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

AGENT_MODEL="${TAU2_AGENT_MODEL:-aws/claude-sonnet-4-5}"
USER_MODEL="${TAU2_USER_MODEL:-aws/claude-sonnet-4-5}"
export TAU2_AGENT_MODEL="$AGENT_MODEL"  # so preflight heredocs see the same value

# claude_harness ships a domain harness for these domains today; others run
# baseline-only until a harness plugin exists for them.
HARNESS_DOMAINS=" retail legal "
if [[ "$TARGET" != baseline && "$HARNESS_DOMAINS" != *" $DOMAIN "* ]]; then
  echo ">> claude_harness has no harness for '$DOMAIN' yet; running baseline only."
  TARGET=baseline
fi

# Run sizing.
if [[ "$MODE" == smoke ]]; then
  NUM_TASKS_ARGS=(--num-tasks 1)
  NUM_TRIALS=1
  BASE_CONC=1
  HARNESS_CONC=1
else
  NUM_TASKS_ARGS=()
  NUM_TRIALS="${TAU2_NUM_TRIALS:-1}"
  BASE_CONC="${TAU2_BASELINE_CONCURRENCY:-4}"
  HARNESS_CONC="${TAU2_HARNESS_CONCURRENCY:-2}"
fi
# bash 3.2-safe expansion of a possibly-empty array under `set -u`.
tasks() { printf '%s\n' "${NUM_TASKS_ARGS[@]+"${NUM_TASKS_ARGS[@]}"}"; }

preflight_sdk() {
  echo ">> preflight: LiteLLM SDK -> proxy (/v1/chat/completions)"
  uv run python - <<'PY'
from tau2 import config  # loads .env
import os, litellm
base, key = os.getenv("LITELLM_PROXY_API_BASE"), os.getenv("LITELLM_PROXY_API_KEY")
assert base and key, "LITELLM_PROXY_API_BASE / LITELLM_PROXY_API_KEY not set (see .env / AGENTS.md)"
model = "litellm_proxy/%s" % os.environ.get("TAU2_AGENT_MODEL", "aws/claude-sonnet-4-5")
r = litellm.completion(model=model, messages=[{"role": "user", "content": "say ok"}], max_tokens=8)
print("   SDK ok ->", (r.choices[0].message.content or "").strip())
PY
}

preflight_messages() {
  echo ">> preflight: Anthropic /v1/messages (claude_harness path)"
  uv run python - <<'PY'
from tau2 import config  # loads .env
import os, json, urllib.request
base, tok = os.environ.get("ANTHROPIC_BASE_URL"), os.environ.get("ANTHROPIC_AUTH_TOKEN")
assert base and tok, "ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN not set (see .env / AGENTS.md)"
payload = {"model": os.environ.get("TAU2_AGENT_MODEL", "aws/claude-sonnet-4-5"),
           "max_tokens": 16, "messages": [{"role": "user", "content": "ping"}]}
req = urllib.request.Request(base.rstrip("/") + "/v1/messages", data=json.dumps(payload).encode(),
    headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
             "x-api-key": tok, "authorization": "Bearer " + tok})
print("   messages ok ->", urllib.request.urlopen(req, timeout=30).read().decode()[:120])
PY
}

run_baseline() {
  local save="${DOMAIN}_${MODE}_baseline"
  echo ">> baseline (llm_agent) on '$DOMAIN' -> data/simulations/$save"
  uv run tau2 run --domain "$DOMAIN" \
    --agent llm_agent --agent-llm "litellm_proxy/$AGENT_MODEL" \
    --user-llm "litellm_proxy/$USER_MODEL" \
    $(tasks) --num-trials "$NUM_TRIALS" --max-concurrency "$BASE_CONC" \
    --save-to "$save"
}

run_harness() {
  local save="${DOMAIN}_${MODE}_harness"
  echo ">> claude_harness on '$DOMAIN' -> data/simulations/$save"
  uv run tau2 run --domain "$DOMAIN" \
    --agent claude_harness --agent-llm "$AGENT_MODEL" \
    --user-llm "litellm_proxy/$USER_MODEL" \
    $(tasks) --num-trials "$NUM_TRIALS" --max-concurrency "$HARNESS_CONC" \
    --save-to "$save"
}

echo "=== tau2 eval: domain=$DOMAIN mode=$MODE target=$TARGET agent=$AGENT_MODEL user=$USER_MODEL ==="
preflight_sdk
[[ "$TARGET" != baseline ]] && preflight_messages

case "$TARGET" in
  baseline) run_baseline ;;
  harness)  run_harness ;;
  both)     run_baseline; run_harness ;;
esac

echo "=== done. Review with:  uv run tau2 view ==="
