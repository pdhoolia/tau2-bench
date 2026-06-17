# Higher-order harness: tau2-bench as a Claude Code plugin

> Status: **design / exploration**. Branch `pdhoolia/tau2-bench-claude-plugin`.
> Companion de-risk spike: [`spikes/stop-hook-loop/`](../spikes/stop-hook-loop/).

## 1. Motivation — inverting the equation

Today **tau2 is the driver** and Claude Code is a guest. The `claude_harness` agent
([`src/tau2/agent/claude_harness/`](../src/tau2/agent/claude_harness/)) drives, per *user turn*:

1. `cli_runner.py` spawns **`claude -p ... --resume <session>`** as a fresh subprocess;
2. it lazily spawns a **per-task MCP server**
   (`python -m tau2.mcp.<domain>_server --transport http --port N --db-path <seeded.json>`)
   and health-checks it;
3. it parses `stream-json`, extracts the `mcp__<server>__*` tool calls, and **re-emits them
   one at a time** into tau2's orchestrator, which *replays* them against its own scored env
   ("double execution by design").

The user-simulator, evaluator, and DB live in tau2 (Python, via the LiteLLM gateway).

The **inversion** ("higher-order harness"): make **Claude Code the driver** and tau2 the guest.
Ship a `tau2-eval` plugin so that, inside a live Claude Code session, the session *is the agent
under test* (a domain harness plugin loaded → its skills + PreToolUse hooks + MCP all active),
and the plugin wraps the tau2 loop around it — user-simulator, task loop, DB reset, scoring —
all **in-situ**.

Three cost/latency sources of today's design motivate the change:

- **`claude -p` cold start every turn** (process spawn + session-resume load).
- **A new MCP server process per task** (spawn + health-check loop).
- **`claude -p` billing** — see §3.

## 2. The constraint that dictates the architecture

Three verified Claude Code semantics (CLI 2.1.x) force a specific shape:

1. **Plugin hooks do not propagate to sub-agents.** Sub-agents run isolated; plugin-provided
   sub-agents cannot even declare `hooks` / `mcpServers` / `permissionMode` (ignored for
   security). → **If the agent-under-test were a sub-agent, the harness's PreToolUse guardrail
   hooks — the core of its determinism — would not fire.** That defeats the purpose.
2. **Billing (post 2026-06-15):** interactive sessions (main loop *and* their sub-agents) draw
   the **Max subscription**; `claude -p` headless draws a **separate, capped Agent-SDK credit
   pool** at API rates. The cost win is real *only if the agent-under-test runs as an interactive
   main session*, not via `claude -p`.
3. **Evaluation orchestration must be invisible to the agent under test** — it must believe it is
   talking to a real user, not running a benchmark. So orchestration cannot live in the main
   agent's own prompt.

Together these yield a single coherent design:
**main session = agent under test; the eval loop drives it from the outside via hooks** — not
via sub-agents, and not via main-prompt instructions.

## 3. Honest assessment of the benefits

| Benefit | Verdict |
|---|---|
| **Product / marketplace** | **Strongest.** A domain-agnostic in-situ evaluator is novel and reusable, and it unlocks the synthetic-task **train/validate** workflow (Agent Tune). Strategic payoff. |
| **Latency** | **Real and large.** Persistent session + persistent MCP replaces per-turn `claude -p` cold starts and per-task server spawns. The inversion *subsumes* the per-task-MCP problem: one server per eval session, reseed DB per task via a `reset` tool. |
| **Cost** | **Real, with nuance.** In-session ⇒ subscription; `claude -p` ⇒ capped Agent-SDK pool. But the user-sim still needs an LLM (multi-turn simulation cannot be made deterministic), and driving a *large en-masse* benchmark unattended through an interactive subscription may bump usage caps. |

**Positioning.** The in-situ plugin is the right tool for **iterative harness development, demos,
and small held-out validate runs** — the "manual, 1–2 task" mode. **Large comparative runs likely
stay on the (optimized) Python CLI path.** Pitch the plugin as the in-situ dev/eval loop that also
fixes small-run latency — not as a replacement for mass benchmarking.

## 4. Architecture — component → Claude Code primitive

| tau2 component | In-situ realization |
|---|---|
| Orchestrator loop | A **`/tau2-eval <domain> <task-id>`** command starts a run; a **Stop hook** drives turn alternation by injecting the next user message and blocking premature stop (`{"decision":"block","reason":<user msg>}`). |
| Agent under test | **The main session**, with the domain harness plugin loaded (skills + PreToolUse hooks + MCP live). Full fidelity. |
| User simulator | A **single LLM call from the Stop hook**, reusing tau2's exact prompt construction (`simulation_guidelines.md` + persona + scenario) for parity (`eval_insitu.usersim.UserSimDriver`, file-backed across the per-turn hook process). Model is provider-agnostic via the **model gateway** (`eval_insitu.model_gateway`): local MLX (Apple Silicon, Qwen 8-bit, OpenAI-compatible `/v1`), the LiteLLM proxy, or a cloud provider — all through tau2's LiteLLM `generate()`. |
| Environment / DB | **One eval-control server per parallel lane** (never shared across concurrent tasks — each is an OS-isolated world on its own port), reseeded between the tasks that lane runs via an admin `/admin/reset` route (`build_task_db`). Removes the per-*task* spawn cost while keeping parallel runs isolated. |
| Evaluator | A terminal script that **calls tau2's existing `evaluate_simulation`** (deterministic DB-hash / action / communicate checks). NL-assertions via a **judge sub-agent**. |
| Transcript / state | Written to a run file by the hooks (hooks are stateless across calls → file-backed state required). |

The agent-under-test writes directly to the live MCP DB, and the evaluator scores *that* DB against
a freshly-replayed golden — dropping "double execution", while golden construction still reuses
`Environment.set_state`.

## 5. Risks to retire early

1. **Stop-hook → next-user-message injection.** Whether `{"decision":"block","reason":...}`
   reliably feeds `reason` back as the next turn is **version-dependent**. **#1 unknown — spiked
   first** (see [`spikes/stop-hook-loop/`](../spikes/stop-hook-loop/)). Fallbacks:
   `hookSpecificOutput.additionalContext` / `systemMessage`, or file-based injection.
2. **Parity with the canonical evaluator.** Credibility depends on the in-situ run producing the
   **same scores** as `tau2 run`. Anchor: reuse tau2's Python user-sim prompt + `evaluate_simulation`,
   validate against the legal 12-task set (existing 12/12 vs 7/12 result is the fixture).
3. **User-sim is irreducibly an LLM** (accepted) — keep it cheap/local and *out of* the
   subscription-billed agent loop.
4. **Scale & subscription fit** — interactive automation at benchmark scale may hit caps; keep mass
   runs on the CLI.

## 6. Phased plan

- **Phase 0 — De-risk spike.** Prove the Stop-hook continuation loop in a throwaway plugin: can a
  hook force N alternating turns by injecting text? Resolve risk #1 before anything else.
  → [`spikes/stop-hook-loop/`](../spikes/stop-hook-loop/).
- **Phase 1 — Per-lane eval-control server + reset.** ✅ Added `build_task_db` (in-memory,
  parity-checked against the file seeder) and `tau2.mcp.eval_control_server`: one isolated world
  per instance, MCP tools at `/mcp/<domain>` plus admin `/admin/{reset,db_hash,info}`. **Concurrency:
  one server per parallel lane, never a shared central DB** — proven isolated by
  `tests/test_eval_control_server.py`. Independently useful; also speeds the current CLI path.
- **Phase 2 — `tau2-eval` plugin, single task.** ✅ Built and unit-tested end to end:
  `eval_insitu.{usersim,transcript,score,hook_logic,model_gateway,run_insitu}` +
  `harnesses/plugins/tau2-eval` (Stop-hook user-sim). Scoring delegates to
  `evaluate_simulation` (parity by reuse) — golden legal trajectories score 1.0, broken ones
  <1.0. **Live smoke** ([`spikes/mcp-control-smoke/`](../spikes/mcp-control-smoke/)) confirms
  `claude` invokes our eval-control MCP tools under root via the settings allowlist. Remaining
  for a live multi-turn run: a reachable user-sim model endpoint.
- **Phase 3 — Parity gate.** Run the legal 12 tasks in-situ vs `tau2 run`; require matching rewards.
  Credibility checkpoint. Needs the user-sim endpoint (local MLX / proxy / cloud).
- **Phase 4 — Generalize + product.** Domain-agnostic task loader, multi-task/multi-trial runner,
  results report; package for the marketplace alongside the existing `tau2-harnesses` entry.
- **Phase 5 (strategic) — Synthetic train/validate.** Wire Agent Tune task generation + a frozen
  validate split, enabling in-situ iterative harness improvement.

## 7. Model gateway (local MLX user-sim)

The user-sim and judge are cost/latency-sensitive and a strong fit for **local
inference** — a Qwen model (e.g. 8-bit) served on a 64 GB Apple-Silicon machine via an
OpenAI-compatible endpoint (`mlx_lm.server` / LM Studio). Because both seams route
through tau2's LiteLLM `generate()` (which forwards `api_base`/`api_key`), this is pure
configuration. `eval_insitu.model_gateway.resolve_model(role)` reads, per role
(`USER_SIM`, `JUDGE`):

```
TAU2_USER_SIM_PROVIDER = mlx | openai | anthropic | litellm   # default: mlx
TAU2_USER_SIM_MODEL    = qwen2.5-32b-instruct-8bit
TAU2_USER_SIM_API_BASE = http://localhost:8080/v1             # mlx/openai
TAU2_USER_SIM_API_KEY  = mlx                                  # dummy ok locally
```

`provider=mlx` targets the local server via LiteLLM's `openai/` route; an explicit
prefix in `MODEL` (`anthropic/…`, `litellm_proxy/…`) is honored verbatim. Build the
driver with `UserSimDriver.from_env(task, role="USER_SIM")`. The agent-under-test stays
on the Claude subscription (configured via the `claude` CLI / `ANTHROPIC_*`), so a
typical local-first setup is: **agent = subscription Claude, user-sim + judge = local
MLX Qwen** — minimizing both API cost and latency.

## 8. Open decisions

1. User-sim model for the prototype (local MLX / gateway / dedicated `claude -p`).
2. Whether large comparative runs stay exclusively on the CLI path (recommended) or are also
   supported in-situ.
</content>
</invoke>
