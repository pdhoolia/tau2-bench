#!/usr/bin/env bash
# Smoke test: can `claude` reach the eval-control MCP server and invoke a domain tool?
#
# Validates the in-situ MCP path independent of the user-sim loop: starts a legal
# eval-control server, points claude at it via --mcp-config, and asks for something that
# requires a tool call. PASS = a mcp__tau2-legal__* tool_use appears and the answer
# reflects the seeded DB. Works under root via the settings tool allowlist (no
# bypassPermissions). Requires an authenticated `claude` CLI and `uv sync --extra mcp`.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT="${PORT:-8123}"
RUN=/tmp/mcp-control-smoke
mkdir -p "$RUN"
cd "$REPO_ROOT"

uv run python -m tau2.mcp.eval_control_server --domain legal --port "$PORT" \
  > "$RUN/ctrl.log" 2>&1 &
CTRL_PID=$!
trap 'kill $CTRL_PID 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do
  curl -s "http://127.0.0.1:$PORT/admin/info" >/dev/null 2>&1 && break
  sleep 0.25
done
echo "server: $(curl -s http://127.0.0.1:$PORT/admin/info)"

cat > "$RUN/mcp.json" <<JSON
{"mcpServers":{"tau2-legal":{"type":"http","url":"http://127.0.0.1:$PORT/mcp/legal"}}}
JSON
cat > "$RUN/settings.json" <<JSON
{"permissions":{"allow":["mcp__tau2-legal__list_practitioners","mcp__tau2-legal__get_practitioner"]}}
JSON

timeout 120 claude -p "Use the tau2-legal MCP tools to list the firm's practitioners, then tell me how many there are. Call a tool; do not guess." \
  --output-format stream-json --verbose \
  --mcp-config "$RUN/mcp.json" --strict-mcp-config \
  --settings "$RUN/settings.json" --max-turns 6 > "$RUN/out.jsonl" 2>"$RUN/err.txt"

echo "=== domain tool calls ==="
grep -o '"name":"mcp__tau2-legal__[a-z_]*"' "$RUN/out.jsonl" | sort | uniq -c || echo "NONE"
