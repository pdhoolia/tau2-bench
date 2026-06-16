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
