---
name: costs-agreement
description: Provide costs disclosure and create a costs agreement for a client under the LPUL. Use once estimated total legal costs are known. Computes the disclosure tier deterministically with a script, enforces the permitted fee types, and applies the 25% uplift cap and the prohibition on contingency fees.
allowed-tools: "mcp__tau2-legal__get_client mcp__tau2-legal__create_costs_agreement"
---

# Costs disclosure and costs agreement

Pre-req: the client exists and the estimated total legal costs (excl. GST and
disbursements) are known.

## Compute the obligations deterministically

Do **not** decide the disclosure tier or judge the fee in your head. Run the
frozen calculator, which encodes the LPUL thresholds and fee rules:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/costs_assessment.py" \
  --estimated-total ESTIMATED_TOTAL [--fee-type FEE_TYPE] [--uplift UPLIFT]
```

It returns JSON with:

- `disclosure_tier` — `none` (< $750), `short_form` ($750-$3,000), or `full`
  (> $3,000);
- `costs_agreement_required` — whether an agreement must be created at all;
- `written_signed_agreement_required` — whether it must be a signed, full
  agreement (estimated costs above $3,000);
- when `--fee-type` is given: `fee_permitted`, and for a conditional fee
  `uplift_required` / `uplift_valid`;
- human-readable `messages`.

Use those values to explain the position to the staff member and to set the
arguments below.

## Create the agreement

Call `create_costs_agreement(client_id, fee_type, estimated_total, ...)`:

- **Fee type** must be one of `time_based`, `fixed`, or `conditional`.
- **Above $3,000:** create a written agreement and set `signed=True` (the `full`
  disclosure tier is recorded automatically). The matter cannot be opened above
  $3,000 without a signed, full agreement.
- **$750-$3,000:** create the agreement (short-form tier recorded automatically).
- **Below $750:** an agreement is optional; create one only if asked.

## Fees — what is and isn't allowed

- A **conditional** ("no win, no fee") agreement may include an **uplift**, but it
  must be greater than 0 and **capped at 25%**. Pass it as `uplift_percentage`.
- An uplift may be set **only** on a conditional agreement.
- **Contingency / percentage-of-recovery fees are prohibited** under the LPUL. If a
  client or staff member asks for a fee that is a percentage of the amount
  recovered (e.g. "you take 30% of the payout"), **refuse** and explain it is not
  permitted in NSW. You may offer a conditional agreement with an uplift of up to
  25% instead.

## Guardrail

A deterministic PreToolUse hook re-checks the fee type, the uplift cap, and that an
uplift is only set on a conditional agreement, before `create_costs_agreement`
runs. A deny is a hard stop — fix the fee arrangement or refuse, do not work around
it.
