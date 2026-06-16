---
description: Read-only audit of a proposed matter against intake policy, before opening it.
argument-hint: "[client_id and/or matter details]"
---

Run a read-only audit of the proposed intake for: $ARGUMENTS

Use the **intake-auditor** sub-agent to independently re-check, against the live
database, whether opening this matter would satisfy the firm's intake policy and
the LPUL: conflict check `clear`, client identity verified, responsible
practitioner holds a current practising certificate, the required costs agreement
is attached (and signed / full-disclosure above $3,000), and the fee arrangement is
permitted.

Summarize its APPROVE/REJECT verdict for the operator. Do not perform any write.
