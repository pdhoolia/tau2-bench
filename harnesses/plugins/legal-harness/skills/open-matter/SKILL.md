---
name: open-matter
description: Choose a responsible practitioner with a current practising certificate and open the matter. Use as the final intake step, once the conflict check is clear, the client exists and is identity-verified, and any required costs agreement is in place. Confirm every precondition before the write.
allowed-tools: "mcp__tau2-legal__get_practitioner mcp__tau2-legal__list_practitioners mcp__tau2-legal__get_client mcp__tau2-legal__get_conflict_check mcp__tau2-legal__get_costs_agreement mcp__tau2-legal__open_matter mcp__tau2-legal__transfer_to_human"
---

# Open the matter (final step)

This is the last intake step. `open_matter` enforces the firm's intake policy and
will fail unless every precondition holds, so confirm them first.

## Responsible practitioner

1. **Current practising certificate required.** Use `get_practitioner` (or
   `list_practitioners`) and confirm `pc_status == "current"`. Do **not** assign a
   practitioner whose certificate is `expired` or `suspended` — pick another
   practitioner with a current certificate, or escalate with `transfer_to_human`.

## Confirm the preconditions

Before calling `open_matter`, verify all of:

- the supplied **conflict check** exists and its status is `clear`
  (`get_conflict_check`);
- the **client's identity is verified** (`get_client` → `identity_verified` true);
- the **responsible practitioner** holds a current practising certificate;
- if estimated costs are **$750 or more**, a **costs agreement** is attached;
- if estimated costs **exceed $3,000**, the attached agreement is a **signed,
  full-disclosure** agreement (`get_costs_agreement` → `disclosure_tier == "full"`
  and `signed` true).

Consider running the `/legal-harness:intake-audit` command (the `intake-auditor`
sub-agent) for an independent read-only re-check of these preconditions before the
write.

## Choosing `matter_type`

`matter_type` is the **area of law** — `commercial`, `family`, `conveyancing`,
`estates`, or `employment`. It is **not** a dispute posture: whether a matter is
contentious / heading to court does not change its area (a commercial dispute is
still `commercial`; a family dispute is still `family`).

Use the area the client/staff stated and map their words to the closest value —
**default to their categorization**:

- "commercial dispute", "shareholder dispute", "contract dispute" → `commercial`
- "family matter", "divorce", "parenting" → `family`
- "conveyancing", "property purchase/sale" → `conveyancing`
- "estate", "probate", "will" → `estates`
- "employment", "unfair dismissal" → `employment`

Do **not** reclassify by posture: the presence of an opposing party, a "dispute",
or pending proceedings does **not** change the area of law. If the area is
genuinely unclear, **confirm with the requester** rather than guessing.

## Open it

2. **Call `open_matter`** with: `client_id`, `responsible_practitioner_id`,
   `matter_type` (`commercial`, `family`, `conveyancing`, `estates`, or
   `employment`) — the area of law, chosen per "Choosing `matter_type`" above,
   `estimated_costs`, the cleared `conflict_check_id`, `opposing_parties`, and
   (where required) the `costs_agreement_id`.

## Guardrail

A deterministic PreToolUse hook re-checks that a costs agreement is attached when
estimated costs are $750 or more, before `open_matter` runs. A deny is a hard
stop. The status / verification / certificate / disclosure-tier preconditions are
re-checked against live data by the `intake-auditor` sub-agent.
