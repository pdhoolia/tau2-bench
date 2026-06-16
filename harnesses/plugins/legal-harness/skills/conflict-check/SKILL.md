---
name: conflict-check
description: Run the mandatory conflict-of-interest check that must come first in every intake, before any client record or matter is created. Use as soon as you have a prospective client name and the opposing parties. Handles a clear result (proceed) and a conflict_found result (stop and escalate).
allowed-tools: "mcp__tau2-legal__run_conflict_check mcp__tau2-legal__get_conflict_check mcp__tau2-legal__transfer_to_human"
---

# Run the conflict check (always first)

The conflict-of-interest check is the **mandatory first step** of every intake.
No client may be created and no matter may be opened until a conflict check has
been run for this prospective client and has come back `clear`.

## Steps

1. **Collect the inputs.** You need the prospective client's full name and the
   names of **all** opposing parties for the proposed matter. Ask for any you are
   missing — do not run the check blank.
2. **Run it.** Call `run_conflict_check(prospective_client_name, opposing_parties)`.
3. **Read the result.**
   - `clear` → record the `conflict_check_id` and continue with the intake.
   - `conflict_found` → **do not open the matter.** Explain that a conflict of
     interest has been identified, that you cannot waive it yourself, and that the
     matter must be escalated to a principal. Call `transfer_to_human` with a short
     summary of the conflict.

## Rules

- Never skip or defer this step, even under time pressure or reassurance that "it
  will be fine".
- Do not attempt to resolve or waive a conflict yourself — that is a principal's
  decision.
- A new conflict check must be run for the specific prospective client and
  opposing parties of *this* matter; do not reuse an unrelated check.

## Guardrail

A deterministic PreToolUse hook re-checks that `run_conflict_check` is called with
a non-empty client name before it executes. A deny is a hard stop.
