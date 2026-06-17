# In-situ benchmark playbook (higher-order harness + MLX)

End-to-end runbook for benchmarking a domain harness **in-situ** — inside a live Claude
Code session — with the **user simulator on a local MLX model** (Apple Silicon) and the
agent-under-test on the Claude subscription. This is the inverse of
[`playbook.md`](playbook.md) (which drives `claude -p` from tau2); design rationale lives
in [`../docs/higher-order-harness.md`](../docs/higher-order-harness.md).

> **When to use which.** In-situ (this playbook) = iterative harness dev, demos, and
> small/medium validate runs on subscription + local MLX (low cost/latency). The CLI
> `playbook.md` path remains fine for large unattended comparative sweeps.

---

## 1. Prerequisites

```bash
uv sync --extra mcp          # FastMCP for the eval-control server
uv run tau2 check-data       # sanity
```

- An **authenticated `claude` CLI** on PATH (`claude --version`).
- Run as a **non-root** user — root rejects `bypassPermissions`; the runner instead writes
  an exact MCP tool allowlist into `settings.json` (works for non-interactive `claude -p`).

## 2. Set up the MLX user-sim (on the Mac, 64 GB)

Full details: [`../docs/mlx-user-sim-setup.md`](../docs/mlx-user-sim-setup.md). Essentials:

```bash
pip install mlx-lm
mlx_lm.server --model mlx-community/Qwen3-30B-A3B-8bit --port 8080   # OpenAI-compatible /v1
```

`Qwen3-30B-A3B-8bit` (MoE, ~3B active) is the recommended fit for 64 GB — fast and ample
for a user-sim. `Qwen2.5-32B-Instruct-8bit` is a dense alternative.

## 3. Configure the gateway (on the eval box)

```bash
export TAU2_USER_SIM_PROVIDER=mlx
export TAU2_USER_SIM_MODEL=mlx-community/Qwen3-30B-A3B-8bit   # must match the served name
export TAU2_USER_SIM_API_BASE=http://<mac-host>:8080/v1      # localhost if same machine
export TAU2_USER_SIM_API_KEY=mlx                             # dummy ok locally
```

The agent-under-test model is passed per-run via `--model` (subscription Claude).

## 4. Preflight (verify before spending a run)

```bash
python -m tau2.eval_insitu.preflight --role USER_SIM
# [PASS] USER_SIM: OK (model=openai/mlx-community/Qwen3-30B-A3B-8bit, api_base=http://...:8080/v1): 'OK'
```

## 5. Smoke: one task in-situ

```bash
python -m tau2.eval_insitu.run_insitu \
  --domain legal --task-id intake_happy_path \
  --harness-plugin-dir harnesses/plugins/legal-harness \
  --tau2-eval-plugin-dir harnesses/plugins/tau2-eval \
  --run-dir /tmp/insitu-legal --model <agent-model>
cat /tmp/insitu-legal/result.json     # expect "reward": 1.0
```

## 6. Full benchmark suite

Runs every task (omit `--task-ids` for ALL), with optional trials and parallel lanes.
Concurrency is safe: each task gets its own eval-control lane/port/world.

```bash
python -m tau2.eval_insitu.suite \
  --domain legal \
  --harness-plugin-dir harnesses/plugins/legal-harness \
  --tau2-eval-plugin-dir harnesses/plugins/tau2-eval \
  --out-dir /tmp/insitu-legal-suite \
  --trials 3 --concurrency 2 --model <agent-model>
```

Output: a per-task table on stdout plus `<out-dir>/suite_result.json`
(`suite_reward`, `pass@1`, `per_task_reward`, and every run's `result.json`).

> One MLX server can back several lanes; raise `--concurrency` only as far as the MLX
> box's throughput/context allows. Start at 2.

## 7. Parity gate (in-situ vs canonical tau2)

Credibility check — in-situ rewards should match canonical `tau2 run` on the same tasks,
same models:

```bash
# canonical baseline via the claude_harness CLI path (same models)
tau2 run --domain legal --agent claude_harness \
  --agent-llm <agent-model> --user-llm <user-model> \
  --num-trials 3 --max-concurrency 2 --save-to data/simulations
tau2 view      # inspect per-task rewards
```

Compare `per_task_reward` in `suite_result.json` against the canonical per-task rewards.
They should agree (both delegate scoring to the same `evaluate_simulation`); investigate
any task that diverges. (A scripted diff is a planned convenience — Phase 4.)

## 8. Zero-setup alternative (no MLX)

For a quick demo with nothing but an authenticated `claude` CLI, run the user-sim on the
subscription via `claude -p`:

```bash
export TAU2_USER_SIM_PROVIDER=claude_cli      # ignores MLX vars
python -m tau2.eval_insitu.run_insitu --domain legal --task-id intake_happy_path \
  --harness-plugin-dir harnesses/plugins/legal-harness \
  --tau2-eval-plugin-dir harnesses/plugins/tau2-eval --run-dir /tmp/insitu-demo
```

Prefer MLX for cost-controlled benchmarking; `claude_cli` has no tool-using user-sim.

## 9. Caveats

- **Domains:** legal and retail today (same shape generalizes). Tool-using user
  simulators (telecom) need a function-calling-capable user-sim model — prefer a LiteLLM
  provider over MLX for those.
- **Model name must match** what the MLX server loaded, or it 404s.
- **Cost/latency:** agent on subscription, user-sim local → near-zero marginal API cost;
  watch subscription usage caps on large sweeps.
