#!/usr/bin/env python3
"""PreToolUse guardrail for retail WRITE tools.

Verification determinism (see "Gradual Determinism" / "From Agents to Harnesses"):
the retail policy says the agent "must" check eligibility before every write, but
the API does not enforce it -- so a confident, wrong tool call slips through. This
hook moves the must-check invariants into a room the agent cannot enter. The
harness runtime invokes it on every retail MCP write, before the call reaches the
tool. A "deny" decision blocks the call and feeds the reason back to the agent.

Scope (Phase 1): this hook enforces invariants decidable from the *tool arguments
alone* -- no live DB read required, so it is fully deterministic and order-of-
operations independent:

  * cancel_pending_order        reason in {'no longer needed', 'ordered by mistake'}
  * modify_pending_order_items  len(item_ids) == len(new_item_ids), and each new
                                item id differs from the one it replaces
  * exchange_delivered_order_items  len(item_ids) == len(new_item_ids)
  * any tool taking order_id    order_id is well-formed ('#W...' with a leading '#')

Invariants that require live order status (e.g. "order must be 'pending'") are
deferred to Phase 2, where the tau2 evaluation bridge gives the hook access to the
live environment state. They are documented in the plugin README.

The hook reads the PreToolUse payload as JSON on stdin and, on a violation, prints
a PreToolUse hook-specific output that denies the call. On success it exits 0
silently, leaving the decision to normal permission flow.
"""

import json
import sys

ALLOWED_CANCEL_REASONS = {"no longer needed", "ordered by mistake"}


def _tool_suffix(tool_name):
    """Return the bare tool name, stripping any 'mcp__<server>__' prefix."""
    return tool_name.rsplit("__", 1)[-1] if tool_name else tool_name


def _deny(reason):
    """Emit a PreToolUse deny decision and exit without blocking the run."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def _check_order_id(args):
    order_id = args.get("order_id")
    if order_id is not None and not str(order_id).startswith("#"):
        _deny(
            f"order_id {order_id!r} is malformed: retail order ids start with '#' "
            "(e.g. '#W0000000'). Re-read the order id before retrying."
        )


def check(tool, args):
    """Apply the deterministic, argument-level invariants for `tool`."""
    # Common: any write that names an order must name a well-formed one.
    _check_order_id(args)

    if tool == "cancel_pending_order":
        reason = args.get("reason")
        if reason not in ALLOWED_CANCEL_REASONS:
            _deny(
                f"Cancellation reason {reason!r} is not permitted. The retail "
                "policy accepts only 'no longer needed' or 'ordered by mistake'. "
                "Confirm one of these reasons with the user before cancelling."
            )

    elif tool in ("modify_pending_order_items", "exchange_delivered_order_items"):
        item_ids = args.get("item_ids") or []
        new_item_ids = args.get("new_item_ids") or []
        if len(item_ids) != len(new_item_ids):
            _deny(
                f"item_ids ({len(item_ids)}) and new_item_ids "
                f"({len(new_item_ids)}) must be the same length and aligned by "
                "position. Collect every item to change into one matched pair of "
                "lists before this single, one-shot call."
            )
        if tool == "modify_pending_order_items":
            for old, new in zip(item_ids, new_item_ids):
                if old == new:
                    _deny(
                        f"Item {old!r} is being 'modified' to itself. Each new "
                        "item id must differ from the one it replaces."
                    )


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Malformed payload: do not block the run on a guardrail parsing error.
        sys.exit(0)

    tool = _tool_suffix(payload.get("tool_name", ""))
    args = payload.get("tool_input") or {}
    if not isinstance(args, dict):
        sys.exit(0)

    check(tool, args)
    sys.exit(0)


if __name__ == "__main__":
    main()
