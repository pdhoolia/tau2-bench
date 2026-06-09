---
name: cancel-pending-order
description: Cancel a pending retail order. Use when an authenticated customer wants to cancel an order that has not yet shipped. Handles the status check, the restricted set of cancellation reasons, and explicit confirmation before the write.
allowed-tools: "mcp__tau2-retail__get_order_details mcp__tau2-retail__cancel_pending_order"
---

# Cancel a pending order

Pre-req: the customer is already authenticated (see authenticate-user) and the
order belongs to them.

## Steps

1. **Check status.** Call `get_order_details` and confirm `status == "pending"`.
   An order that is processed, delivered, or cancelled **cannot** be cancelled —
   say so and stop.
2. **Establish the reason.** The reason must be exactly one of:
   - `no longer needed`
   - `ordered by mistake`

   No other reason is acceptable. If the customer gives a different reason, ask
   them to choose one of these two, or decline the cancellation.
3. **Confirm explicitly.** List the order id, the items, the refund amount, and
   the reason, then obtain an explicit **yes** from the customer before writing.
4. **Cancel.** Call `cancel_pending_order(order_id, reason)`.

## What the customer should be told

After cancellation the order status becomes `cancelled` and the total is refunded
to the original payment method: **immediately** for a gift card, otherwise within
**5–7 business days**.

## Guardrail

A deterministic PreToolUse hook independently re-checks the reason enum and the
order-id format before `cancel_pending_order` executes. Treat a deny from it as a
hard stop, not a suggestion — fix the input or decline, do not work around it.
