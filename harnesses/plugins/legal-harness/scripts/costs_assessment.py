#!/usr/bin/env python3
"""Deterministic costs-disclosure / fee assessment for NSW legal intake.

Computational determinism (see "Governing the Determinism Spectrum in Legal
Practice"): the firm's costs-disclosure obligations and fee rules under the Legal
Profession Uniform Law turn on fixed thresholds, not judgement. Letting the model
re-derive "is a written agreement required here?" or "is this uplift lawful?"
token-by-token is exactly the kind of step that drifts between fee-earners. This
script freezes it: identical inputs, identical answer, every time, from code a
principal reviewed.

It mirrors the thresholds in src/tau2/domains/legal/utils.py and the rules in
src/tau2/domains/legal/tools.py (`_disclosure_tier`, `create_costs_agreement`,
and the `open_matter` cost preconditions):

  * disclosure tier from the estimated total legal costs (excl. GST & disb.):
        < $750            -> "none"        (no formal disclosure required)
        $750  - $3,000    -> "short_form"  (disclosure required)
        > $3,000          -> "full"        (written, signed agreement required)
  * a costs agreement must be attached once estimated costs reach $750;
  * above $3,000 that agreement must be full-disclosure AND signed;
  * permitted fee types are time_based / fixed / conditional;
    contingency / percentage-of-recovery fees are PROHIBITED;
  * a conditional ("no win, no fee") agreement may carry an uplift fee that is
    greater than 0 and capped at 25%; uplift is only valid on a conditional.

Usage:
    costs_assessment.py --estimated-total 8000
    costs_assessment.py --estimated-total 8000 --fee-type conditional --uplift 20
    costs_assessment.py --estimated-total 500 --fee-type time_based

Output: a JSON object on stdout, e.g.
    {
      "estimated_total": 8000.0,
      "disclosure_tier": "full",
      "costs_agreement_required": true,
      "written_signed_agreement_required": true,
      "fee_type": "conditional",
      "fee_permitted": true,
      "uplift_required": true,
      "uplift_valid": true,
      "messages": ["..."]
    }
"""

import argparse
import json
import sys

# Thresholds mirror src/tau2/domains/legal/utils.py.
COSTS_DISCLOSURE_LOWER_THRESHOLD = 750.0
COSTS_DISCLOSURE_UPPER_THRESHOLD = 3000.0
MAX_UPLIFT_PERCENTAGE = 25.0

PERMITTED_FEE_TYPES = {"time_based", "fixed", "conditional"}


def disclosure_tier(estimated_total: float) -> str:
    """Return the disclosure tier for an estimated total (LPUL thresholds)."""
    if estimated_total > COSTS_DISCLOSURE_UPPER_THRESHOLD:
        return "full"
    if estimated_total >= COSTS_DISCLOSURE_LOWER_THRESHOLD:
        return "short_form"
    return "none"


def assess(estimated_total, fee_type=None, uplift_percentage=None):
    """Assess costs-disclosure obligations and (optionally) the fee arrangement.

    :param estimated_total: estimated total legal costs (AUD, excl. GST & disb.).
    :param fee_type: optional proposed fee type to validate.
    :param uplift_percentage: optional uplift fee percentage for a conditional.
    :returns: dict describing the disclosure obligations and fee validity.
    """
    total = round(float(estimated_total), 2)
    tier = disclosure_tier(total)

    result = {
        "estimated_total": total,
        "disclosure_tier": tier,
        "costs_agreement_required": total >= COSTS_DISCLOSURE_LOWER_THRESHOLD,
        "written_signed_agreement_required": total > COSTS_DISCLOSURE_UPPER_THRESHOLD,
    }
    messages = []
    if tier == "none":
        messages.append(
            "Below $750: no formal costs disclosure required; a costs agreement "
            "is optional."
        )
    elif tier == "short_form":
        messages.append(
            "$750-$3,000: costs disclosure required. Create a costs agreement "
            "(short-form disclosure tier is recorded automatically)."
        )
    else:
        messages.append(
            "Above $3,000: a written, signed costs agreement (full disclosure) is "
            "required before the matter can be opened."
        )

    if fee_type is not None:
        permitted = fee_type in PERMITTED_FEE_TYPES
        result["fee_type"] = fee_type
        result["fee_permitted"] = permitted
        if not permitted:
            messages.append(
                f"Fee type {fee_type!r} is not permitted. The LPUL allows only "
                "time_based, fixed, or conditional fees; contingency / "
                "percentage-of-recovery fees are prohibited. Offer a conditional "
                "('no win, no fee') agreement with an uplift of up to 25% instead."
            )

        if fee_type == "conditional":
            result["uplift_required"] = True
            if uplift_percentage is None:
                result["uplift_valid"] = False
                messages.append(
                    "A conditional costs agreement requires an uplift_percentage "
                    "(greater than 0, capped at 25%)."
                )
            else:
                up = float(uplift_percentage)
                valid = 0 < up <= MAX_UPLIFT_PERCENTAGE
                result["uplift_percentage"] = up
                result["uplift_valid"] = valid
                if not valid:
                    messages.append(
                        f"Uplift of {up}% is invalid: it must be greater than 0 and "
                        f"no more than {MAX_UPLIFT_PERCENTAGE}% under the LPUL."
                    )
        else:
            result["uplift_required"] = False
            if uplift_percentage is not None:
                result["uplift_valid"] = False
                messages.append(
                    "An uplift fee can only be set on a 'conditional' costs agreement."
                )

    result["messages"] = messages
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--estimated-total",
        type=float,
        required=True,
        help="Estimated total legal costs (AUD, excl. GST & disbursements).",
    )
    parser.add_argument(
        "--fee-type",
        default=None,
        help="Proposed fee type to validate: time_based, fixed, or conditional.",
    )
    parser.add_argument(
        "--uplift",
        dest="uplift",
        type=float,
        default=None,
        help="Uplift fee percentage for a conditional agreement (0 < x <= 25).",
    )
    args = parser.parse_args(argv)

    try:
        result = assess(args.estimated_total, args.fee_type, args.uplift)
    except (ValueError, TypeError) as e:
        print(json.dumps({"error": str(e)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
