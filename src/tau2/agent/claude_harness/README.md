# claude_harness — the Architecture-B evaluation bridge

`claude_harness` is a tau2 agent that runs **Claude Code as a domain harness** and
scores it on τ²-bench. It is the applied core of *From Agents to Harnesses*: Claude
executes the real domain tools over MCP — with the retail-harness plugin's skills,
scripts, and PreToolUse hooks active — and we reconcile what it did back into the
tau2 trajectory so the standard evaluator still grades it fairly.

## How it works (the replay)

Claude's tool calls happen side-band over MCP, which the tau2 evaluator never sees.
So instead of trusting a separate world, we **replay** Claude's domain tool calls
through tau2's own orchestrator loop:

```
user turn ─▶ run `claude -p` once ─▶ Claude makes domain calls c0..cN + final text
          ─▶ emit c0 as AssistantMessage(tool_call); tau2 executes it against ITS env
          ─▶ on the returned ToolMessage, emit c1; … ; then emit the final text
```

tau2 records each `(AssistantMessage(tool_call), ToolMessage)` pair in the
trajectory, so the **ACTION** evaluator (subset match) and **DB** evaluator (replay
on a fresh env from `initial_state`) get exactly what they need — **with zero core
changes**. Claude's non-domain tool use (Bash for the scripts, Read, skill loads) is
filtered out; only `mcp__<server>__*` calls are replayed, with the prefix stripped to
the bare toolkit method name.

Per simulation, the agent seeds an **isolated retail DB** for the task
(`task_db.py`), launches the retail MCP server against it on a free port
(`cli_runner.py`), drives `claude -p` with the retail-harness plugin, and resumes the
same Claude session across user turns.

## Module layout

| File            | Responsibility                                                            |
| --------------- | ------------------------------------------------------------------------- |
| `agent.py`      | `ClaudeHarnessAgent` (replay state machine) + factory + registry wiring.  |
| `cli_runner.py` | `ClaudeCLIRunner`: per-task MCP server lifecycle, `claude -p` invocation, stream-json parsing. |
| `task_db.py`    | Seed the task's initial retail DB to a JSON file for the MCP server.       |

## Prerequisites (for a live run)

- `uv sync --extra mcp` (the retail MCP server needs FastMCP).
- The `claude` CLI on PATH and a working `ANTHROPIC_API_KEY`.
- The retail-harness plugin present at `harnesses/plugins/retail-harness`
  (override with `TAU2_RETAIL_HARNESS_PLUGIN_DIR`).

## Run it

```bash
tau2 run --domain retail \
  --agent claude_harness --agent-llm sonnet \
  --user-llm gpt-4.1 \
  --num-trials 1 --num-tasks 5
```

`--agent-llm` is forwarded to the Claude CLI as `--model`, so pass a Claude model id
the CLI understands (e.g. `sonnet`, `opus`, or a full id). For a fair head-to-head
against the legacy `llm_agent`, hold the base model constant on both sides — the
harness, not a bigger model, is the variable under test.

### Config overrides (`--agent-llm-args`, JSON)

| key                    | default                | meaning                                  |
| ---------------------- | ---------------------- | ---------------------------------------- |
| `mcp_server_name`      | `tau2-retail`          | MCP server key; must match the plugin hook matcher. |
| `max_turns`            | `40`                   | `claude -p --max-turns` per user turn.   |
| `permission_mode`      | `bypassPermissions`    | Non-interactive permission mode (hooks still fire). |
| `append_system_prompt` | harness framing string | Replace the short harness system prompt. |
| `plugin_dir`           | repo retail-harness    | Path to the plugin to load.              |
| `claude_bin`           | `claude`               | CLI binary.                              |
| `extra_cli_args`       | `[]`                   | Extra raw flags appended to every call.  |

## What is validated

Validated by unit tests (no API key needed): stream-json parsing, the replay state
machine (domain-call filtering, prefix stripping, fresh-id alignment, cost/session
capture, fallbacks), per-task DB seeding round-trip, registry wiring, and CLI command
assembly.

Validated live: the retail bridge has been run end-to-end through a LiteLLM gateway
(Bedrock Claude Sonnet 4.5) with the `claude` CLI v2.1.173 — the flag set in
`build_command` (`--plugin-dir`, `--mcp-config`, `--strict-mcp-config`,
`--permission-mode bypassPermissions`, stream-json) drives the retail-harness plugin +
MCP server, and the replayed trajectory scores on the tau2 evaluator (reward, action,
and DB match). See [harnesses/docs/tau2-playbook.md](../../../../harnesses/docs/tau2-playbook.md) to
reproduce. CLI flags can drift across versions, so the assembly stays in one
overridable method (`ClaudeCLIRunner.build_command`) — tune there if a flag name has
moved.

## Caveats

- **Step budget.** Replaying N tool calls consumes ~N orchestrator steps; very long
  tasks may need a higher `--max-steps` on `tau2 run`.
- **Retail only.** This first bridge hardcodes the retail server/plugin. Airline and
  telecom generalize the same way (swap server module + plugin dir).
- **Double execution by design.** Claude executes tools against its own per-task MCP
  DB (so hooks/skills fire and it can reason on real data); tau2 re-executes the same
  calls against the *scored* env on replay. The two are independent copies seeded from
  the same `initial_state`, so the scored env is authoritative.
