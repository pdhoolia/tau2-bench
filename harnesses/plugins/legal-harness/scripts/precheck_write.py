#!/usr/bin/env python3
"""PreToolUse guardrail for legal-intake WRITE tools.

Verification determinism (see "Governing the Determinism Spectrum in Legal
Practice"): the intake policy says the assistant "must" follow the steps and the
fee rules, but a confident, wrong tool call would otherwise slip straight through.
This hook moves the must-hold invariants into a room the model cannot enter. The
harness runtime invokes it on every legal MCP write, before the call reaches the
tool. A "deny" decision blocks the call and feeds the reason back to the model.

Scope (Phase 1): this hook enforces invariants decidable from the *tool arguments
alone* -- no live DB read required, so it is fully deterministic and order-of-
operations independent:

  * create_costs_agreement
      - fee_type in {time_based, fixed, conditional} (contingency/percentage
        fees are prohibited under the LPUL);
      - a conditional agreement requires an uplift > 0 and <= 25%;
      - an uplift may only be set on a conditional agreement.
  * open_matter
      - if estimated_costs >= $750, a costs_agreement_id must be attached.
  * run_conflict_check
      - a non-empty prospective_client_name (the check is the mandatory first
        step and is meaningless without a name).

Invariants that require live state -- conflict check actually returned 'clear',
client identity verified, responsible practitioner holds a CURRENT practising
certificate, and (above $3,000) the attached agreement is full-disclosure and
signed -- are deferred to the `intake-auditor` sub-agent, which reads the live DB.
They are documented in the plugin README.

The hook reads the PreToolUse payload as JSON on stdin and, on a violation, prints
a PreToolUse-specific output that denies the call. On success it exits 0 silently,
leaving the decision to normal permission flow.
"""

import json
import os
import re
import sys


def _debug(record):
    """Append a JSON diagnostic line to ``$TAU2_HOOK_DEBUG`` if that env var is set.

    Temporary instrumentation (gated, no-op unless the env var points at a file) used
    to verify what a PreToolUse hook actually sees in a live `claude -p` harness run —
    notably whether the in-flight user turn is flushed to ``transcript_path`` before the
    hook fires. Safe to leave in (silent by default) or remove.
    """
    path = os.environ.get("TAU2_HOOK_DEBUG")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass


PERMITTED_FEE_TYPES = {"time_based", "fixed", "conditional"}
COSTS_DISCLOSURE_LOWER_THRESHOLD = 750.0
MAX_UPLIFT_PERCENTAGE = 25.0

# Provenance check (Phase 2 — conversation-aware): free-text identity fields the
# model tends to fill speculatively. A value persisted here must trace to what the
# client/staff said or to a prior tool result; otherwise it is fabrication. Enum /
# controlled-vocabulary fields (client_type, matter_type, fee_type) and IDs are
# deliberately excluded — they are derived, not free text, and the tool validates them.
PROVENANCE_FIELDS = {
    "create_client": ["address", "date_of_birth", "abn"],
}
# Generic words that carry no provenance signal on their own (so an invented
# address isn't "supported" just because it contains the word "street" or "NSW").
GENERIC_TOKENS = {
    "street",
    "st",
    "road",
    "rd",
    "avenue",
    "ave",
    "drive",
    "dr",
    "lane",
    "ln",
    "court",
    "ct",
    "place",
    "pl",
    "way",
    "close",
    "crescent",
    "cres",
    "parade",
    "nsw",
    "act",
    "qld",
    "vic",
    "wa",
    "sa",
    "tas",
    "nt",
    "australia",
    "level",
    "unit",
    "suite",
    "apt",
    "po",
    "box",
    "pty",
    "ltd",
    "the",
    "and",
    "of",
}
# City / locality names carry no provenance signal *for an address*: they appear in
# any same-region transcript regardless of the street, so a fabricated street can
# borrow their match. The distinctive part of an address is the street number +
# street name, so these (and 4-digit postcodes; see _has_provenance) are stripped
# before address matching. NOT applied to date_of_birth / abn, where numbers matter.
LOCALITY_TOKENS = {
    "sydney",
    "melbourne",
    "brisbane",
    "perth",
    "adelaide",
    "canberra",
    "newcastle",
    "wollongong",
    "parramatta",
    "darwin",
    "hobart",
    "geelong",
    "townsville",
    "cairns",
    "gosford",
    "penrith",
    "bondi",
    "manly",
    "chatswood",
}


def _tool_suffix(tool_name):
    """Return the bare tool name, stripping any 'mcp__<server>__' prefix."""
    return tool_name.rsplit("__", 1)[-1] if tool_name else tool_name


def _deny(reason):
    """Emit a PreToolUse deny decision and exit without blocking the run."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def _check_costs_agreement(args):
    fee_type = args.get("fee_type")
    if fee_type is not None and fee_type not in PERMITTED_FEE_TYPES:
        _deny(
            f"Fee type {fee_type!r} is not permitted. The LPUL allows only "
            "'time_based', 'fixed', or 'conditional' fees; contingency / "
            "percentage-of-recovery fees are prohibited. Offer a conditional "
            "('no win, no fee') agreement with an uplift of up to 25% instead."
        )

    uplift = args.get("uplift_percentage")
    if fee_type == "conditional":
        if uplift is None:
            _deny(
                "A conditional costs agreement requires an uplift_percentage "
                "(greater than 0 and no more than 25%). Confirm the uplift with "
                "the client before creating the agreement."
            )
        try:
            up = float(uplift)
        except (TypeError, ValueError):
            _deny(f"uplift_percentage {uplift!r} must be a number between 0 and 25.")
        if up <= 0 or up > MAX_UPLIFT_PERCENTAGE:
            _deny(
                f"Uplift of {up}% is invalid. The uplift on a conditional costs "
                f"agreement must be greater than 0 and no more than "
                f"{MAX_UPLIFT_PERCENTAGE}% under the LPUL."
            )
    elif uplift is not None:
        _deny(
            "An uplift fee can only be set on a 'conditional' costs agreement, "
            f"not on a {fee_type!r} one. Remove the uplift_percentage."
        )


def _check_open_matter(args):
    estimated = args.get("estimated_costs")
    try:
        est = float(estimated) if estimated is not None else None
    except (TypeError, ValueError):
        est = None
    if (
        est is not None
        and est >= COSTS_DISCLOSURE_LOWER_THRESHOLD
        and not args.get("costs_agreement_id")
    ):
        _deny(
            f"Estimated costs of ${est:,.0f} are at or above the $750 disclosure "
            "threshold, so a costs agreement must be created and attached "
            "(costs_agreement_id) before the matter can be opened."
        )


def _check_conflict_check(args):
    name = (args.get("prospective_client_name") or "").strip()
    if not name:
        _deny(
            "run_conflict_check needs the prospective client's name. The conflict "
            "check is the mandatory first intake step and cannot be run blank."
        )


# Conflict-check-first guard (Phase 2 — transcript-based). Policy: the conflict
# check is the mandatory first intake step; no client may be created and no matter
# opened until a conflict check has been run for this prospective client and come
# back 'clear'. The open_matter TOOL already enforces a cleared conflict_check_id,
# but create_client does not — so this guard moves "conflict check first" out of the
# model's reach for the earliest write. It reads the live transcript for a prior
# conflict-check tool result with status 'clear'.
CONFLICT_GATED_TOOLS = {"create_client", "open_matter"}
_CC_ID_RE = re.compile(r'"conflict_check_id"\s*:\s*"([^"]+)"')
_CC_CLEAR_RE = re.compile(r'"status"\s*:\s*"clear"')


def _clear_conflict_ids_from_text(text):
    """Return the set of cleared conflict_check_ids found in one tool-result text."""
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        obj = None
    if isinstance(obj, dict):
        if obj.get("conflict_check_id") and obj.get("status") == "clear":
            return {obj["conflict_check_id"]}
        return set()
    # Fallback: a single conflict-check result blob carrying both signals.
    if _CC_CLEAR_RE.search(text):
        m = _CC_ID_RE.search(text)
        if m:
            return {m.group(1)}
    return set()


def _result_block_texts(message):
    """Yield the raw text of each tool_result block in a transcript message."""
    if not isinstance(message, dict):
        return
    content = message.get("content")
    blocks = content if isinstance(content, list) else [content]
    for block in blocks:
        if isinstance(block, str):
            yield block
        elif isinstance(block, dict) and block.get("type") == "tool_result":
            inner = block.get("content")
            if isinstance(inner, str):
                yield inner
            elif isinstance(inner, list):
                yield " ".join(x.get("text", "") for x in inner if isinstance(x, dict))


def _load_clear_conflict_checks(transcript_path):
    """Set of conflict_check_ids that returned 'clear' in the transcript.

    Returns ``None`` if the transcript is unavailable/unreadable (cannot judge ->
    the caller fails open), distinct from an empty set (readable, but no cleared
    conflict check found -> enforce).
    """
    if not transcript_path:
        return None
    try:
        ids = set()
        with open(transcript_path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if rec.get("type") != "user":
                    continue
                for text in _result_block_texts(rec.get("message", {})):
                    if text:
                        ids |= _clear_conflict_ids_from_text(text)
        return ids
    except OSError:
        return None


def _check_conflict_first(tool, args, transcript_path):
    """Deny create_client / open_matter until a 'clear' conflict check precedes it."""
    cleared = _load_clear_conflict_checks(transcript_path)
    if cleared is None:
        _debug({"event": "conflict_skip", "reason": "no_transcript", "tool": tool})
        return  # cannot read transcript -> fail open
    _debug({"event": "conflict_check", "tool": tool, "cleared_ids": sorted(cleared)})
    if tool == "open_matter":
        cid = args.get("conflict_check_id")
        if cid and cid in cleared:
            return
        detail = (
            f"The attached conflict check {cid!r} did not return 'clear' in this "
            "conversation. "
            if cid
            else "No cleared conflict check is attached. "
        )
        _deny(
            "A matter cannot be opened until run_conflict_check has been run for this "
            "client and returned 'clear'. " + detail + "Run "
            "run_conflict_check(prospective_client_name, opposing_parties) first — if "
            "you do not yet have the client's full name and every opposing party, ask "
            "the user for them — then open the matter with the returned "
            "conflict_check_id. If the check returns conflict_found, do not proceed: "
            "escalate with transfer_to_human."
        )
    else:  # create_client
        if cleared:
            return
        _deny(
            "Run the conflict check before creating a client record: it is the "
            "mandatory first intake step and no client may be created until it has "
            "returned 'clear'. Call run_conflict_check(prospective_client_name, "
            "opposing_parties) first — if you do not yet have the client's full name "
            "and every opposing party, ask the user for them — then create the client. "
            "If the check returns conflict_found, do not proceed: escalate with "
            "transfer_to_human."
        )


def _normalize(text):
    """Lowercase and split on non-alphanumeric runs -> a set of tokens."""
    return set(re.sub(r"[^a-z0-9]+", " ", str(text).lower()).split())


def _message_text(message):
    """Flatten a transcript message's content (string or content-block list)."""
    if isinstance(message, str):
        return message
    if not isinstance(message, dict):
        return ""
    content = message.get("content", message)
    if isinstance(content, str):
        return content
    parts = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                inner = block.get("content")  # e.g. tool_result content
                if isinstance(inner, str):
                    parts.append(inner)
                elif isinstance(inner, list):
                    for sub in inner:
                        if isinstance(sub, dict) and isinstance(sub.get("text"), str):
                            parts.append(sub["text"])
    return " ".join(parts)


def _load_provenance_tokens(transcript_path):
    """Token set of everything the *user* side said + every tool result.

    Provenance = what the client/staff stated and what prior tools returned. We
    read only `user`-role transcript lines (which carry both the user turns and
    the tool_result blocks); the assistant's own narration is NOT provenance —
    that is precisely where a fabrication would originate. Returns an empty set
    if the transcript is unavailable, in which case the check is skipped (fail-open).
    """
    if not transcript_path:
        return set()
    try:
        tokens = set()
        with open(transcript_path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if rec.get("type") != "user":
                    continue
                tokens |= _normalize(_message_text(rec.get("message", {})))
        return tokens
    except OSError:
        return set()


def _significant_tokens(value, *, drop_tokens=frozenset(), drop_postcodes=False):
    """Return ``(all_tokens, distinctive_tokens)`` for a value.

    Distinctive = tokens with provenance signal: drop short tokens, generic words
    (street types / state codes), `drop_tokens` (e.g. city names), and — when
    `drop_postcodes` — 4-digit postcodes. Single-sourced so the provenance decision
    and the debug log can never disagree.
    """
    value_tokens = _normalize(value)
    significant = {
        t
        for t in value_tokens
        if len(t) >= 2
        and t not in GENERIC_TOKENS
        and t not in drop_tokens
        and not (drop_postcodes and t.isdigit() and len(t) == 4)
    }
    return value_tokens, significant


def _has_provenance(
    value,
    corpus_tokens,
    *,
    drop_tokens=frozenset(),
    drop_postcodes=False,
    require_all=False,
):
    """True if `value` is empty/default, or its distinctive tokens are supported.

    `drop_tokens` and `drop_postcodes` remove contextual tokens that carry no
    provenance signal (city/locality names, 4-digit postcodes) so only the
    *distinctive* part of the value is matched against the corpus. `require_all`
    demands every distinctive token be present — used for addresses, where the
    street number + name must all trace to what the client said (the model is free
    to append city/state/postcode, which we have dropped). Otherwise a >= half-the-
    tokens match suffices (used for date_of_birth / abn).
    """
    value_tokens, significant = _significant_tokens(
        value, drop_tokens=drop_tokens, drop_postcodes=drop_postcodes
    )
    if not value_tokens:
        return True
    if not significant:
        # All-contextual value (e.g. "PO Box", "Sydney NSW 2000"): require any
        # original token to be present.
        return bool(value_tokens & corpus_tokens)
    present = len(significant & corpus_tokens)
    if require_all:
        # Every distinctive token must be supported (no false provenance from a
        # single coincidental match).
        return present == len(significant)
    # Supported if at least half the distinctive tokens appear in the corpus.
    return present * 2 >= len(significant)


_MONTHS = {
    1: "january",
    2: "february",
    3: "march",
    4: "april",
    5: "may",
    6: "june",
    7: "july",
    8: "august",
    9: "september",
    10: "october",
    11: "november",
    12: "december",
}


def _has_dob_provenance(value, corpus_tokens):
    """Date-aware provenance for an ISO ``date_of_birth`` (YYYY-MM-DD).

    A real DOB the client stated appears in many surface forms ("9th of April
    1984", "9 April 1984", "09/04/1984"); token-matching the ISO string alone
    false-denies these (the zero-padded '04'/'09' never appear in prose, so only
    the year matches → below threshold). So we require the YEAR, plus a month form
    (number or name) and a day form (number, with or without an ordinal suffix) to
    be present in the corpus. Non-ISO values fall back to the lenient token check.
    """
    m = re.match(r"\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*$", str(value))
    if not m:
        return _has_provenance(value, corpus_tokens)
    year, mon, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mon <= 12 and 1 <= day <= 31):
        return _has_provenance(value, corpus_tokens)
    if str(year) not in corpus_tokens:
        return False
    month_forms = {f"{mon:02d}", str(mon), _MONTHS[mon], _MONTHS[mon][:3]}
    day_forms = {f"{day:02d}", str(day)} | {
        f"{day}{suffix}" for suffix in ("st", "nd", "rd", "th")
    }
    return bool(month_forms & corpus_tokens) and bool(day_forms & corpus_tokens)


def _provenance_opts(field):
    """Matching options for a field's provenance check (single source for check+debug)."""
    if field == "address":
        # Strip city/postcode context and require the distinctive street tokens.
        return {
            "drop_tokens": LOCALITY_TOKENS,
            "drop_postcodes": True,
            "require_all": True,
        }
    return {}


def _check_provenance(tool, args, corpus_tokens):
    """Deny free-text identity fields the model invented (no conversational source)."""
    if not corpus_tokens:
        _debug({"event": "provenance_skip", "reason": "empty_corpus", "tool": tool})
        return  # no transcript -> cannot judge provenance; fail open
    for field in PROVENANCE_FIELDS.get(tool, []):
        value = args.get(field)
        if value in (None, "", [], {}):
            continue
        opts = _provenance_opts(field)
        if field == "date_of_birth":
            supported = _has_dob_provenance(value, corpus_tokens)
        else:
            supported = _has_provenance(value, corpus_tokens, **opts)
        if os.environ.get("TAU2_HOOK_DEBUG"):
            _, sig = _significant_tokens(
                value,
                drop_tokens=opts.get("drop_tokens", frozenset()),
                drop_postcodes=opts.get("drop_postcodes", False),
            )
            _debug(
                {
                    "event": "provenance_check",
                    "tool": tool,
                    "field": field,
                    "value": value,
                    "significant": sorted(sig),
                    "present": sorted(sig & corpus_tokens),
                    "absent": sorted(sig - corpus_tokens),
                    "supported": supported,
                }
            )
        if not supported:
            _deny(
                f"The {field} you supplied for {tool} has no provenance: it does not "
                "trace to anything the client or staff stated, or to any prior tool "
                "result. Never invent client details, and never copy a value out of a "
                f"guardrail/deny message — omit {field} (leave it null) unless the "
                "client actually provided it."
            )


def check(tool, args, corpus_tokens=None):
    """Apply the deterministic, argument-level invariants for `tool`."""
    if tool == "create_costs_agreement":
        _check_costs_agreement(args)
    elif tool == "open_matter":
        _check_open_matter(args)
    elif tool == "run_conflict_check":
        _check_conflict_check(args)
    _check_provenance(tool, args, corpus_tokens or set())


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Malformed payload: do not block the run on a guardrail parsing error.
        sys.exit(0)

    tool = _tool_suffix(payload.get("tool_name", ""))
    args = payload.get("tool_input") or {}
    if not isinstance(args, dict):
        sys.exit(0)

    transcript_path = payload.get("transcript_path")
    if tool in CONFLICT_GATED_TOOLS:
        _check_conflict_first(tool, args, transcript_path)
    corpus_tokens = (
        _load_provenance_tokens(transcript_path) if tool in PROVENANCE_FIELDS else set()
    )
    if os.environ.get("TAU2_HOOK_DEBUG"):
        tp = payload.get("transcript_path")
        exists = bool(tp) and os.path.exists(tp)
        _debug(
            {
                "event": "invoke",
                "tool": tool,
                "payload_keys": sorted(payload.keys()),
                "transcript_path": tp,
                "transcript_exists": exists,
                "transcript_size": (os.path.getsize(tp) if exists else None),
                "corpus_size": len(corpus_tokens),
            }
        )
    check(tool, args, corpus_tokens)
    sys.exit(0)


if __name__ == "__main__":
    main()
