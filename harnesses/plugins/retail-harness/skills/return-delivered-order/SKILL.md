---
name: return-delivered-order
description: Return items from a delivered retail order. Use when an authenticated customer wants to return (not exchange) items they have already received. Handles the delivered-status check, allowed refund destinations, and explicit confirmation.
allowed-tools: "mcp__tau2-retail__get_order_details mcp__tau2-retail__get_user_details mcp__tau2-retail__return_delivered_order_items"
---

# Return items from a delivered order

Pre-req: the customer is authenticated and the order is theirs.

## Steps

1. **Check status.** Call `get_order_details` and confirm `status == "delivered"`.
   Only delivered orders can be returned.
2. **Collect the items.** Confirm the order id and the exact list of item ids to
   return (duplicates allowed if the order has duplicates).
3. **Choose the refund destination.** The refund must go to **either** the
   original payment method **or** an existing gift card — nothing else. Ask which.
4. **Confirm explicitly**, then call
   `return_delivered_order_items(order_id, item_ids, payment_method_id)`.

## What the customer should be told

The order status becomes `return requested` and the customer will receive an email
explaining how and where to return the items.

## Note

Return/exchange on a delivered order can be done **once** per order. If the
customer instead wants different options of the same products, use
exchange-delivered-order rather than returning.
