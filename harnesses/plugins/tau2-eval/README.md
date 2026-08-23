# tau2-eval — in-situ benchmark runner (Claude Code plugin)

Runs a tau2-bench evaluation **inside a live Claude Code session**, inverting the usual
setup where tau2 drives `claude -p` from the outside. Here the session *is* the
agent-under-test and tau2 is the guest. See [`harnesses/docs/higher-order-harness.md`](../../docs/higher-order-harness.md)
for the full design and rationale.

## How it works

```
/tau2-eval (run_insitu.py)
  ├─ user-sim opening turn        (eval_insitu.usersim + model_gateway)
  ├─ eval-control server lane     (eval_insitu.eval_control_server, own port + world)
  └─ one `claude -p` session:
       ├─ domain harness plugin   ← agent-under-test (skills + PreToolUse hooks + MCP)
       └─ tau2-eval plugin        ← this: a Stop hook plays the user simulator
  → parse transcript → score with tau2's canonical evaluator (parity by reuse)
```

The **Stop hook** (`hooks/hooks.json` → `python -m tau2.eval_insitu.hook_logic`) fires
each time the agent finishes a turn: it reads the agent's new user-facing text, asks the
tau2 user-simulator for the next user turn, and either injects it
(`{"decision":"block","reason": …}`) or lets the session stop when the user is done.
This continuation mechanism is validated by the Phase 0 spike
([`spikes/stop-hook-loop/`](../../../spikes/stop-hook-loop/)).

## Why two plugins

`tau2-eval` is **domain-agnostic** — it provides only the eval loop. Pair it with the
domain harness under test (e.g. `legal-harness`), which supplies the skills, PreToolUse
guardrail hooks, and MCP connector. Plugin hooks do not propagate to sub-agents, so the
agent-under-test must be the main session — hence this runner-as-Stop-hook shape.

## Run

```bash
python -m tau2.eval_insitu.run_insitu \
  --domain legal --task-id intake_happy_path \
  --harness-plugin-dir harnesses/plugins/legal-harness \
  --tau2-eval-plugin-dir harnesses/plugins/tau2-eval \
  --run-dir /tmp/insitu-legal-1 \
  --model <agent-model>            # agent-under-test (subscription Claude)
```

User-sim / judge models are configured via the gateway env vars (local MLX by default).
**Local MLX setup runbook:** [`harnesses/docs/mlx-user-sim-setup.md`](../../docs/mlx-user-sim-setup.md)
(install → serve → configure → `python -m tau2.eval_insitu.preflight` → run). Design
rationale in `harnesses/docs/higher-order-harness.md` §7; env examples in `.env.example`
(`TAU2_USER_SIM_*`). Zero-setup fallback: `TAU2_USER_SIM_PROVIDER=claude_cli`.

## Prerequisites

- A runnable `claude` CLI with MCP tool calls permitted: a **non-root** user (root
  rejects `bypassPermissions`) or the tool allowlist the runner writes into `settings.json`.
- `uv sync --extra mcp` (FastMCP for the eval-control server).
- A reachable user-sim model endpoint (local MLX server, the LiteLLM proxy, or a cloud key).

## Status

Phase 2 (single-task vertical slice). Phase 3 is the parity gate: in-situ scores must
match `tau2 run` across the legal 12-task set.
