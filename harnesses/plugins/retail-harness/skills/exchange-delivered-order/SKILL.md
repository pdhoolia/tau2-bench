---
name: exchange-delivered-order
description: Exchange items in a delivered retail order for different options of the same products. Use when an authenticated customer wants to swap received items (e.g. a different size or color) rather than return them. Handles the one-shot caution, same-product-type rule, and price-difference handling.
allowed-tools: "mcp__tau2-retail__get_order_details mcp__tau2-retail__get_user_details mcp__tau2-retail__get_product_details mcp__tau2-retail__get_item_details mcp__tau2-retail__exchange_delivered_order_items"
---

# Exchange items in a delivered order

Pre-req: the customer is authenticated and the order is theirs.

## Steps

1. **Check status.** Call `get_order_details` and confirm `status == "delivered"`.
   Only delivered orders can be exchanged, and exchange/return can be done **once**
   per order.
2. **Collect every item first.** Remind the customer to confirm they have provided
   **all** items to exchange. Build aligned `item_ids` / `new_item_ids` lists in a
   single batch — this is a one-shot call.
3. **Same product type only.** Each item may be exchanged only for a different
   available option of the **same product** — never a different product type.
   Use `get_product_details` / `get_item_details` to confirm availability.
4. **Compute the price difference deterministically:**

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/price_delta.py" \
     --pairs '[[OLD_PRICE, NEW_PRICE], ...]' --gift-card-balance BALANCE
   ```

   The customer must provide a payment method to pay or receive the difference; if
   it is a gift card it must cover any charge (`gift_card_sufficient`).
5. **Confirm explicitly, then call once**:
   `exchange_delivered_order_items(order_id, item_ids, new_item_ids, payment_method_id)`.

## What the customer should be told

The status becomes `exchange requested` and they will receive an email about how to
return the original items. No new order needs to be placed.

## Guardrail

A deterministic PreToolUse hook re-checks that `item_ids` and `new_item_ids` are
equal length and that order ids are well-formed before the tool runs. A deny is a
hard stop.
