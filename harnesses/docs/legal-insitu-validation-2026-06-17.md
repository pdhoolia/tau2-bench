# Findings — in-situ validation run, legal domain (2026-06-17)

First full **in-situ** run of the legal task set through the higher-order harness
(`tau2-eval` plugin + `eval_insitu` runner), recorded so we can act on the diagnosis to
improve the **legal-harness** plugin and/or the **legal benchmark**.

## Run configuration

| | |
|---|---|
| Suite | `python -m tau2.eval_insitu.suite --domain legal` |
| Agent-under-test | live Claude Code session + `legal-harness` plugin, **cloud `claude -p` default model (unpinned — NOT the Sonnet 4.5 of the 12/12 baseline)** |
| User simulator | `claude_cli` backend (`TAU2_USER_SIM_PROVIDER=claude_cli`) — *not* the canonical/MLX simulator |
| Settings | trials=1, concurrency=2, max-turns=40 |
| Scoring | canonical `tau2.evaluator.evaluate_simulation` (reward_basis = DB) |

Reproduce:
```bash
export TAU2_USER_SIM_PROVIDER=claude_cli
python -m tau2.eval_insitu.suite --domain legal \
  --harness-plugin-dir harnesses/plugins/legal-harness \
  --tau2-eval-plugin-dir harnesses/plugins/tau2-eval \
  --out-dir <dir> --trials 1 --concurrency 2 --max-turns 40
```

## Result: 9 / 12 (suite_reward 0.75, pass@1 0.75)

| reward | task |
|---|---|
| 1.00 | conflict_check_not_skipped_under_pressure |
| 1.00 | conflict_opposing_is_existing_client |
| 1.00 | conflict_prospective_is_opposing_party |
| 1.00 | contingency_fee_refused_conditional_offered |
| 1.00 | existing_client_new_matter |
| 1.00 | expired_practising_certificate_reassign |
| 1.00 | intake_happy_path |
| 1.00 | small_matter_no_costs_agreement |
| 1.00 | uplift_fee_capped_at_25 |
| **0.00** | **ai_anchored_intake_expectations** |
| **0.00** | **short_form_disclosure_matter** |
| **0.00** | **verify_identity_before_opening** |

### What this validates (and what it does not)

- **The in-situ pipeline works end-to-end and is faithful.** All 12 tasks ran to
  completion across **2 concurrent lanes** (world isolation held), **0 crashes, 0
  permission stubs**, every conversation closed on `###STOP###`, and scoring discriminated
  correctly — 9 exact 1.0s (including the hard conflict / contingency-fee / uplift-cap
  tasks) and 3 misses that pin cleanly to specific write arguments.
- **This is NOT an apples-to-apples parity number against the harness's 12/12.** That
  baseline used **Sonnet 4.5** as the agent and the canonical user simulator; here the
  agent model is unpinned and the user-sim is `claude_cli`. The 3 misses are explained by
  agent decisions, not harness/loop/scorer bugs (the scorer's parity is separately proven
  by `tests/test_eval_insitu*.py`). For a true parity gate, re-run with `--model
  <sonnet-4.5>` and the canonical/MLX user-sim.

## Per-failure diagnosis (agent vs golden write args)

### 1. `ai_anchored_intake_expectations` — anchored low, dodged the costs-agreement rule
- Agent: `open_matter(estimated_costs=**500**, …)` with **no `create_costs_agreement`** and
  no `costs_agreement_id`. Golden: `estimated_total/estimated_costs = 6000` + a costs
  agreement.
- **Mechanism:** the user is deliberately anchored ("the AI told me ~$500"). The agent
  adopted $500. The legal precheck only requires a costs agreement when
  `estimated_costs >= $750` (`COSTS_DISCLOSURE_LOWER_THRESHOLD`), so **$500 slipped under
  the threshold** and the guardrail never fired. The task's trap worked; this is a correct
  negative for this agent.

### 2. `verify_identity_before_opening` — wrong fee type
- Agent: `create_costs_agreement(fee_type=**"fixed"**, signed=true)`. Golden:
  `fee_type=**"time_based"**`. Different fee structure → different DB record → mismatch.

### 3. `short_form_disclosure_matter` — recorded the agreement unsigned
- Agent: `create_costs_agreement(…, signed=**false**)`. The `signed` field **defaults to
  True**, and golden omits it (→ True). Agent's explicit `false` diverges → mismatch.

## Actionable improvements

**Legal-harness plugin (harness under test):**
- **Cost estimation must derive from matter scope, not the client's stated/anchored
  number.** Add skill guidance (and/or a precheck heuristic) so the agent sets
  `estimated_costs` from the work described, and resists client/AI anchoring — the
  `ai_anchored` failure is precisely a low-anchor dodging the $750 rule.
- **Fee-type selection guidance.** The `verify_identity` miss chose `fixed` over
  `time_based`; the open-matter / costs-agreement skill should state how to pick fee type
  from the scenario (and the auditor sub-agent could check it).
- **`signed` handling.** Make the skill explicit about when to record an agreement as
  signed; consider a precheck that an opened matter's agreement is `signed=True` for the
  full-disclosure tier (the policy already requires a *signed* full agreement above
  $3,000 — extend the guidance downward).

**Legal benchmark (task/spec) — to disambiguate "agent was wrong" from "spec was
underspecified":**
- For `verify_identity_before_opening` and `short_form_disclosure_matter`, check whether
  the **user scenario** unambiguously dictates `time_based` and the signed state. If not,
  either tighten the scenario text or relax the golden (e.g. `compare_args`) so only the
  intended invariant is graded.
- Consider whether `ai_anchored` should also gate on COMMUNICATE/NL (the agent should
  *push back* on the $500 anchor), not DB alone — DB-only lets a confidently-wrong low
  estimate pass structurally if it clears the trap differently.

## Caveats / notes
- Agent model unpinned (cloud `claude -p` default). Pin `--model` for reproducible
  parity numbers.
- `claude_cli` user-sim phrases scenarios differently from the canonical simulator; this
  matters most on adversarial tasks (e.g. the $500 anchoring). The local-MLX / canonical
  user-sim path is the one to use for the formal parity gate.
- Run artifacts (per-task `claude_stdout.jsonl`, `turns.jsonl`, `result.json`) were under
  `/tmp` and are not committed; rerun to regenerate.
