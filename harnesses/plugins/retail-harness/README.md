# retail-harness

A higher-order harness for the tau2-bench **retail** domain, packaged as a Claude
Code plugin. It decomposes [`data/tau2/domains/retail/policy.md`](../../../data/tau2/domains/retail/policy.md)
by *altitude on the determinism spectrum* and routes each concern to the plugin
primitive built for it, instead of asking one prompt to be judge, calculator, and
bouncer at once.

## The mapping

| Altitude        | Primitive | In this plugin                                                                                             |
| --------------- | --------- | ---------------------------------------------------------------------------------------------------------- |
| Soft judgment / procedure | **skill**     | `authenticate-user`, `cancel-pending-order`, `modify-pending-order`, `return-delivered-order`, `exchange-delivered-order` — progressively disclosed, one per policy section. |
| Computation     | **script**    | `scripts/price_delta.py` — the charge/refund price-difference math, frozen so it cannot drift a cent.       |
| Hard invariant  | **hook**      | `scripts/precheck_write.py` (PreToolUse) — denies out-of-policy writes *before* the MCP tool runs.          |
| Isolated audit  | **sub-agent** | `agents/policy-auditor.md` — re-checks a proposed write against the rulebook in its own context window.     |
| Entry point     | **command**   | `/retail-harness:authenticate`, `/retail-harness:audit-order`.                                              |
| Tools           | **MCP**       | `.mcp.json` → the fork's retail MCP server (`tau2-retail`).                                                 |

## Layout

```
retail-harness/
├── .claude-plugin/plugin.json
├── .mcp.json                       # tau2-retail MCP connector (http://localhost:8000/mcp/retail)
├── skills/
│   ├── authenticate-user/SKILL.md
│   ├── cancel-pending-order/SKILL.md
│   ├── modify-pending-order/SKILL.md
│   ├── return-delivered-order/SKILL.md
│   └── exchange-delivered-order/SKILL.md
├── commands/
│   ├── authenticate.md
│   └── audit-order.md
├── agents/
│   └── policy-auditor.md
├── hooks/
│   └── hooks.json                  # PreToolUse → scripts/precheck_write.py
└── scripts/
    ├── precheck_write.py           # deterministic pre-write guardrail
    └── price_delta.py              # deterministic price-difference calculator
```

## Prerequisites

The plugin's *hands* are the retail MCP server already in this fork. Start it
(needs `uv sync --extra mcp`):

```bash
python -m tau2.mcp.unified_server --port 8000     # retail at /mcp/retail
# or, standalone:
python -m tau2.mcp.retail_server --transport http --port 8000   # retail at /mcp/
```

If you use the standalone server, point `.mcp.json` at `http://localhost:8000/mcp/`.

## Install

```
/plugin marketplace add ./harnesses
/plugin install retail-harness@tau2-harnesses
```

## The guardrail, precisely

`precheck_write.py` enforces only invariants decidable from the **tool arguments
alone**, so it is fully deterministic regardless of order state or call ordering:

- `cancel_pending_order` — reason ∈ {`no longer needed`, `ordered by mistake`}.
- `modify_pending_order_items` / `exchange_delivered_order_items` — `item_ids` and
  `new_item_ids` equal length; for modify, no item maps to itself.
- any write naming an `order_id` — id is well-formed (`#…`).

A violation returns a PreToolUse `deny` with a reason, which Claude Code surfaces
back to the agent — the write never reaches the tool.

### Not yet enforced by the hook (still sub-agent-only)

Invariants that need **live order status** — "order must be `pending`/`delivered`",
gift-card balance sufficiency, one-shot-already-used, cross-user ownership — are
*documented in the skills and checked by the `policy-auditor` sub-agent*, but are
**not** yet enforced by the hook. The hook is intentionally stateless for now
because a static read of `db.json` would not reflect in-session mutations. The
`claude_harness` tau2 agent now bridges MCP tool calls back into the tau2 trajectory;
a follow-up that feeds the hook live environment state would let those predicates move
into the hook, closing the gap the policy's "the agent must make sure" clauses point
at.

## Running it under tau2

This plugin runs head-to-head against the legacy `llm_agent` via the
`--agent claude_harness` bridge (Architecture B: Claude owns its loop and calls the
real retail tools over MCP; the bridge reconciles those calls into the trajectory the
evaluator scores — see [`src/tau2/agent/claude_harness/`](../../../src/tau2/agent/claude_harness)).
For the end-to-end commands (preflight, smoke run, full run, the `run_eval.sh`
shortcut), follow the [**evaluation playbook**](../../playbook.md).

Still open: the live-status invariants listed above are checked by the
`policy-auditor` sub-agent, not yet enforced by the (intentionally stateless)
PreToolUse hook.
