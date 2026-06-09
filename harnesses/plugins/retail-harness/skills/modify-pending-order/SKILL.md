---
name: modify-pending-order
description: Modify a pending retail order — its shipping address, payment method, or item options. Use when an authenticated customer wants to change (not cancel) an order that has not yet shipped. Covers the one-shot item-modification caution and price-difference handling.
allowed-tools: "mcp__tau2-retail__get_order_details mcp__tau2-retail__get_user_details mcp__tau2-retail__get_product_details mcp__tau2-retail__get_item_details mcp__tau2-retail__modify_pending_order_address mcp__tau2-retail__modify_pending_order_payment mcp__tau2-retail__modify_pending_order_items"
---

# Modify a pending order

Pre-req: the customer is authenticated and the order is theirs.

For a pending order you may modify **only** its shipping address, payment method,
or item options — nothing else. Always `get_order_details` first and confirm the
status is pending. Obtain an explicit **yes** before any write.

## Address — `modify_pending_order_address`
Collect the full address (address1, address2, city, state, country, zip), confirm,
then call the tool.

## Payment — `modify_pending_order_payment`
- The new payment method must be **different** from the current one, and only a
  single method may be chosen.
- If paying by gift card, it must hold enough balance to cover the order total.
- The original method is refunded immediately (gift card) or within 5–7 business
  days otherwise.

## Items — `modify_pending_order_items` (one-shot, irreversible)
This is the dangerous one. It can be called **once** and changes the status to
`pending (item modified)`, after which the order can no longer be modified or
cancelled. So:

1. **Collect every change first.** Remind the customer to confirm they have listed
   *all* items they want to change. Build the aligned `item_ids` / `new_item_ids`
   lists in one batch.
2. **Same product type only.** Each item may change only to a different available
   option of the **same product** (e.g. switch keyboard switch type) — never to a
   different product type.
3. **Compute the price difference deterministically.** Do not do the arithmetic in
   your head. Look up old and new prices, then run:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/price_delta.py" \
     --pairs '[[OLD_PRICE, NEW_PRICE], ...]' --gift-card-balance BALANCE
   ```

   Use its `direction` (charge/refund) and `gift_card_sufficient` to explain the
   outcome and to confirm a gift card can cover any charge.
4. **Confirm, then call once** with the matched lists and the payment method id.

## Guardrail

A deterministic PreToolUse hook re-checks that `item_ids` and `new_item_ids` are
equal length and that no item is "modified" to itself, and that order ids are
well-formed, before the tool runs. A deny is a hard stop.
