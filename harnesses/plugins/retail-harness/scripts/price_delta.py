#!/usr/bin/env python3
"""Deterministic price-difference calculator for retail item swaps.

Computational determinism (see "Gradual Determinism"): the retail policy charges
or refunds the *price difference* when a pending order's items are modified, or a
delivered order's items are exchanged. Letting the model re-derive that sum
token-by-token is exactly the kind of arithmetic tau2 scores as a failure when it
drifts a cent. This script freezes the calculation: same inputs, same output,
every time, from code a human reviewed.

It mirrors the math in src/tau2/domains/retail/tools.py
(modify_pending_order_items / exchange_delivered_order_items): sum(new - old)
over the swapped items, rounded to 2 decimals; positive => the customer is
charged, negative => the customer is refunded; and a gift card must hold enough
balance to cover a charge.

Usage:
    price_delta.py --pairs '[[old1, new1], [old2, new2], ...]'
    price_delta.py --pairs '[[52.0, 55.0]]' --gift-card-balance 3.50

Output: a JSON object on stdout, e.g.
    {
      "total_diff": 3.0,
      "direction": "charge",
      "abs_amount": 3.0,
      "gift_card_balance": 3.5,
      "gift_card_sufficient": true
    }
"""

import argparse
import json
import sys


def compute(pairs, gift_card_balance=None):
    """Compute the rounded price difference and gift-card sufficiency.

    :param pairs: list of [old_price, new_price] for each swapped item.
    :param gift_card_balance: optional balance of the gift card paying the
        difference; only meaningful when the result is a charge.
    :returns: dict describing the delta and (if applicable) gift-card coverage.
    """
    total = 0.0
    for pair in pairs:
        if len(pair) != 2:
            raise ValueError(f"Each pair must be [old_price, new_price]; got {pair!r}")
        old_price, new_price = float(pair[0]), float(pair[1])
        total += new_price - old_price
    total = round(total, 2)

    if total > 0:
        direction = "charge"
    elif total < 0:
        direction = "refund"
    else:
        direction = "none"

    result = {
        "total_diff": total,
        "direction": direction,
        "abs_amount": round(abs(total), 2),
    }

    if gift_card_balance is not None:
        bal = round(float(gift_card_balance), 2)
        result["gift_card_balance"] = bal
        # A gift card only needs to cover a *charge*; refunds always succeed.
        result["gift_card_sufficient"] = bal >= total if total > 0 else True

    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pairs",
        required=True,
        help='JSON list of [old_price, new_price] pairs, e.g. "[[52.0, 55.0]]".',
    )
    parser.add_argument(
        "--gift-card-balance",
        type=float,
        default=None,
        help="Balance of the gift card paying the difference (optional).",
    )
    args = parser.parse_args(argv)

    try:
        pairs = json.loads(args.pairs)
        if not isinstance(pairs, list):
            raise ValueError("--pairs must be a JSON list of [old, new] pairs")
        result = compute(pairs, args.gift_card_balance)
    except (ValueError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
