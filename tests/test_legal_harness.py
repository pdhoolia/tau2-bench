"""Tests for the legal-harness plugin scripts and the legal MCP server.

These cover the deterministic primitives the harness relies on, without needing a
live `claude` CLI: the costs-disclosure / fee calculator, the PreToolUse write
guardrail (exercised through its real stdin/stdout contract), and the legal MCP
server's tool registration.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN = _REPO_ROOT / "harnesses" / "plugins" / "legal-harness"
_COSTS = _PLUGIN / "scripts" / "costs_assessment.py"
_PRECHECK = _PLUGIN / "scripts" / "precheck_write.py"


# ---------------------------------------------------------------------------
# costs_assessment.py — computational determinism
# ---------------------------------------------------------------------------


def _run_costs(*args):
    proc = subprocess.run(
        [sys.executable, str(_COSTS), *args], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.parametrize(
    "total,tier,agreement,written",
    [
        (500, "none", False, False),
        (749.99, "none", False, False),
        (750, "short_form", True, False),
        (3000, "short_form", True, False),
        (3000.01, "full", True, True),
        (8000, "full", True, True),
    ],
)
def test_costs_disclosure_tiers(total, tier, agreement, written):
    out = _run_costs("--estimated-total", str(total))
    assert out["disclosure_tier"] == tier
    assert out["costs_agreement_required"] is agreement
    assert out["written_signed_agreement_required"] is written


def test_costs_conditional_uplift_valid():
    out = _run_costs(
        "--estimated-total", "8000", "--fee-type", "conditional", "--uplift", "20"
    )
    assert out["fee_permitted"] is True
    assert out["uplift_required"] is True
    assert out["uplift_valid"] is True


def test_costs_conditional_uplift_over_cap_invalid():
    out = _run_costs(
        "--estimated-total", "8000", "--fee-type", "conditional", "--uplift", "30"
    )
    assert out["uplift_valid"] is False


def test_costs_uplift_on_non_conditional_invalid():
    out = _run_costs(
        "--estimated-total", "8000", "--fee-type", "time_based", "--uplift", "10"
    )
    assert out["uplift_valid"] is False


def test_costs_contingency_fee_not_permitted():
    out = _run_costs("--estimated-total", "8000", "--fee-type", "contingency")
    assert out["fee_permitted"] is False


# ---------------------------------------------------------------------------
# precheck_write.py — verification determinism (PreToolUse guardrail)
# ---------------------------------------------------------------------------


def _run_precheck(tool_name, tool_input):
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    proc = subprocess.run(
        [sys.executable, str(_PRECHECK)], input=payload, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    if not out:
        return None  # allowed (silent exit 0)
    return json.loads(out)["hookSpecificOutput"]


def _is_deny(result):
    return result is not None and result["permissionDecision"] == "deny"


def test_precheck_allows_valid_conditional_agreement():
    result = _run_precheck(
        "mcp__tau2-legal__create_costs_agreement",
        {
            "client_id": "client_005",
            "fee_type": "conditional",
            "estimated_total": 8000,
            "uplift_percentage": 20,
        },
    )
    assert result is None


def test_precheck_denies_contingency_fee():
    result = _run_precheck(
        "mcp__tau2-legal__create_costs_agreement",
        {"client_id": "client_005", "fee_type": "contingency", "estimated_total": 8000},
    )
    assert _is_deny(result)
    assert "not permitted" in result["permissionDecisionReason"].lower()


def test_precheck_denies_uplift_over_cap():
    result = _run_precheck(
        "mcp__tau2-legal__create_costs_agreement",
        {
            "client_id": "c",
            "fee_type": "conditional",
            "estimated_total": 8000,
            "uplift_percentage": 40,
        },
    )
    assert _is_deny(result)


def test_precheck_denies_conditional_without_uplift():
    result = _run_precheck(
        "mcp__tau2-legal__create_costs_agreement",
        {"client_id": "c", "fee_type": "conditional", "estimated_total": 8000},
    )
    assert _is_deny(result)


def test_precheck_denies_uplift_on_non_conditional():
    result = _run_precheck(
        "mcp__tau2-legal__create_costs_agreement",
        {
            "client_id": "c",
            "fee_type": "fixed",
            "estimated_total": 8000,
            "uplift_percentage": 10,
        },
    )
    assert _is_deny(result)


def test_precheck_denies_open_matter_missing_costs_agreement():
    result = _run_precheck(
        "mcp__tau2-legal__open_matter",
        {
            "client_id": "client_005",
            "responsible_practitioner_id": "prac_johnson",
            "matter_type": "commercial",
            "estimated_costs": 8000,
            "conflict_check_id": "cc_1",
        },
    )
    assert _is_deny(result)


def test_precheck_allows_open_matter_with_agreement():
    result = _run_precheck(
        "mcp__tau2-legal__open_matter",
        {
            "client_id": "client_005",
            "responsible_practitioner_id": "prac_johnson",
            "matter_type": "commercial",
            "estimated_costs": 8000,
            "conflict_check_id": "cc_1",
            "costs_agreement_id": "ca_1",
        },
    )
    assert result is None


def test_precheck_allows_small_matter_without_agreement():
    result = _run_precheck(
        "mcp__tau2-legal__open_matter",
        {
            "client_id": "client_005",
            "responsible_practitioner_id": "prac_johnson",
            "matter_type": "conveyancing",
            "estimated_costs": 500,
            "conflict_check_id": "cc_1",
        },
    )
    assert result is None


def test_precheck_denies_blank_conflict_check():
    result = _run_precheck(
        "mcp__tau2-legal__run_conflict_check", {"prospective_client_name": "  "}
    )
    assert _is_deny(result)


# ---------------------------------------------------------------------------
# precheck_write.py — conversation-aware provenance check (create_client)
# ---------------------------------------------------------------------------


def _run_precheck_with_transcript(tool_name, tool_input, user_turns, tmp_path):
    """Run the precheck with a synthetic transcript of `user_turns` (user-role text).

    A cleared conflict-check result is seeded first so the conflict-check-first guard
    (which gates create_client) is satisfied and these tests exercise *provenance*.
    """
    transcript = tmp_path / "session.jsonl"
    cleared_check = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "content": json.dumps(
                        {"conflict_check_id": "cc_1", "status": "clear"}
                    ),
                }
            ],
        },
    }
    with transcript.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(cleared_check) + "\n")
        for text in user_turns:
            fh.write(
                json.dumps(
                    {"type": "user", "message": {"role": "user", "content": text}}
                )
                + "\n"
            )
    payload = json.dumps(
        {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "transcript_path": str(transcript),
        }
    )
    proc = subprocess.run(
        [sys.executable, str(_PRECHECK)], input=payload, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    return json.loads(out)["hookSpecificOutput"] if out else None


def test_precheck_denies_fabricated_address(tmp_path):
    # Sydney-firm transcript that never mentions the street: the city/postcode
    # tokens must not lend a fabricated street false provenance.
    result = _run_precheck_with_transcript(
        "mcp__tau2-legal__create_client",
        {"name": "Jane Doe", "address": "42 Maple Street, Sydney NSW 2000"},
        ["Hi, I'd like to open a matter. I'm based in Sydney 2000."],
        tmp_path,
    )
    assert _is_deny(result)
    assert "provenance" in result["permissionDecisionReason"].lower()
    # The deny message must NOT echo the rejected value (else it pollutes the
    # transcript corpus and a retry copying it back would gain false provenance).
    assert "Maple" not in result["permissionDecisionReason"]


def test_precheck_allows_client_provided_address_with_appended_context(tmp_path):
    # Client stated the distinctive street; model appended city/state/postcode.
    result = _run_precheck_with_transcript(
        "mcp__tau2-legal__create_client",
        {"name": "Jane Doe", "address": "42 Maple Street, Sydney NSW 2000"},
        ["My address is 42 Maple Street."],
        tmp_path,
    )
    assert result is None


def test_precheck_allows_address_when_no_transcript():
    # No provenance source available -> fail open (do not block the run).
    result = _run_precheck(
        "mcp__tau2-legal__create_client",
        {"name": "Jane Doe", "address": "42 Maple Street, Sydney NSW 2000"},
    )
    assert result is None


def test_precheck_denies_fabricated_dob(tmp_path):
    result = _run_precheck_with_transcript(
        "mcp__tau2-legal__create_client",
        {"name": "Jane Doe", "date_of_birth": "1985-03-15"},
        ["Hi, I'd like to open a conveyancing matter please."],
        tmp_path,
    )
    assert _is_deny(result)


def test_precheck_allows_client_provided_dob(tmp_path):
    result = _run_precheck_with_transcript(
        "mcp__tau2-legal__create_client",
        {"name": "Jane Doe", "date_of_birth": "1985-03-15"},
        ["My date of birth is 15 March 1985."],
        tmp_path,
    )
    assert result is None


# ---------------------------------------------------------------------------
# precheck_write.py — conflict-check-first guard (create_client / open_matter)
# ---------------------------------------------------------------------------


def _run_precheck_with_records(tool_name, tool_input, records, tmp_path):
    """Run the precheck against a transcript built from raw jsonl records."""
    transcript = tmp_path / "t.jsonl"
    with transcript.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    payload = json.dumps(
        {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "transcript_path": str(transcript),
        }
    )
    proc = subprocess.run(
        [sys.executable, str(_PRECHECK)], input=payload, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    return json.loads(out)["hookSpecificOutput"] if out else None


def _conflict_result_record(cid="cc_1", status="clear"):
    """A transcript user line carrying a run_conflict_check tool_result."""
    result = {
        "conflict_check_id": cid,
        "prospective_client_name": "Sophie Hall",
        "opposing_parties": ["Northbridge Pty Ltd"],
        "matches": [] if status == "clear" else [{"name": "Northbridge Pty Ltd"}],
        "status": status,
        "performed_date": "2026-06-15",
    }
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "content": json.dumps(result)}],
        },
    }


_NEW_CLIENT = {
    "name": "Sophie Hall",
    "client_type": "individual",
    "email": "sophie.hall@example.com",
    "phone": "0422 888 999",
}


def test_conflict_first_denies_create_client_without_clear_check(tmp_path):
    rec = {"type": "user", "message": {"role": "user", "content": "Open a matter."}}
    result = _run_precheck_with_records(
        "mcp__tau2-legal__create_client", _NEW_CLIENT, [rec], tmp_path
    )
    assert _is_deny(result)
    assert "conflict" in result["permissionDecisionReason"].lower()


def test_conflict_first_allows_create_client_after_clear_check(tmp_path):
    result = _run_precheck_with_records(
        "mcp__tau2-legal__create_client",
        _NEW_CLIENT,
        [_conflict_result_record(status="clear")],
        tmp_path,
    )
    assert result is None


def test_conflict_first_denies_create_client_when_conflict_found(tmp_path):
    # A conflict_found result is not 'clear' -> still gated (agent must escalate).
    result = _run_precheck_with_records(
        "mcp__tau2-legal__create_client",
        _NEW_CLIENT,
        [_conflict_result_record(status="conflict_found")],
        tmp_path,
    )
    assert _is_deny(result)


def test_conflict_first_denies_open_matter_without_matching_clear_check(tmp_path):
    result = _run_precheck_with_records(
        "mcp__tau2-legal__open_matter",
        {
            "client_id": "client_005",
            "responsible_practitioner_id": "prac_johnson",
            "matter_type": "conveyancing",
            "estimated_costs": 500,
            "conflict_check_id": "cc_2",  # not the cleared cc_1
        },
        [_conflict_result_record(cid="cc_1", status="clear")],
        tmp_path,
    )
    assert _is_deny(result)


def test_conflict_first_allows_open_matter_with_matching_clear_check(tmp_path):
    result = _run_precheck_with_records(
        "mcp__tau2-legal__open_matter",
        {
            "client_id": "client_005",
            "responsible_practitioner_id": "prac_johnson",
            "matter_type": "conveyancing",
            "estimated_costs": 500,
            "conflict_check_id": "cc_1",
        },
        [_conflict_result_record(cid="cc_1", status="clear")],
        tmp_path,
    )
    assert result is None


def test_conflict_first_fails_open_without_transcript():
    # No transcript -> cannot judge -> do not block (open_matter's own arg checks
    # and the tool still apply).
    result = _run_precheck(
        "mcp__tau2-legal__open_matter",
        {
            "client_id": "client_005",
            "responsible_practitioner_id": "prac_johnson",
            "matter_type": "conveyancing",
            "estimated_costs": 500,
            "conflict_check_id": "cc_1",
        },
    )
    assert result is None


def test_precheck_allows_dob_stated_in_words(tmp_path):
    # Regression: an ISO date_of_birth must be recognised as provenanced when the
    # client stated it in word form ("9th of April 1984"); the zero-padded '04'/'09'
    # never appear as literal tokens, so a plain token match would false-deny.
    result = _run_precheck_with_transcript(
        "mcp__tau2-legal__create_client",
        {"name": "Sophie Hall", "date_of_birth": "1984-04-09"},
        ["Her date of birth is 9th of April 1984."],
        tmp_path,
    )
    assert result is None


# ---------------------------------------------------------------------------
# legal MCP server — tool registration
# ---------------------------------------------------------------------------


def test_legal_mcp_server_registers_all_tools():
    from tau2.mcp.legal_server import create_legal_mcp_server

    mcp = create_legal_mcp_server(name="tau2-legal-test")
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert {
        "run_conflict_check",
        "create_client",
        "verify_client_identity",
        "create_costs_agreement",
        "open_matter",
    } <= names
    assert len(names) == 13
