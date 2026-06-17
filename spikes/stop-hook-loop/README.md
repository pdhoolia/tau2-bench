# Phase 0 spike — Stop-hook continuation loop

De-risks the **#1 unknown** of the higher-order-harness design
([`docs/higher-order-harness.md`](../../docs/higher-order-harness.md), risk #1):

> Can a Claude Code **Stop hook** force the main session to *continue* a conversation by
> feeding the next "user" message back to the model — so the tau2 user-simulator can drive
> the agent-under-test from the outside, invisibly?

If yes, the whole inversion is clean: the agent-under-test runs as the main session (with its
plugin skills + PreToolUse hooks live), and a Stop hook plays the user simulator.

## What it does

- [`user_sim_stub.py`](user_sim_stub.py) — a Stop hook standing in for the user-simulator. Instead
  of calling an LLM, it replays a fixed script of follow-up turns, each asking the assistant for a
  distinct token (`TURN-B`, `TURN-C`, `TURN-D`). State is file-backed, keyed by `session_id`.
  Continuation uses `{"decision": "block", "reason": "<next user message>"}`; exhaustion returns
  `{}` to allow a clean stop.
- [`settings.json`](settings.json) — wires the hook as a `Stop` hook via `--settings`.
- [`run.sh`](run.sh) — launches `claude -p` (opening turn asks for `TURN-A`) and analyzes the log.
- [`analyze.py`](analyze.py) — parses the `stream-json` log and checks which tokens reached the model.

## Run

```bash
bash spikes/stop-hook-loop/run.sh
```

Requires an authenticated `claude` CLI. Runtime artifacts land in `.runtime/` (gitignored).

## Result — PASS (CLI 2.1.179, 2026-06-17)

Assistant emitted, in order: `TURN-A`, `TURN-B`, `TURN-C`, `TURN-D`. The hook trace:

```
stop_hook_fired  stop_hook_active=false  turn_index_before=0  -> inject TURN-B
stop_hook_fired  stop_hook_active=true   turn_index_before=1  -> inject TURN-C
stop_hook_fired  stop_hook_active=true   turn_index_before=2  -> inject TURN-D
stop_hook_fired  stop_hook_active=true   turn_index_before=3  -> allow_stop
```

Confirmed:

1. **`{"decision":"block","reason":...}` reliably feeds `reason` to the model as the next turn** —
   each injected follow-up produced its token. The orchestrator-via-Stop-hook design is viable.
2. **`stop_hook_active` is `true` on continuation iterations** — the documented loop-protection
   signal is present and usable (we bound the loop by a turn index regardless).
3. **`session_id` persists across the loop** — file-backed, session-keyed state works for the real
   user-simulator (transcript, turn count, stop detection).
4. **Returning `{}` allows a clean stop** — the natural terminal for "user ends the conversation".

## Notes / caveats

- Run as root, `--permission-mode bypassPermissions` is rejected; omitted here (text-only spike,
  no tools). The real plugin run will need a non-root user or an alternate permission mode.
- The real user-simulator replaces the scripted turns with one LLM call (tau2's user-sim prompt:
  `simulation_guidelines.md` + persona + scenario) and detects end-of-conversation
  (`###STOP###` / `###TRANSFER###` / `###OUT-OF-SCOPE###`) to decide block-vs-allow-stop.
- The terminal stop (return `{}`) is where the evaluator runs (`evaluate_simulation`).
</content>
