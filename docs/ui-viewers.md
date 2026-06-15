# Playbook — viewing domains, tasks, and results in the browser

τ²-bench ships three browser/terminal views. They are **separate servers on different
ports** and answer different questions:

| You want to see… | Use | Where | Needs a run first? |
|---|---|---|---|
| A domain's **policy + tools** | `tau2 domain <domain>` | `http://127.0.0.1:8004/redoc` | No |
| A domain's **tasks** (scenarios + evaluation criteria) | `tau2 start` → simulation API | `http://127.0.0.1:8001/docs` | No |
| **Completed simulation trajectories** (agent ↔ user runs) | `tau2 view` | terminal TUI | Yes |

The running example below is the `legal` domain; substitute any registered domain
(`tau2` with no args, or `POST /api/v1/get_options`, lists them).

---

## 1. Domain viewer — policy + tools (`:8004`)

Renders the domain's `policy.md` and every tool as a documented HTTP endpoint.

```bash
tau2 domain legal
```

- Auto-opens your browser to **http://127.0.0.1:8004/redoc** (ReDoc).
- Interactive Swagger equivalent: **http://127.0.0.1:8004/docs** — you can call a tool
  live (e.g. `POST /tools/run_conflict_check`) against an in-memory copy of the domain DB.
- Raw schema: `http://127.0.0.1:8004/api/openapi.json` (note the `/api/` prefix —
  it is **not** at `/openapi.json`).

What you'll see for `legal`: the title *"Environment: legal"*, the full NSW intake
policy as the description, and the 13 tool endpoints under `/tools/` (`run_conflict_check`,
`create_client`, `verify_client_identity`, `create_costs_agreement`, `open_matter`, …).

> The server runs in the foreground and **blocks the terminal** until you `Ctrl-C`. It
> binds `127.0.0.1:8004`; if that port is busy you'll get `address already in use` —
> stop the other process first (see [Shutting down](#shutting-down)).

---

## 2. Tasks / simulation API (`:8001`)

Exposes the task sets and the run/evaluate endpoints as a FastAPI service.

```bash
tau2 start
```

This starts the simulation service on **http://127.0.0.1:8001** (see
`scripts/start_tau2_server.sh`). Open the Swagger UI at **http://127.0.0.1:8001/docs**.

> Port note: `tau2 start` hardcodes `:8001`. Running the module directly
> (`uvicorn src.tau2.api_service.simulation_service:app`) instead defaults to
> `API_PORT` (`8000`) from `src/tau2/config.py`.

### Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET`  | `/health` | — | health check |
| `POST` | `/api/v1/get_options` | — | registered domains, agents, users, task sets |
| `POST` | `/api/v1/get_tasks` | `{"domain": "legal"}` | all tasks for the domain |
| `POST` | `/api/v1/run_domain` | a `RunConfig` JSON | runs a simulation, returns `Results` |

### Browse the `legal` tasks

In Swagger: expand **`POST /api/v1/get_tasks`** → **Try it out** → body
`{"domain": "legal"}` → **Execute**. Or from the shell:

```bash
curl -s -X POST http://127.0.0.1:8001/api/v1/get_tasks \
  -H "Content-Type: application/json" \
  -d '{"domain": "legal"}' | python3 -m json.tool
```

Each task includes its `user_scenario` (persona, reason for call, known/unknown info)
and `evaluation_criteria` (reference `actions`, `communicate_info`, `reward_basis`).

> `POST /api/v1/run_domain` drives real LLM calls through LiteLLM and needs configured
> API keys — it is not free. For running evaluations, prefer the CLI (`tau2 run`) and
> the [LiteLLM-gateway eval playbook](../harnesses/playbook.md).

---

## 3. Results viewer — trajectories (`tau2 view`)

After a run (`tau2 run --domain legal …`), results land in `data/simulations/`. Browse
them in the terminal TUI:

```bash
tau2 view                         # picks from data/simulations/
tau2 view --file path/to/results.json
tau2 view --only-show-failed      # only failed tasks
```

This shows the actual agent ↔ user conversations, tool calls, and per-task rewards — the
thing the other two views do **not** show. See [evaluation.md](evaluation.md) for how
rewards are computed.

---

## Shutting down

Each server is its own process. `Ctrl-C` in its terminal stops it. If one was launched in
the background (or a port is stuck `address already in use`):

```bash
# find and kill whatever holds the port (8004 = domain viewer, 8001 = simulation API)
lsof -ti tcp:8004 | xargs kill
lsof -ti tcp:8001 | xargs kill
```

---

## Quick reference

```bash
tau2 domain legal     # :8004/redoc  — policy + tools
tau2 start            # :8001/docs   — tasks + run/evaluate API
tau2 run --domain legal --agent-llm <m> --user-llm <m> --num-tasks 3   # produce results
tau2 view             # browse the resulting trajectories
```
