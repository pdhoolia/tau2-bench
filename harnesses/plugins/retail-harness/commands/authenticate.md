---
description: Authenticate the retail customer before handling any request.
argument-hint: "[email or 'name, zip']"
---

Authenticate the customer for this retail session using the **authenticate-user**
skill. Identity must be established via the tools (by email, or by name + zip) —
never trust a stated user id.

Customer-provided identifier (if any): $ARGUMENTS

Once the user id is confirmed, state that authentication succeeded and ask how you
can help. Do not perform any read or write for the customer until this succeeds.
