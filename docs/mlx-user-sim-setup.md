# Setting up the MLX user-sim gateway (Apple Silicon)

Step-by-step setup for running the in-situ harness's **user simulator** (and optionally
the NL-assertion **judge**) on a **local MLX model** — a Qwen 8-bit model served on a
64 GB unified-RAM Apple-Silicon Mac via an OpenAI-compatible endpoint. The
agent-under-test stays on the Claude subscription; user-sim + judge run locally,
minimizing API cost and latency.

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
| **`mlx-community/Qwen3-30B-A3B-8bit`** (recommended) | MoE, ~3B active params → much faster on MLX; ~32 GB weights. Best latency for a user-sim. |
| `mlx-community/Qwen2.5-32B-Instruct-8bit` | Dense alternative, ~34 GB. |

Both leave headroom for KV cache / context on a 64 GB machine. The user simulator is an
instruction-following role, so a 30–32B model is ample.

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
```

For the NL-assertion judge, set the same knobs with the `JUDGE` prefix
(`TAU2_JUDGE_PROVIDER`, …). See commented examples in [`.env.example`](../.env.example).

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
