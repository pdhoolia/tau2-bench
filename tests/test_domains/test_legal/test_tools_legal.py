import pytest

from tau2.data_model.message import ToolCall
from tau2.domains.legal.environment import get_environment
from tau2.environment.environment import Environment


@pytest.fixture
def environment() -> Environment:
    # Loads the seed db.json from data/tau2/domains/legal/.
    return get_environment()


def call(environment: Environment, tool: str, **arguments):
    return environment.get_response(ToolCall(id="1", name=tool, arguments=arguments))


def test_solo_mode_not_supported():
    with pytest.raises(ValueError):
        get_environment(solo_mode=True)


def test_conflict_check_clear(environment: Environment):
    resp = call(
        environment,
        "run_conflict_check",
        prospective_client_name="Jane Wilson",
        opposing_parties=["Zenith Corp"],
    )
    assert not resp.error
    check = environment.tools.db.conflict_checks["cc_1"]
    assert check.status == "clear"
    assert check.matches == []


def test_conflict_when_prospective_is_existing_opposing_party(environment: Environment):
    # Greenfield Holdings Pty Ltd is the opposing party on matter_001.
    call(
        environment,
        "run_conflict_check",
        prospective_client_name="Greenfield Holdings Pty Ltd",
        opposing_parties=["Bluewater Pty Ltd"],
    )
    assert environment.tools.db.conflict_checks["cc_1"].status == "conflict_found"


def test_conflict_when_opposing_is_existing_client(environment: Environment):
    # John Smith (client_smith) is an existing client.
    call(
        environment,
        "run_conflict_check",
        prospective_client_name="Olivia Martin",
        opposing_parties=["John Smith"],
    )
    assert environment.tools.db.conflict_checks["cc_1"].status == "conflict_found"


def test_costs_agreement_disclosure_tiers(environment: Environment):
    call(
        environment,
        "create_costs_agreement",
        client_id="client_smith",
        fee_type="time_based",
        estimated_total=500,
    )
    call(
        environment,
        "create_costs_agreement",
        client_id="client_smith",
        fee_type="time_based",
        estimated_total=2000,
    )
    call(
        environment,
        "create_costs_agreement",
        client_id="client_smith",
        fee_type="time_based",
        estimated_total=8000,
    )
    cas = environment.tools.db.costs_agreements
    assert cas["ca_1"].disclosure_tier == "none"
    assert cas["ca_2"].disclosure_tier == "short_form"
    assert cas["ca_3"].disclosure_tier == "full"


def test_uplift_above_cap_rejected(environment: Environment):
    resp = call(
        environment,
        "create_costs_agreement",
        client_id="client_smith",
        fee_type="conditional",
        estimated_total=9000,
        uplift_percentage=40,
    )
    assert resp.error
    # 25% is accepted.
    resp = call(
        environment,
        "create_costs_agreement",
        client_id="client_smith",
        fee_type="conditional",
        estimated_total=9000,
        uplift_percentage=25,
    )
    assert not resp.error


def test_uplift_on_non_conditional_rejected(environment: Environment):
    resp = call(
        environment,
        "create_costs_agreement",
        client_id="client_smith",
        fee_type="time_based",
        estimated_total=9000,
        uplift_percentage=10,
    )
    assert resp.error


def test_open_matter_requires_verified_identity(environment: Environment):
    # client_taylor's identity is not verified in the seed data.
    cc = environment.get_response(
        ToolCall(
            id="1",
            name="run_conflict_check",
            arguments={
                "prospective_client_name": "Robert Taylor",
                "opposing_parties": [],
            },
        )
    )
    assert not cc.error
    resp = call(
        environment,
        "open_matter",
        client_id="client_taylor",
        responsible_practitioner_id="prac_johnson",
        matter_type="family",
        estimated_costs=500,
        conflict_check_id="cc_1",
    )
    assert resp.error


def test_open_matter_requires_current_pc(environment: Environment):
    call(
        environment,
        "run_conflict_check",
        prospective_client_name="x",
        opposing_parties=[],
    )
    # prac_white has an expired practising certificate.
    resp = call(
        environment,
        "open_matter",
        client_id="client_smith",
        responsible_practitioner_id="prac_white",
        matter_type="litigation",
        estimated_costs=500,
        conflict_check_id="cc_1",
    )
    assert resp.error


def test_open_matter_requires_clear_conflict_check(environment: Environment):
    # A conflict check that found a conflict cannot be used to open a matter.
    call(
        environment,
        "run_conflict_check",
        prospective_client_name="x",
        opposing_parties=["John Smith"],
    )
    assert environment.tools.db.conflict_checks["cc_1"].status == "conflict_found"
    resp = call(
        environment,
        "open_matter",
        client_id="client_smith",
        responsible_practitioner_id="prac_johnson",
        matter_type="litigation",
        estimated_costs=500,
        conflict_check_id="cc_1",
    )
    assert resp.error


def test_full_happy_path(environment: Environment):
    db = environment.tools.db
    call(
        environment,
        "run_conflict_check",
        prospective_client_name="Jane Wilson",
        opposing_parties=["Zenith Corp"],
    )
    call(
        environment,
        "create_client",
        name="Jane Wilson",
        client_type="individual",
        email="jane.wilson@example.com",
        phone="0400 000 111",
        date_of_birth="1988-07-07",
    )
    assert "client_005" in db.clients
    assert db.clients["client_005"].identity_verified is False
    call(environment, "verify_client_identity", client_id="client_005")
    assert db.clients["client_005"].identity_verified is True
    call(
        environment,
        "create_costs_agreement",
        client_id="client_005",
        fee_type="time_based",
        estimated_total=8000,
    )
    resp = call(
        environment,
        "open_matter",
        client_id="client_005",
        responsible_practitioner_id="prac_johnson",
        matter_type="commercial",
        estimated_costs=8000,
        conflict_check_id="cc_1",
        opposing_parties=["Zenith Corp"],
        costs_agreement_id="ca_1",
    )
    assert not resp.error
    matter = db.matters["matter_004"]
    assert matter.status == "open"
    assert matter.responsible_practitioner_id == "prac_johnson"


def test_open_matter_above_threshold_requires_costs_agreement(environment: Environment):
    call(
        environment,
        "run_conflict_check",
        prospective_client_name="Jane Wilson",
        opposing_parties=[],
    )
    call(
        environment,
        "create_client",
        name="Jane Wilson",
        client_type="individual",
        email="jane.wilson@example.com",
        phone="0400 000 111",
        date_of_birth="1988-07-07",
    )
    call(environment, "verify_client_identity", client_id="client_005")
    # $8,000 with no costs agreement -> must fail.
    resp = call(
        environment,
        "open_matter",
        client_id="client_005",
        responsible_practitioner_id="prac_johnson",
        matter_type="commercial",
        estimated_costs=8000,
        conflict_check_id="cc_1",
    )
    assert resp.error
