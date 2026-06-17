# Playbook — evaluating the `legal` domain and viewing it in the web visualizer

End-to-end runbook for the NSW boutique-firm **`legal`** domain: run the full
benchmark, turn the results into a leaderboard *submission*, and browse the
trajectories in the **React web visualizer** at `http://localhost:5173`.

It covers **both** agents the domain can be run with:

- the **standard agent** (`llm_agent`) — one prompt + the legal tools, the baseline; and
- the **legal-harness** (`--agent claude_harness`) — the higher-order
  [legal-harness Claude plugin](../harnesses/plugins/legal-harness/README.md)
  (skills + scripts + PreToolUse hooks over the legal MCP server), driven through the
  [`claude_harness` bridge](../src/tau2/agent/claude_harness).

Both produce the **same `results.json` schema**, so the submission/visualizer steps are
identical — you just create one submission per agent and switch between them in the
model dropdown for a head-to-head.

This is the browser **TrajectoryVisualizer** path — distinct from the terminal
`tau2 view` TUI. For the terminal viewer and the policy/tasks API servers, see
[ui-viewers.md](ui-viewers.md). For gateway/`.env` plumbing, preflight smoke tests, and
the `run_eval.sh` shortcut, see the [LiteLLM-gateway playbook](../harnesses/docs/tau2-playbook.md).

---

## 1. Run the full benchmark

`legal` has 12 tasks. Omit `--num-tasks` to run the whole split. Sanity-check first
with `--num-tasks 1 --max-concurrency 1` before any full run.

Results land in `data/simulations/<save-to>/results.json` (a single `--save-to` dir;
without it, an auto-named timestamped dir is used). That `results.json` contains a
`simulations[]` array (one per task/trial, each with `reward_info`, messages, tool
calls) and a `tasks[]` array — exactly what the web visualizer consumes. A healthy run
prints the metrics panel: average reward, per-domain DB-match, and an `LLM Judge Review`
block (the Opus judge ran).

### 1a. Standard agent (`llm_agent`) — the baseline

Agent and user simulator both route through the LiteLLM proxy (note the
`litellm_proxy/` prefix); the judge models come from `.env` (`TAU2_LLM_*`).

```bash
uv run tau2 run --domain legal \
  --agent-llm litellm_proxy/aws/claude-sonnet-4-5 \
  --user-llm  litellm_proxy/aws/claude-sonnet-4-5 \
  --num-trials 1 --max-concurrency 4 \
  --save-to legal_full_baseline
```

Cost shows `$0.00` — expected through the gateway (LiteLLM can't price proxy names).

### 1b. Legal-harness (`--agent claude_harness`)

The harness runs the [legal-harness plugin](../harnesses/plugins/legal-harness/README.md)
as a headless Claude Code session that calls the real legal tools over MCP; the bridge
reconciles those calls into the scored trajectory. Differences from the baseline:

- **Model name is bare** (`aws/claude-sonnet-4-5`, no `litellm_proxy/` prefix): the
  bridge passes it to `claude --model`, which hits the gateway's Anthropic
  `/v1/messages` endpoint. The user simulator stays on the SDK path (keeps the prefix).
- **Extra prerequisites:** `uv sync --extra mcp`, the `claude` CLI on `PATH`, and the
  gateway must expose `/v1/messages`. The bridge spawns the legal MCP server and seeds
  its DB per task — no server to start by hand.
- **Keep concurrency low** (each task spawns an MCP server + a `claude` subprocess) and
  give the replay room with a larger step budget. Cost shows `$nan` (still unpriced).

```bash
uv run tau2 run --domain legal \
  --agent claude_harness --agent-llm aws/claude-sonnet-4-5 \
  --user-llm litellm_proxy/aws/claude-sonnet-4-5 \
  --num-trials 1 --max-concurrency 2 --max-steps 400 \
  --save-to legal_full_harness
```

Or use the scripted shortcut (preflight + run), which sizes concurrency for you:

```bash
harnesses/run_eval.sh legal smoke harness   # 1-task wiring check first
harnesses/run_eval.sh legal full harness    # the full 12-task split
```

---

## 2. Convert the results into a submission

The web visualizer reads **submissions**, not raw `data/simulations/` output. A
submission is a directory under `web/leaderboard/public/submissions/<dir>/` with:

```
<dir>/
├── submission.json                 # metadata + domain→trajectory-file map
└── trajectories/
    └── legal_results.json          # a copy of your run's results.json
```

> **Official tool vs. manual.** `tau2 submit prepare <results> -o <dir>` generates
> `submission.json` and copies trajectories for you. It is interactive and runs
> **public trajectory verification**, which is built around the upstream domains —
> it is **not** validated for this fork's `legal` domain, and it does **not** wire
> up the web app (steps 2c/2d below). The steps here are the verified manual path
> we used; reach for `submit prepare` only if you also intend a real leaderboard PR.

> **The harness needs no extra web support.** A `claude_harness` run produces a
> `results.json` with the **identical schema** to the baseline (same `simulations[]` /
> `tasks[]`, `reward_info`, messages with `tool_calls`; `agent_cost` is `null`, not the
> invalid-JSON `NaN`). So the visualizer renders it as-is — to compare the two agents
> you just create **one submission per agent** (distinct dir + `model_name`) and switch
> between them in the model dropdown. Steps 2c/2d below are one-time and shared.

### 2a. Create the submission dir and copy the trajectory

One dir per agent — give the harness a distinct, recognizable name:

```bash
cd web/leaderboard
# baseline
BASE_DIR=public/submissions/legal-claude-sonnet-4-5_local_$(date +%Y-%m-%d)
mkdir -p "$BASE_DIR/trajectories"
cp ../../data/simulations/legal_full_baseline/results.json "$BASE_DIR/trajectories/legal_results.json"
# harness
HARN_DIR=public/submissions/legal-harness-claude-sonnet-4-5_local_$(date +%Y-%m-%d)
mkdir -p "$HARN_DIR/trajectories"
cp ../../data/simulations/legal_full_harness/results.json "$HARN_DIR/trajectories/legal_results.json"
```

> Trajectory JSON is gitignored (`public/submissions/*/trajectories/*.json` — they
> are normally hosted on S3), so the copied results files stay local and untracked.

### 2b. Write `submission.json`

`trajectories_available` and the `trajectory_files` map (domain → filename inside
`trajectories/`) are the two fields the visualizer requires. Baseline:

```json
{
  "model_name": "claude-sonnet-4-5 (legal, local)",
  "model_organization": "local",
  "submission_date": "2026-06-16",
  "submission_type": "standard",
  "trajectories_available": true,
  "trajectory_files": { "legal": "legal_results.json" },
  "methodology": {
    "user_simulator": "litellm_proxy/aws/claude-sonnet-4-5",
    "notes": "Local run of the legal domain (llm_agent). Judge = aws/claude-opus-4-8."
  }
}
```

Harness — same shape, but a distinct `model_name` (so both show in the dropdown) and
`submission_type: "custom"` (the scaffold is non-standard):

```json
{
  "model_name": "claude-sonnet-4-5 (legal-harness, local)",
  "model_organization": "local",
  "submission_date": "2026-06-16",
  "submission_type": "custom",
  "trajectories_available": true,
  "trajectory_files": { "legal": "legal_results.json" },
  "methodology": {
    "user_simulator": "litellm_proxy/aws/claude-sonnet-4-5",
    "notes": "legal-harness Claude plugin via --agent claude_harness (Architecture B). Judge = aws/claude-opus-4-8."
  }
}
```

### 2c. Register the dir in the manifest

Add **both** directory names to the `submissions` array in
[`public/submissions/manifest.json`](../web/leaderboard/public/submissions/manifest.json):

```json
{
  "submissions": [
    "legal-claude-sonnet-4-5_local_2026-06-16",
    "legal-harness-claude-sonnet-4-5_local_2026-06-16",
    "...existing entries..."
  ]
}
```

### 2d. Add `legal` to the visualizer's domain list

The domain pills render from a **hardcoded** array in
[`src/components/TrajectoryVisualizer.jsx`](../web/leaderboard/src/components/TrajectoryVisualizer.jsx)
(`const domains = [...]`); a domain absent from it has no pill. Add:

```jsx
{ id: 'legal', label: 'Legal', icon: '⚖️', color: '#b45309' }
```

> **Task-data** for the "Tasks" tab (`public/task-data/domains/legal/tasks.json` and
> `policy.md`) already ships with the legal domain — nothing to do there.

---

## 3. View it in the web visualizer

```bash
cd web/leaderboard
npm install        # first time only
npm run dev        # serves http://localhost:5173
```

Open the app → **Trajectory Visualizer** → Model dropdown → pick "claude-sonnet-4-5
(legal, local)" or "claude-sonnet-4-5 (legal-harness, local)" → Domain pill = ⚖️
**Legal** → pick a task. You get the message-by-message agent ↔ user trajectory, tool
calls/results, and the reward + evaluation-criteria breakdown (handy for failing tasks).

**Head-to-head:** keep the same task selected and flip the Model dropdown between the
two submissions to compare how the baseline and the harness handled the *same* scenario
— e.g. where the harness's PreToolUse guardrail denied a fee/uplift violation the
baseline let through.

Deep link straight to a run (URL state is in the hash) — swap `model=` for either dir:

```
http://localhost:5173/#trajectory-visualizer?model=legal-claude-sonnet-4-5_local_2026-06-16&domain=legal
http://localhost:5173/#trajectory-visualizer?model=legal-harness-claude-sonnet-4-5_local_2026-06-16&domain=legal
```

Quick check that everything serves before opening the browser:

```bash
BASE=http://localhost:5173
curl -s $BASE/submissions/manifest.json | python3 -m json.tool | head
curl -s $BASE/submissions/<DIR>/submission.json | python3 -m json.tool
curl -s -o /dev/null -w "%{http_code}\n" $BASE/submissions/<DIR>/trajectories/legal_results.json
```

Stop the dev server with `Ctrl-C` (or `pkill -f vite` if backgrounded).

---

## Quick reference

```bash
# 1. run — baseline (standard agent)
uv run tau2 run --domain legal \
  --agent-llm litellm_proxy/aws/claude-sonnet-4-5 \
  --user-llm  litellm_proxy/aws/claude-sonnet-4-5 \
  --num-trials 1 --max-concurrency 4 --save-to legal_full_baseline

# 1. run — legal-harness (bare agent model; user-sim keeps the prefix)
harnesses/run_eval.sh legal full harness        # -> data/simulations/legal_full_harness

# 2. convert (manual, once per agent): mkdir submission dir, cp results.json into
#    trajectories/, write submission.json (distinct model_name per agent), add both
#    dirs to manifest.json. One-time: add 'legal' to domains[] in TrajectoryVisualizer.jsx.

# 3. view
cd web/leaderboard && npm run dev    # http://localhost:5173 → Trajectory Visualizer → Legal
#                                      switch the Model dropdown for the baseline-vs-harness head-to-head
```
