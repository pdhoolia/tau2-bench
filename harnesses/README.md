# tau2-harnesses — a Claude Code plugin marketplace

Higher-order **harnesses** for the [tau2-bench](../README.md) customer-service
domains, packaged as [Claude Code plugins](https://code.claude.com/docs).

This is the applied home of the position pieces in
[`docs/vision/`](../docs/vision/from-agents-to-harnesses.html): instead of cramming
a domain's whole policy into one system prompt, we treat each domain as a
**domain-specific harness** over Claude Code — soft judgment as *skills*, arithmetic
as *scripts*, and hard invariants as deterministic *hooks the agent cannot route
around* — over the fork's existing [MCP tool servers](../src/tau2/mcp/).

## Status

Incremental build. The marketplace currently ships **two** plugins:

| Plugin           | Domain  | State                                                       |
| ---------------- | ------- | ----------------------------------------------------------- |
| `retail-harness` | retail  | Scaffold complete — skills, script, hook, sub-agent, MCP.   |
| `legal-harness`  | legal   | Scaffold complete — skills, scripts, hook, sub-agent, MCP.  |
| _airline_        | airline | Planned.                                                    |
| _telecom_        | telecom | Planned.                                                    |

The tau2 evaluation bridge (an `--agent claude_harness` wrapper that drives
`claude -p` and reconciles MCP tool calls back into the tau2 trajectory) is now
domain-aware — it picks the right MCP server, plugin, and per-task DB seeder from
the domain under test (`retail` and `legal` today). See
[`src/tau2/agent/claude_harness/`](../src/tau2/agent/claude_harness).
To run an evaluation of a harness plugin (and its baseline) end-to-end, follow the
**[evaluation playbook](docs/tau2-playbook.md)** — preflight, smoke run, full run, and the
`run_eval.sh` shortcut, with all models routed through a LiteLLM gateway.

To instead evaluate a harness **in-situ** (inside a live Claude Code session, with the
user simulator on a **local MLX model** and the agent on the Claude subscription), see
the **[in-situ benchmark playbook](docs/insitu-playbook.md)** — MLX setup, preflight, smoke,
the multi-task suite runner, and the parity gate. This uses the domain-agnostic
[`tau2-eval`](plugins/tau2-eval) plugin paired with the domain harness under test.

## Layout

```
harnesses/
├── .claude-plugin/marketplace.json     # this marketplace
└── plugins/
    ├── retail-harness/                  # see plugins/retail-harness/README.md
    └── legal-harness/                   # see plugins/legal-harness/README.md
```

## Try it (manual, today)

1. Start the retail MCP server from the repo root (needs `uv sync --extra mcp`):

   ```bash
   python -m tau2.mcp.unified_server --port 8000
   # retail tools served at http://localhost:8000/mcp/retail
   ```

2. In a Claude Code session, add this marketplace and install the plugin:

   ```
   /plugin marketplace add ./harnesses
   /plugin install retail-harness@tau2-harnesses
   ```

3. Play the agent against a retail task by hand to watch the skills disclose, the
   `price_delta.py` script compute, and the PreToolUse hook deny an out-of-policy
   write before it reaches the tool.
