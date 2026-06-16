---
description: Run the mandatory conflict-of-interest check that must precede any intake.
argument-hint: "[prospective client name; opposing parties]"
---

Run the conflict-of-interest check for this intake using the **conflict-check**
skill. This is the mandatory first step — no client may be created and no matter
opened until a conflict check has been run and returned `clear`.

Prospective client / opposing parties (if provided): $ARGUMENTS

Ask for the prospective client's name and all opposing parties if they are not
supplied. Run `run_conflict_check`, then report the result:

- `clear` → state the `conflict_check_id` and that the intake may proceed.
- `conflict_found` → do not open the matter; explain the conflict and escalate to a
  principal with `transfer_to_human`.
