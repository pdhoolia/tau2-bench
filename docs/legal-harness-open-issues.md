# Legal-harness — open issues to investigate

> Handoff brief. Self-contained, but the working conversation needs the repo checked
> out on branch `pdhoolia/eval_legal_domain` to see the code/commits/run dirs below.

## Context
The `legal-harness` is a Claude Code plugin (skills + scripts + PreToolUse hooks over a
per-task legal MCP server) evaluated in tau2-bench via `--agent claude_harness`
(Architecture B: headless `claude -p` owns its loop; a bridge reconciles its tool calls
into the scored trajectory). Goal (per
[`determinism-spectrum-nsw-legal.html`](../harnesses/plugins/legal-harness/determinism-spectrum-nsw-legal.html)):
move must-hold intake invariants out of the model's reach (hooks/scripts) so the
harness, on the same base model, beats the plain `llm_agent` baseline.

Current reality: on the (now-corrected) 12-task legal benchmark, harness ≈ baseline at
single-trial (~0.58 both), bouncing 7–9/12 run-to-run. The intended guarantee mechanism
(the PreToolUse hook) is **not actually engaging** in live runs. Below are the exact
issues.

### Where things live
- Bridge: `src/tau2/agent/claude_harness/{agent.py,cli_runner.py,task_db.py}`
  - `cli_runner.build_command`: `claude -p --output-format stream-json --verbose
    --mcp-config … --plugin-dir … --permission-mode … --max-turns … [--resume <sid>]`,
    run with `cwd=<per-task temp dir>`. Per-task MCP server on an OS-free port.
- Plugin: `harnesses/plugins/legal-harness/`
  - `hooks/hooks.json` — PreToolUse matcher (run_conflict_check, create_client,
    create_costs_agreement, open_matter)
  - `scripts/precheck_write.py` — the hook (arg-level fee/threshold checks + a
    conversation-aware provenance check)
  - `skills/` — intake-process, conflict-check, client-and-identity, costs-agreement,
    open-matter
- Live claude transcripts: `~/.claude/projects/<encoded-temp-cwd>/<session>.jsonl`
  (type=user lines carry user-sim turns + tool_result blocks; type=assistant = model)
- Relevant commits on `pdhoolia/eval_legal_domain`: `dedb656` (benchmark fix: litigation
  removed as matter_type), `8f76d40` (provenance hook + skill/task-data sharpening),
  `41abe47` (client-and-identity DOB fix).
- Result dirs: `data/simulations/legal_clean_harness` (latest clean, 7/12),
  `legal_v3_harness` (fused 12), `legal_v3_baseline` (7/12).

---

## ISSUE 1 — Provenance hook does not engage in live runs (highest priority)
**Symptom:** Blatantly fabricated client addresses persist in `create_client` records,
un-denied: `ai_anchored` → "42 Maple Street, Sydney NSW 2000"; `conflict_check_not_
skipped` → "45 Collins Street, Melbourne VIC 3000" (a Melbourne address for a Sydney
firm). DB exact-match then fails because ground truth has no address.
**Evidence:** In the claude transcripts, the `create_client` tool_use carries the
fabricated address with **no deny tool_result after it**; no `permissionDecision` /
`provenance` strings appear in any transcript.
**Hooked code:** `precheck_write.py::_check_provenance` / `_load_provenance_tokens`. It
reads `payload["transcript_path"]`, builds a token corpus from `type==user` lines, and
denies `create_client` free-text fields (address/date_of_birth/abn) whose significant
tokens aren't in the corpus. **It fails OPEN** (skips) if the corpus is empty.
**Hypotheses to test:**
  1. `transcript_path` is absent/empty/not-yet-written when a PreToolUse hook fires in
     headless `claude -p` → empty corpus → check skipped. VERIFY FIRST: does a
     PreToolUse hook in headless mode actually receive a readable `transcript_path`?
     (Instrument the hook to log the payload keys + whether the file exists/parses.)
  2. Even when it reads, the "≥ half of significant tokens" threshold is too lenient:
     "Maple Street **Sydney** NSW **2000**" — `sydney`/`2000` are everywhere in a
     Sydney-firm transcript, giving a fabricated address false provenance.
**Directions:** (a) confirm transcript availability to hooks; if unavailable, feed
provenance another way (e.g., the bridge writes the per-turn user message / DB-read
results to a sidecar file the hook reads, or passes them via env). (b) Tighten address
matching: drop city/state/postcode/generic tokens, require the *distinctive* street
tokens to be present; consider fail-CLOSED for `create_client.address` when no
provenance source is available. (c) Decide fail-open vs fail-closed policy explicitly.

## ISSUE 2 — Duplicate `create_client` (real bug, reproduces)
**Symptom:** `uplift_fee_capped_at_25` calls `create_client` **twice** → duplicate
client record → DB mismatch. Reproduced in both the contended and the clean run, so it
is not just gateway contention.
**Context:** `client-and-identity` skill says "search first (find_clients) to avoid
duplicates." The model still double-creates.
**Directions:** Investigate the turn sequence (does find_clients return empty, then two
creates?). Candidate guard: a PreToolUse/idempotency check that denies a second
`create_client` once one has succeeded this session (needs session/transcript or DB
state — ties to Issue 1's state-access question). Or enforce find_clients→create
ordering in the hook.

## ISSUE 3 — DOB omission (soft-skill variance, not fully fixed)
**Symptom:** Agent sometimes omits a user-provided `date_of_birth` from `create_client`
(e.g., `contingency_fee` in the clean run) → DB mismatch. The `41abe47` skill fix
("include every detail the client provided, invent none") reduced but did not eliminate
it.
**Directions:** This is the inverse of fabrication — under-inclusion. A skill (in-band)
can't guarantee it. To enforce out-of-band, a hook would need to know the user provided
a DOB and assert it's present in the args — i.e., the same conversation/state access as
Issue 1. Investigate a "completeness" check alongside the provenance check.

## ISSUE 4 — Unjustified escalation (`transfer_to_human`)
**Symptom:** Agent escalates on a completable intake (`small_matter` clean run:
conflict→client→verify→**transfer_to_human**, never opens the matter) → missing records.
Persists despite the `intake-process` skill nudge to prefer completing.
**Directions:** Likely confusion around the sub-$750 "no costs agreement needed" path.
Investigate whether a hook should deny `transfer_to_human` unless a genuine block
condition holds (conflict found / no current practitioner / unlawful fee refused) —
again needs state to evaluate the block condition.

## ISSUE 5 — Unnecessary costs agreement below $750 (flaky)
**Symptom:** For sub-$750 matters the agent sometimes creates a costs agreement that
ground truth doesn't expect (extra record → mismatch). The costs-agreement skill now
says "below $750: do not create unless explicitly asked," but it's soft and flaky.
**Directions:** Candidate hook rule: deny `create_costs_agreement` when
`estimated_total < 750` and it wasn't explicitly requested ("explicitly requested" needs
conversation context → Issue 1 state-access again).

---

## CROSS-CUTTING

### A. Hooks need reliable conversation/DB-state access
Issues 1–5 all reduce to the same root: the must-hold invariants are **stateful** (did
the user say X? was a client already created? is this a genuine block?), but the hook
today is arg-only + a non-working transcript read. The plugin README explicitly deferred
stateful invariants to the `intake-auditor` sub-agent and noted "a follow-up that feeds
the hook live state could move those predicates into the hook." **The core engineering
question: how does the claude_harness bridge expose per-turn conversation text and/or
live MCP DB state to PreToolUse hooks reliably?** Solve this and 1–5 become enforceable.

### B. Evaluation is n=1 and variance-dominated
Single-trial runs bounce 7–9/12 with *different* tasks failing each time (matter_type
wording, estimate wording, address, dropped DOB, escalation). No conclusion about
"harness vs baseline" is trustworthy at n=1. **Evaluate at ≥3 trials (pass^k)**; hold
user-sim + judge models constant; vary only the agent. This is a measurement
prerequisite for validating any fix above.

### C. Benchmark-vs-harness boundary (out of harness scope)
Some failures are user-simulator improvisation against an exact-match DB, not agent
errors: the sim volunteers data the task author didn't expect (we already fixed
matter_type at the schema level and pinned the contingency/ai_anchored estimates).
Residual example: the sim surfacing an `address`. Decide per case whether to pin/relax
in task-data (`data/tau2/domains/legal/tasks.json`) or accept as noise — but track it
separately from harness bugs so the two don't get conflated.

---

## Suggested order in the new conversation
1. Verify hook ↔ transcript/state access (Issue 1 hypothesis 1) — unblocks 1–5.
2. Make the provenance check actually fire + tighten address matching (Issue 1).
3. Add stateful guards for duplicate-create / unjustified-escalation / sub-$750 CA
   (Issues 2, 4, 5) once state access exists.
4. Stand up a ≥3-trial eval harness (Cross-cutting B) to measure each fix.
