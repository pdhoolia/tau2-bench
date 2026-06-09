---
name: authenticate-user
description: Authenticate the retail customer's identity before doing anything else. Use at the very start of every conversation, and before any lookup or write — even if the user volunteers a user id. Locates the user id by email, or by first name + last name + zip code.
allowed-tools: "mcp__tau2-retail__find_user_id_by_email mcp__tau2-retail__find_user_id_by_name_zip mcp__tau2-retail__get_user_details"
---

# Authenticate the customer

Identity authentication is the mandatory first gate of every retail conversation.
You must establish the user id **yourself, via the tools** — never trust a user id
the customer simply states.

## Steps

1. **Prefer email.** Ask for the customer's email and call
   `find_user_id_by_email`. This is the default path.
2. **Fall back to name + zip.** If the user cannot remember their email (or it is
   not found), ask for first name, last name, and zip code, then call
   `find_user_id_by_name_zip`.
3. **Confirm and remember.** Once a user id is returned, that is the *only* user
   you may act for in this conversation.

## Rules

- Authenticate even when the user already provides their user id — verify it.
- You can help **only one user per conversation**. Politely deny any request that
  concerns a different user's profile, orders, or data.
- After authentication you may freely answer read-only questions about that user's
  own profile, orders, and the products they reference (e.g. help them find an
  order id).
- Do not invent information. Only state what the tools return.

Once authenticated, route the request to the matching procedure skill:
cancel-pending-order, modify-pending-order, return-delivered-order, or
exchange-delivered-order.
