---
name: client-and-identity
description: Create or reuse a client record and verify the client's identity. Use after the conflict check is clear and before opening a matter. Avoids duplicate clients by searching first, and ensures identity is verified (a matter cannot be opened for an unverified client).
allowed-tools: "mcp__tau2-legal__find_clients mcp__tau2-legal__get_client mcp__tau2-legal__create_client mcp__tau2-legal__verify_client_identity"
---

# Establish the client and verify identity

Pre-req: the conflict check for this matter has returned `clear`.

## Client record

1. **Search first to avoid duplicates.** Call `find_clients(name)` with the
   client's name (or part of it). If a matching client already exists, reuse that
   record — note its `client_id` and do **not** create a second one.
2. **Create only if new.** If there is no existing record, gather the details and
   call `create_client`:
   - `name`, `client_type` (`individual` or `company`), `email`, `phone`;
   - for an individual, `date_of_birth`; for a company, `abn`;
   - `address` if the client gave one.
   The record must reflect **exactly what the client supplied — no more, no less**:
   - **Include every detail the client did provide.** If they gave a date of birth,
     ABN or address, pass it. Do **not** drop a detail the client actually stated.
   - **Never invent a detail the client did not provide.** In particular, do not
     fabricate an `address` (or `date_of_birth` / `abn`); if it was not given, leave
     it null. Ask for any *required* detail you are missing rather than guessing.

## Verify identity

3. **Check current status.** For an existing client, call `get_client` and look at
   `identity_verified`. If it is already `true`, no action is needed.
4. **Verify once ID is sighted.** A matter **cannot** be opened for a client whose
   identity is not verified. Once the staff member confirms ID documents have been
   sighted, call `verify_client_identity(client_id)`.

## Rules

- One client per matter; reuse existing records rather than duplicating them.
- Do not mark identity verified unless the staff member confirms ID was sighted.
