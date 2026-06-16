# Playbook — evaluating the `legal` domain and viewing it in the web visualizer

End-to-end runbook for the NSW boutique-firm **`legal`** domain: run the full
benchmark, turn the results into a leaderboard *submission*, and browse the
trajectories in the **React web visualizer** at `http://localhost:5173`.

This is the browser **TrajectoryVisualizer** path — distinct from the terminal
`tau2 view` TUI. For the terminal viewer and the policy/tasks API servers, see
[ui-viewers.md](ui-viewers.md). For gateway/`.env` plumbing and the
harness-vs-baseline head-to-head, see the [LiteLLM-gateway playbook](../harnesses/playbook.md).

---

## 1. Run the full benchmark

`legal` has 12 tasks. Both the agent and the user simulator route through the
LiteLLM proxy (note the `litellm_proxy/` prefix); the judge models come from `.env`
(`TAU2_LLM_*`). Omit `--num-tasks` to run the whole split.

```bash
uv run tau2 run --domain legal \
  --agent-llm litellm_proxy/aws/claude-sonnet-4-5 \
  --user-llm  litellm_proxy/aws/claude-sonnet-4-5 \
  --num-trials 1 --max-concurrency 4 \
  --save-to legal_full_sonnet
```

- Sanity-check first with `--num-tasks 1 --max-concurrency 1` before the full run.
- Results land in `data/simulations/<save-to>/results.json` (a single `--save-to`
  dir; without it, an auto-named timestamped dir is used).
- A healthy run prints the metrics panel: average reward, per-domain DB-match,
  and an `LLM Judge Review` block (the Opus judge ran). Cost shows `$0.00` —
  expected through the gateway (LiteLLM can't price proxy model names).

The `results.json` contains both a `simulations[]` array (one per task/trial, each
with `reward_info`, messages, tool calls) and a `tasks[]` array — exactly what the
web visualizer consumes.

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

### 2a. Create the submission dir and copy the trajectory

```bash
cd web/leaderboard
DIR=public/submissions/legal-claude-sonnet-4-5_local_$(date +%Y-%m-%d)
mkdir -p "$DIR/trajectories"
cp ../../data/simulations/legal_full_sonnet/results.json "$DIR/trajectories/legal_results.json"
```

> Trajectory JSON is gitignored (`public/submissions/*/trajectories/*.json` — they
> are normally hosted on S3), so the copied results file stays local and untracked.

### 2b. Write `submission.json`

`trajectories_available` and the `trajectory_files` map (domain → filename inside
`trajectories/`) are the two fields the visualizer requires.

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
    "notes": "Local run of the legal domain. Judge = aws/claude-opus-4-8."
  }
}
```

### 2c. Register the dir in the manifest

Add the directory name to the `submissions` array in
[`public/submissions/manifest.json`](../web/leaderboard/public/submissions/manifest.json):

```json
{
  "submissions": [
    "legal-claude-sonnet-4-5_local_2026-06-16",
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

Open the app → **Trajectory Visualizer** → Model = "claude-sonnet-4-5 (legal,
local)" → Domain pill = ⚖️ **Legal** → pick a task. You get the message-by-message
agent ↔ user trajectory, tool calls/results, and the reward + evaluation-criteria
breakdown (handy for failing tasks).

Deep link straight to the run (URL state is in the hash):

```
http://localhost:5173/#trajectory-visualizer?model=legal-claude-sonnet-4-5_local_2026-06-16&domain=legal
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
# 1. run
uv run tau2 run --domain legal \
  --agent-llm litellm_proxy/aws/claude-sonnet-4-5 \
  --user-llm  litellm_proxy/aws/claude-sonnet-4-5 \
  --num-trials 1 --max-concurrency 4 --save-to legal_full_sonnet

# 2. convert (manual): mkdir submission dir, cp results.json into trajectories/,
#    write submission.json, add dir to manifest.json, add 'legal' to domains[] in
#    TrajectoryVisualizer.jsx

# 3. view
cd web/leaderboard && npm run dev    # http://localhost:5173  → Trajectory Visualizer → Legal
```
