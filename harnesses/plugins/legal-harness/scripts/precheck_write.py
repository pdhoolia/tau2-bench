#!/usr/bin/env python3
"""PreToolUse guardrail for legal-intake WRITE tools.

Verification determinism (see "Governing the Determinism Spectrum in Legal
Practice"): the intake policy says the assistant "must" follow the steps and the
fee rules, but a confident, wrong tool call would otherwise slip straight through.
This hook moves the must-hold invariants into a room the model cannot enter. The
harness runtime invokes it on every legal MCP write, before the call reaches the
tool. A "deny" decision blocks the call and feeds the reason back to the model.

Scope (Phase 1): this hook enforces invariants decidable from the *tool arguments
alone* -- no live DB read required, so it is fully deterministic and order-of-
operations independent:

  * create_costs_agreement
      - fee_type in {time_based, fixed, conditional} (contingency/percentage
        fees are prohibited under the LPUL);
      - a conditional agreement requires an uplift > 0 and <= 25%;
      - an uplift may only be set on a conditional agreement.
  * open_matter
      - if estimated_costs >= $750, a costs_agreement_id must be attached.
  * run_conflict_check
      - a non-empty prospective_client_name (the check is the mandatory first
        step and is meaningless without a name).

Invariants that require live state -- conflict check actually returned 'clear',
client identity verified, responsible practitioner holds a CURRENT practising
certificate, and (above $3,000) the attached agreement is full-disclosure and
signed -- are deferred to the `intake-auditor` sub-agent, which reads the live DB.
They are documented in the plugin README.

The hook reads the PreToolUse payload as JSON on stdin and, on a violation, prints
a PreToolUse-specific output that denies the call. On success it exits 0 silently,
leaving the decision to normal permission flow.
"""

import json
import sys

PERMITTED_FEE_TYPES = {"time_based", "fixed", "conditional"}
COSTS_DISCLOSURE_LOWER_THRESHOLD = 750.0
MAX_UPLIFT_PERCENTAGE = 25.0


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


def _check_costs_agreement(args):
    fee_type = args.get("fee_type")
    if fee_type is not None and fee_type not in PERMITTED_FEE_TYPES:
        _deny(
            f"Fee type {fee_type!r} is not permitted. The LPUL allows only "
            "'time_based', 'fixed', or 'conditional' fees; contingency / "
            "percentage-of-recovery fees are prohibited. Offer a conditional "
            "('no win, no fee') agreement with an uplift of up to 25% instead."
        )

    uplift = args.get("uplift_percentage")
    if fee_type == "conditional":
        if uplift is None:
            _deny(
                "A conditional costs agreement requires an uplift_percentage "
                "(greater than 0 and no more than 25%). Confirm the uplift with "
                "the client before creating the agreement."
            )
        try:
            up = float(uplift)
        except (TypeError, ValueError):
            _deny(f"uplift_percentage {uplift!r} must be a number between 0 and 25.")
        if up <= 0 or up > MAX_UPLIFT_PERCENTAGE:
            _deny(
                f"Uplift of {up}% is invalid. The uplift on a conditional costs "
                f"agreement must be greater than 0 and no more than "
                f"{MAX_UPLIFT_PERCENTAGE}% under the LPUL."
            )
    elif uplift is not None:
        _deny(
            "An uplift fee can only be set on a 'conditional' costs agreement, "
            f"not on a {fee_type!r} one. Remove the uplift_percentage."
        )


def _check_open_matter(args):
    estimated = args.get("estimated_costs")
    try:
        est = float(estimated) if estimated is not None else None
    except (TypeError, ValueError):
        est = None
    if (
        est is not None
        and est >= COSTS_DISCLOSURE_LOWER_THRESHOLD
        and not args.get("costs_agreement_id")
    ):
        _deny(
            f"Estimated costs of ${est:,.0f} are at or above the $750 disclosure "
            "threshold, so a costs agreement must be created and attached "
            "(costs_agreement_id) before the matter can be opened."
        )


def _check_conflict_check(args):
    name = (args.get("prospective_client_name") or "").strip()
    if not name:
        _deny(
            "run_conflict_check needs the prospective client's name. The conflict "
            "check is the mandatory first intake step and cannot be run blank."
        )


def check(tool, args):
    """Apply the deterministic, argument-level invariants for `tool`."""
    if tool == "create_costs_agreement":
        _check_costs_agreement(args)
    elif tool == "open_matter":
        _check_open_matter(args)
    elif tool == "run_conflict_check":
        _check_conflict_check(args)


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
