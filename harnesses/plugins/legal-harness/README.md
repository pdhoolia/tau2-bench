# legal-harness

A higher-order harness for the tau2-bench **legal** domain (NSW boutique-firm
client intake under the Legal Profession Uniform Law), packaged as a Claude Code
plugin. It decomposes [`data/tau2/domains/legal/policy.md`](../../../data/tau2/domains/legal/policy.md)
by *altitude on the determinism spectrum* and routes each concern to the plugin
primitive built for it, instead of asking one prompt to be procedure-runner,
calculator, and bouncer at once.

This is the legal-domain application of the position pieces in
[`docs/vision/`](../../../docs/vision) — *"Governing the Determinism Spectrum"* and
its NSW-legal adaptation: keep the model fluent where fluency is cheap (gathering
facts, explaining the position), and pin down the handful of intake invariants
that, if wrong, are negligence in waiting.

## The mapping

| Altitude        | Primitive | In this plugin                                                                                                                       |
| --------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Soft judgment / procedure | **skill**     | `intake-process` (the ordered procedure + routing), `conflict-check`, `client-and-identity`, `costs-agreement`, `open-matter` — progressively disclosed, one per policy step. |
| Computation     | **script**    | `scripts/costs_assessment.py` — the costs-disclosure tier + fee/uplift validation, frozen to the LPUL thresholds so it cannot drift.   |
| Hard invariant  | **hook**      | `scripts/precheck_write.py` (PreToolUse) — denies fee/uplift/threshold violations *before* the legal MCP write runs.                   |
| Isolated audit  | **sub-agent** | `agents/intake-auditor.md` — re-checks the open-matter preconditions against the live DB in its own context window.                    |
| Entry point     | **command**   | `/legal-harness:conflict-check`, `/legal-harness:intake-audit`.                                                                        |
| Tools           | **MCP**       | `.mcp.json` → the fork's legal MCP server (`tau2-legal`).                                                                              |

## Layout

```
legal-harness/
├── .claude-plugin/plugin.json
├── .mcp.json                       # tau2-legal MCP connector (http://localhost:8000/mcp/legal)
├── skills/
│   ├── intake-process/SKILL.md
│   ├── conflict-check/SKILL.md
│   ├── client-and-identity/SKILL.md
│   ├── costs-agreement/SKILL.md
│   └── open-matter/SKILL.md
├── commands/
│   ├── conflict-check.md
│   └── intake-audit.md
├── agents/
│   └── intake-auditor.md
├── hooks/
│   └── hooks.json                  # PreToolUse → scripts/precheck_write.py
└── scripts/
    ├── precheck_write.py           # deterministic pre-write guardrail
    └── costs_assessment.py         # deterministic costs-disclosure / fee calculator
```

## Prerequisites

The plugin's *hands* are the legal MCP server in this fork. Start it (needs
`uv sync --extra mcp`):

```bash
python -m tau2.mcp.unified_server --port 8000     # legal at /mcp/legal
# or, standalone:
python -m tau2.mcp.legal_server --transport http --port 8000   # legal at /mcp/
```

If you use the standalone server, point `.mcp.json` at `http://localhost:8000/mcp/`.

## Install

```
/plugin marketplace add ./harnesses
/plugin install legal-harness@tau2-harnesses
```

## The guardrail, precisely

`precheck_write.py` enforces only invariants decidable from the **tool arguments
alone**, so it is fully deterministic regardless of DB state or call ordering:

- `create_costs_agreement` — `fee_type` ∈ {`time_based`, `fixed`, `conditional`}
  (contingency / percentage-of-recovery fees denied); a conditional agreement
  requires an uplift `> 0` and `≤ 25`; an uplift may only be set on a conditional.
- `open_matter` — if `estimated_costs ≥ 750`, a `costs_agreement_id` must be
  attached.
- `run_conflict_check` — a non-empty `prospective_client_name`.

A violation returns a PreToolUse `deny` with a reason, which Claude Code surfaces
back to the agent — the write never reaches the tool.

### Not yet enforced by the hook (sub-agent / tool only)

Invariants that need **live state** — the conflict check actually returned
`clear`, the client's identity is verified, the responsible practitioner holds a
**current** practising certificate, and (above $3,000) the attached agreement is
`full`-disclosure and `signed` — are *documented in the skills and re-checked by
the `intake-auditor` sub-agent*, which reads the live DB. They are also enforced by
the domain's own `open_matter` tool. The hook is intentionally stateless: it
catches the argument-level mistakes a confident model makes, without depending on a
DB read that could go stale mid-session. The legal MCP server is per-task seeded by
the `claude_harness` bridge, so a follow-up that feeds the hook live environment
state could move those predicates into the hook too.

## Running it under tau2

This plugin runs head-to-head against the legacy `llm_agent` via the
`--agent claude_harness` bridge (Architecture B: Claude owns its loop and calls the
real legal tools over MCP; the bridge reconciles those calls into the trajectory
the evaluator scores — see [`src/tau2/agent/claude_harness/`](../../../src/tau2/agent/claude_harness)).
For the end-to-end commands (preflight, smoke run, full run, the `run_eval.sh`
shortcut), follow the [**evaluation playbook**](../../playbook.md):

```bash
harnesses/run_eval.sh legal smoke both     # 1-task wiring check, baseline + harness
harnesses/run_eval.sh legal full harness   # full legal split, harness only
```
