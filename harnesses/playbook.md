# Playbook — evaluating a domain harness on τ²-bench (via a LiteLLM gateway)

How to run a τ²-bench evaluation of a **domain-specific higher-order harness**
(`--agent claude_harness`, e.g. the [retail-harness](plugins/retail-harness) plugin)
and its **baseline** (`--agent llm_agent`), with every model routed through a corporate
LiteLLM gateway.

The two agents are a head-to-head: `claude_harness` runs Claude Code as the retail
harness (skills + scripts + PreToolUse hooks over the retail MCP server) and replays
its tool calls into the tau2 trajectory; `llm_agent` is the plain single-prompt agent.
Hold the **base model constant** on both sides so the *harness*, not a bigger model, is
the variable under test.

> Gateway plumbing (which env var each consumer reads, and why) is documented once in
> [AGENTS.md → "LiteLLM gateway"](../AGENTS.md) and [`.env.example`](../.env.example).
> This playbook is the operational runbook on top of that.

---

## 1. Prerequisites

```bash
uv sync --extra mcp --extra dev      # mcp: retail MCP server (claude_harness); dev: lint
uv run tau2 check-data               # verify the install
claude --version                     # the claude CLI must be on PATH (claude_harness only)
```

`.env` must point at the gateway. Minimum (see `.env.example` for the full annotated
block):

```bash
LITELLM_API_KEY=sk-<your_virtual_key>
LITELLM_API_BASE=https://your-litellm-gateway        # no trailing /v1

# SDK path (agent / user-sim / evaluator)
LITELLM_PROXY_API_BASE=${LITELLM_API_BASE}
LITELLM_PROXY_API_KEY=${LITELLM_API_KEY}

# claude CLI path (claude_harness)
ANTHROPIC_BASE_URL=${LITELLM_API_BASE}
ANTHROPIC_AUTH_TOKEN=${LITELLM_API_KEY}
ANTHROPIC_MODEL=aws/claude-sonnet-4-5
ANTHROPIC_SMALL_FAST_MODEL=aws/claude-haiku-4-5
ANTHROPIC_DEFAULT_HAIKU_MODEL=aws/claude-haiku-4-5
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

# Evaluator / judge models (hardcoded in config.py — no CLI flag)
TAU2_LLM_NL_ASSERTIONS=litellm_proxy/aws/claude-opus-4-8
TAU2_LLM_ENV_INTERFACE=litellm_proxy/aws/claude-opus-4-8
TAU2_LLM_EVAL_USER_SIMULATOR=litellm_proxy/aws/claude-opus-4-8
```

Use your gateway's **public model names** (the "Public Model Name" column in the
LiteLLM UI), e.g. `aws/claude-sonnet-4-5`. The SDK path needs the `litellm_proxy/`
prefix; the claude CLI path uses the bare name.

---

## 2. Preflight smoke tests (connectivity)

Fail fast before launching a run. Both load `.env` via tau2's dotenv, so no shell
sourcing needed.

```bash
# (a) SDK -> proxy /v1/chat/completions  (agent / user-sim / judge path)
uv run python -c "from tau2 import config; import litellm; print(litellm.completion(model='litellm_proxy/aws/claude-sonnet-4-5', messages=[{'role':'user','content':'say ok'}], max_tokens=8).choices[0].message.content)"
```

```bash
# (b) Anthropic /v1/messages  (claude_harness path — REQUIRED for the harness agent)
uv run python - <<'PY'
from tau2 import config
import os, json, urllib.request
base, tok = os.environ["ANTHROPIC_BASE_URL"], os.environ["ANTHROPIC_AUTH_TOKEN"]
req = urllib.request.Request(base.rstrip("/") + "/v1/messages",
  data=json.dumps({"model":"aws/claude-sonnet-4-5","max_tokens":16,"messages":[{"role":"user","content":"ping"}]}).encode(),
  headers={"content-type":"application/json","anthropic-version":"2023-06-01","x-api-key":tok,"authorization":"Bearer "+tok})
print(urllib.request.urlopen(req, timeout=30).read().decode()[:200])
PY
```

`(a)` returns `ok`; `(b)` returns a small JSON message ending in `"pong"` (or similar).
If `(b)` 404s/405s, your gateway does **not** expose the Anthropic Messages API and
`claude_harness` cannot run through it — only the `llm_agent` baseline will work.

---

## 3. Smoke run — 1 task per agent (the wiring check)

### Baseline (`llm_agent`)

```bash
uv run tau2 run --domain retail \
  --agent llm_agent --agent-llm litellm_proxy/aws/claude-sonnet-4-5 \
  --user-llm litellm_proxy/aws/claude-sonnet-4-5 \
  --num-tasks 1 --num-trials 1 --max-concurrency 1 \
  --save-to retail_smoke_baseline
```

### Harness (`claude_harness`)

```bash
uv run tau2 run --domain retail \
  --agent claude_harness --agent-llm aws/claude-sonnet-4-5 \
  --user-llm litellm_proxy/aws/claude-sonnet-4-5 \
  --num-tasks 1 --num-trials 1 --max-concurrency 1 \
  --save-to retail_smoke_harness
```

Note the model-name difference: baseline gets `litellm_proxy/aws/claude-sonnet-4-5`
(SDK), the harness gets the bare `aws/claude-sonnet-4-5` (forwarded to `claude --model`).
The user simulator is on the SDK path in both, so it always keeps the `litellm_proxy/`
prefix.

A healthy smoke run prints the metrics panel with `Average Reward 1.0000`, action match
`100%`, `DB Match ✓`, and an `LLM Judge Review` block (the Opus judge ran).

---

## 4. Full run — the whole task split

Drop `--num-tasks` to run every task in the split; raise concurrency; optionally raise
`--num-trials` for pass^k stability.

```bash
# Baseline, full retail split, 2 trials, parallel
uv run tau2 run --domain retail \
  --agent llm_agent --agent-llm litellm_proxy/aws/claude-sonnet-4-5 \
  --user-llm litellm_proxy/aws/claude-sonnet-4-5 \
  --num-trials 2 --max-concurrency 4 \
  --save-to retail_full_baseline

# Harness, full retail split — keep concurrency low (each task spawns an MCP server
# + a claude subprocess) and give the replay room with a larger step budget.
uv run tau2 run --domain retail \
  --agent claude_harness --agent-llm aws/claude-sonnet-4-5 \
  --user-llm litellm_proxy/aws/claude-sonnet-4-5 \
  --num-trials 1 --max-concurrency 2 --max-steps 400 \
  --save-to retail_full_harness
```

Variations:

| Lever | Flag | Notes |
| --- | --- | --- |
| Task count | `--num-tasks N` | omit for the full split; smoke uses `1` |
| Specific tasks | `--task-ids id1 id2` | target a subset by id |
| Repeat for pass^k | `--num-trials K` | K runs per task; reward becomes pass^K |
| Parallelism | `--max-concurrency N` | baseline scales freely; **keep harness low** |
| Replay budget | `--max-steps M` | raise for the harness (replaying N calls ≈ N steps) |
| Resume | reuse `--save-to` | an existing results dir resumes instead of restarting |

**Vary the agent model, hold the cast constant.** To benchmark a different agent
model, change only `--agent-llm` (both runs); keep `--user-llm` and the `TAU2_LLM_*`
judge models fixed across all experiments so scores stay comparable.

Review everything with:

```bash
uv run tau2 view
```

---

## 5. The scripted shortcut — `run_eval.sh`

[`harnesses/run_eval.sh`](run_eval.sh) does §2–§4 in one call: preflight, then the
baseline and/or harness run, with smoke/full sizing.

```bash
harnesses/run_eval.sh <domain> <smoke|full> [baseline|harness|both]
```

Examples:

```bash
# Retail, 1 task each, both agents — the head-to-head wiring check
harnesses/run_eval.sh retail smoke both

# Retail, full split, baseline only
harnesses/run_eval.sh retail full baseline

# Retail, full split, harness only
harnesses/run_eval.sh retail full harness

# Another domain (baseline only — claude_harness is retail-only today; the script
# detects this and runs just the baseline)
harnesses/run_eval.sh airline smoke
```

Override models / sizing via env vars (bare gateway public names):

```bash
TAU2_AGENT_MODEL=aws/claude-opus-4-8 \
TAU2_USER_MODEL=aws/claude-sonnet-4-5 \
TAU2_NUM_TRIALS=2 TAU2_HARNESS_CONCURRENCY=2 \
  harnesses/run_eval.sh retail full both
```

Results land in `data/simulations/<domain>_<mode>_<agent>/`; review with `tau2 view`.

---

## 6. Notes & caveats

- **Cost is unavailable through the gateway.** LiteLLM can't price proxy model names,
  so per-conversation cost shows `$0.00` (baseline) / `$nan` (harness), and each LLM
  call logs a benign `get_response_cost ... This model isn't mapped yet` **ERROR**.
  It's harmless (cost falls back to 0); use your gateway's own usage dashboard for
  spend. On full runs this line is noisy — filter it with `2>&1 | grep -v "isn't mapped yet"`.
- **`claude_harness` is retail-only today** — it hardcodes the retail MCP server +
  plugin. Airline/telecom generalize the same way (swap server module + plugin dir);
  until then the script runs baseline-only for non-retail domains.
- **Background model.** The claude CLI makes small/fast background calls; point
  `ANTHROPIC_SMALL_FAST_MODEL` at a gateway model (e.g. Haiku) or those calls fail.
- **Step budget.** Replaying N tool calls costs ~N orchestrator steps; long harness
  tasks may need a higher `--max-steps`.
- **Recommended fixed cast:** user-sim = Sonnet, judge = Opus (in `.env`), claude
  background = Haiku. Vary only the agent model between experiments.
