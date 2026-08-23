# Setting up the MLX user-sim gateway (Apple Silicon)

Step-by-step setup for running the in-situ harness's **user simulator** on a **local MLX
model** — a Qwen 8-bit model served on a 64 GB unified-RAM Apple-Silicon Mac via an
OpenAI-compatible endpoint. The agent-under-test stays on the Claude subscription; the
user-sim runs locally, minimizing API cost and latency.

Trajectory **scoring** is a separate seam and does *not* use this MLX endpoint — most
checks are deterministic (no model at all), and the one LLM-judged check has its own knob.
See [§7 What scores the run](#7-what-scores-the-run) below.

Background and design: [`higher-order-harness.md`](higher-order-harness.md) §7. This page
is the concrete runbook.

## 1. Install the MLX server (on the Mac)

```bash
pip install mlx-lm            # or: uv pip install mlx-lm
```

LM Studio (GUI) also works — load the model and "Start Server" (OpenAI-compatible,
usually on port 1234). The rest of this guide assumes `mlx_lm.server`.

## 2. Pick a model that fits 64 GB at 8-bit

| Model | Notes |
|---|---|
| **`mlx-community/Qwen3-30B-A3B-8bit`** (recommended) | MoE, ~3B active params → much faster on MLX; ~32 GB weights. Best latency for a user-sim. **Reasoning model — you MUST disable thinking** (see §4), else it spends the token budget on `<think>` and returns empty turns. |
| `mlx-community/Qwen2.5-32B-Instruct-8bit` | Dense, non-reasoning alternative, ~34 GB. Works out of the box, no thinking toggle needed. |

Both leave headroom for KV cache / context on a 64 GB machine. The user simulator is an
instruction-following role, so a 30–32B model is ample.

> **Reasoning vs. instruct.** Qwen3 is a *hybrid reasoning* model that thinks by default.
> For the user-sim role that's harmful (empty/truncated turns, latency, and the thinking
> text leaking into the conversation), so disable it via the env knobs in §4. A plain
> *instruct* model (e.g. Qwen2.5-32B-Instruct, or `Qwen3-30B-A3B-Instruct-2507-8bit`) needs
> no toggle. Disabling thinking does **not** degrade user-sim quality — role-play is
> instruction-following, which is exactly what non-thinking mode is for.

## 3. Serve it (OpenAI-compatible `/v1`)

```bash
mlx_lm.server --model mlx-community/Qwen3-30B-A3B-8bit --port 8080
# exposes http://<mac-host>:8080/v1/chat/completions
```

First run downloads the weights (tens of GB) — allow time. Leave this running.

## 4. Point the gateway at it (on the box running the eval)

The model gateway reads per-role env vars (`TAU2_<ROLE>_*`). For the user simulator:

```bash
export TAU2_USER_SIM_PROVIDER=mlx
export TAU2_USER_SIM_MODEL=mlx-community/Qwen3-30B-A3B-8bit   # must match the served name
export TAU2_USER_SIM_API_BASE=http://<mac-host>:8080/v1      # localhost if same machine
export TAU2_USER_SIM_API_KEY=mlx                             # dummy is fine for a local server
# Reasoning models (Qwen3) only — disable thinking, else turns come back empty:
export TAU2_USER_SIM_MAX_TOKENS=512
export TAU2_USER_SIM_EXTRA_BODY='{"chat_template_kwargs": {"enable_thinking": false}}'
```

`PROVIDER` / `MODEL` / `API_BASE` / `API_KEY` point the gateway at the server.
`MAX_TOKENS` and `EXTRA_BODY` are optional passthroughs to `litellm.completion` — needed
here to turn Qwen3's thinking off (a plain instruct model needs neither). Setting these in
your [`.env`](../../.env.example) is preferred over per-shell `export`s (the framework loads
`.env` automatically). The scoring model is configured separately — see
[§7](#7-what-scores-the-run); `TAU2_JUDGE_*` is **not** consumed by scoring today.

> `provider=mlx` routes through LiteLLM's `openai/` path. `TAU2_USER_SIM_MODEL` **must
> match** what the server loaded (mlx_lm.server echoes the model id) or you'll get a 404.

## 5. Verify before a full run

```bash
python -m tau2.eval_insitu.preflight --role USER_SIM
# [PASS] USER_SIM: OK (model=openai/mlx-community/Qwen3-30B-A3B-8bit, api_base=http://...:8080/v1): 'OK'
```

A `PASS` confirms the endpoint is reachable and the model answers through our stack.

## 6. Run an in-situ evaluation

```bash
python -m tau2.eval_insitu.run_insitu \
  --domain legal --task-id intake_happy_path \
  --harness-plugin-dir harnesses/plugins/legal-harness \
  --tau2-eval-plugin-dir harnesses/plugins/tau2-eval \
  --run-dir /tmp/insitu-legal --model <agent-model>
```

`--model` is the **agent-under-test** model (subscription Claude). The user-sim uses the
MLX config above. Result (with `reward`) is written to `<run-dir>/result.json`.

## 7. What scores the run

Scoring is **not** done by the MLX user-sim, and **not** by a `TAU2_JUDGE_*` role (the
gateway has a `JUDGE` role but nothing in the scoring path reads it). `run_insitu` scores
with tau2's canonical evaluator (`evaluate_simulation`, parity with `tau2 run`), which
combines whichever checks the task defines:

| Check | What it does | Uses an LLM? |
|---|---|---|
| **Action** | Replays the agent's tool calls against a fresh, task-seeded env | No — deterministic |
| **Env / DB-state** | Asserts final DB state | No — deterministic |
| **`communicate_info`** | Case-insensitive substring match in the agent's text | No — deterministic |
| **`nl_assertions`** | LLM-as-judge over the conversation | **Yes** — the only LLM-judged check |

So a task with **no `nl_assertions`** is scored **fully deterministically and locally** —
no scoring API key required. The runbook's `legal/intake_happy_path` is one such task
(action + `communicate_info` only), so it needs no scoring model at all.

When a task *does* have `nl_assertions`, the judge model is `TAU2_LLM_NL_ASSERTIONS`
(default **`gpt-4.1-2025-04-14`**, which needs `OPENAI_API_KEY`). To route it through your
proxy or a local server instead, set it explicitly — e.g.
`TAU2_LLM_NL_ASSERTIONS=litellm_proxy/<name>`, or
`TAU2_LLM_NL_ASSERTIONS=openai/<served-model>` with `OPENAI_API_BASE` pointed at your MLX
server. This is a different env var from the `TAU2_USER_SIM_*` / `TAU2_JUDGE_*` gateway
knobs.

## Notes & caveats

- **Run on a non-root user.** Root rejects `--permission-mode bypassPermissions`; the
  runner instead writes an exact MCP tool allowlist into `settings.json`, which works for
  non-interactive `claude -p`.
- **Tool-using user simulators (e.g. telecom).** MLX servers' OpenAI function-calling
  support is uneven. The legal/retail user-sims need no tools (fine on MLX); for
  tool-using domains, prefer a LiteLLM provider that supports function calling.
- **Zero-setup alternative.** `TAU2_USER_SIM_PROVIDER=claude_cli` runs the whole loop on
  the Claude subscription with no MLX/key — handy for demos; prefer MLX for
  cost-controlled benchmarking.
- **Concurrency.** Each parallel run gets its own eval-control lane; a single MLX server
  can back several lanes, but watch its throughput/context limits under load.
