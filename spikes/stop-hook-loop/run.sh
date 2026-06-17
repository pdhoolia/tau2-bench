#!/usr/bin/env bash
# Phase 0 spike runner: does a Stop hook drive a multi-turn loop by injecting user turns?
#
# Launches `claude -p` with a Stop hook (user_sim_stub.py) wired via --settings, then
# analyzes the stream-json log. The opening prompt asks for TURN-A; the hook injects
# follow-ups that ask for TURN-B/C/D. If the assistant emits B/C/D, injection works.
set -euo pipefail

SPIKE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SPIKE_DIR}/../.." && pwd)"
RUNTIME="${SPIKE_DIR}/.runtime"

# Fresh state every run.
rm -rf "${RUNTIME}"
mkdir -p "${RUNTIME}"

OPENING="We are testing a turn loop. Reply with exactly the token TURN-A and nothing else."

cd "${REPO_ROOT}"
export CLAUDE_PROJECT_DIR="${REPO_ROOT}"

echo "Running claude -p with Stop-hook injection (this drives several turns)..."
set +e
claude -p "${OPENING}" \
  --settings "${SPIKE_DIR}/settings.json" \
  --output-format stream-json \
  --verbose \
  --include-hook-events \
  --max-turns 12 \
  > "${RUNTIME}/run.log" 2>&1
echo "claude exit=$? (log: ${RUNTIME}/run.log)"
set -e

echo
python3 "${SPIKE_DIR}/analyze.py"
