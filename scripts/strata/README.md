# Running tau2 agents through a Strata gateway

Uses tau2's own agents, domains and user simulator as a realistic load client for
[Strata](https://github.com/pdhoolia/strata). Only the **agent** role goes through
Strata; the user simulator and the LLM judges go direct to LiteLLM, so Strata's
ledger sees exactly the workload it would see in production.

```
tau2 agent ──litellm_proxy/<model>──▶ Strata /c/tau2-<sim_id>/litellm/v1 ──▶ LiteLLM ──▶ provider
tau2 user-sim / judges ─────────────▶ LiteLLM (LITELLM_PROXY_API_BASE)
```

## How it plugs in

- `src/tau2/utils/llm_utils.py` `_route_via_strata()` — when `TAU2_STRATA_BASE` is
  set, calls whose `call_name` is in `TAU2_STRATA_CALLS` (default `agent_response`)
  get `api_base = {TAU2_STRATA_BASE}/c/tau2-<simulation_id>/litellm/v1`, the keyless
  sentinel `api_key`, and `extra_body.metadata = {user_id: <simulation_id>, task: <call_name>}`
  (Strata's sticky-routing key and router-rule label).
- `src/tau2/runner/batch.py` always sets `_current_simulation_id` (upstream only did
  so under `--verbose-logs`).
- One Strata conversation per tau2 simulation: `tau2-<simulation.id>` — the join key
  between `results.json` and `GET {STRATA}/api/conversations/<id>`.

## Run

Prereqs: `.env` with `LITELLM_PROXY_API_BASE` / `LITELLM_PROXY_API_KEY`
(see `.env.example`), and a Strata gateway whose `LITELLM_BASE_URL` is the same proxy.

```bash
scripts/strata/run.sh                 # airline, task 0, 1 trial, concurrency 1
TASK_IDS="0 1 2" NUM_TRIALS=3 MAX_CONCURRENCY=8 scripts/strata/run.sh   # load
AGENT_LLM=litellm_proxy/strata/tau2-agent scripts/strata/run.sh          # via a Strata router
scripts/strata/run.sh -- --verbose-logs                                  # extra tau2 flags
```

When `AGENT_LLM` targets a Strata router (`litellm_proxy/strata/<name>`), the
preflight runs `ensure_router.py` instead of the plain catalog check: if the router
is absent it is created from `router.json` (override with `ROUTER_JSON=…`) and made
live — the default `tau2-agent` definition is a 50/50 sonnet/haiku A/B, sticky per
simulation, with `maskToolResults(olderThanTurns: 4)`; if it exists it must already
be live (a draft/paused router is left alone — fix it in the console), and either
way every variant model must be visible on the LiteLLM catalog behind Strata. A
freshly created router is probed with a 1-token call (conversation `tau2-preflight`)
until the gateway's route-refresh tick picks it up (~15 s).

In the ledger, a routed call shows `original_model: strata/<name>`, the served
variant as `model`, `router_rule: default`, and `router_counterfactual_*` anchored
on the heavier variant. Masking stats appear only once resent tool results are older
than the plan's `olderThanTurns`.

Knobs (env): `DOMAIN`, `TASK_IDS`, `NUM_TRIALS`, `MAX_CONCURRENCY`, `AGENT_LLM`,
`USER_LLM`, `SAVE_TO`, `TAU2_STRATA_BASE`, `TAU2_STRATA_CALLS`, and the judge models
`TAU2_LLM_NL_ASSERTIONS` / `TAU2_LLM_ENV_INTERFACE` / `TAU2_LLM_EVAL_USER_SIMULATOR`
(all default to `litellm_proxy/aws/claude-sonnet-4-5`).

## Verify

```bash
SIM=$(python3 -c "import json;print(json.load(open('data/simulations/<SAVE_TO>/results.json'))['simulations'][0]['id'])")
curl -s http://127.0.0.1:8080/api/conversations/tau2-$SIM | python3 -m json.tool | less
```

Expect one call per agent turn with `input_tokens`, `cost_usd` (LiteLLM price sheet)
and `context_stats` (`uncached_repeat_usd`, `stale_tool_tokens`) — the latter is what
Strata's overview reports as *compressible / remaining opportunity*. tau2's own
`Avg Cost/Conversation` shows `$0.0000` for `litellm_proxy/` names (litellm cannot
price opaque proxy ids); Strata's ledger is the cost source of truth.

## Notes

- `tau2 --max-concurrency` > 10 is throttled by tau2's shared httpx pool
  (`llm_utils.py`, `max_connections=10`).
- A hallucination retry starts a *new* simulation id → a new Strata conversation;
  join on the final id in `results.json`.
