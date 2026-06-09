---
description: Read-only audit of an order's current state against policy, before any write.
argument-hint: "[order_id]"
---

Run a read-only audit of order $ARGUMENTS for the authenticated customer.

Use the **policy-auditor** sub-agent to independently inspect the order and report
whether a contemplated cancel / modify / return / exchange would satisfy the retail
policy's eligibility predicates (ownership, status, item rules, payment/refund).
Summarize its APPROVE/REJECT verdict for the operator. Do not perform any write.
