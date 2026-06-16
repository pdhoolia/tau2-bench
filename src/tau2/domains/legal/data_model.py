from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from tau2.domains.legal.utils import LEGAL_DB_PATH
from tau2.environment.db import DB

# --- Enumerations (NSW / Legal Profession Uniform Law) -----------------------

# Practising Certificate status. Under the LPUL a practitioner may only act on a
# matter while holding a *current* practising certificate (PC).
PCStatus = Literal["current", "expired", "suspended"]
PCType = Literal["principal", "employee"]

ClientType = Literal["individual", "company"]

# A matter is "prospective" during intake and only becomes "open" once the
# intake checks pass. "declined" is used when a conflict (or other bar) prevents
# the firm from acting.
MatterStatus = Literal["prospective", "open", "declined", "closed"]

# Controlled vocabulary for the area of law. Kept as an enum so the agent
# selects a known token (and the database stays deterministic for grading).
# NOTE: "litigation" is deliberately absent — it is a dispute posture, not an
# area of law (a commercial/family/employment matter can each be litigious), so
# it does not belong in a mutually-exclusive area-of-law enum.
MatterType = Literal[
    "commercial",
    "family",
    "conveyancing",
    "estates",
    "employment",
]

# Permitted fee types. NOTE: contingency / percentage-of-recovery fees are
# *prohibited* under the LPUL and are deliberately absent from this list.
FeeType = Literal["time_based", "fixed", "conditional"]

ConflictStatus = Literal["clear", "conflict_found"]

# Costs-disclosure tier derived from the estimated total legal costs:
#   - "none":       below the lower disclosure threshold (< $750)
#   - "short_form": between the thresholds ($750 - $3,000) — disclosure required
#   - "full":       above the upper threshold (> $3,000) — written, signed
#                   costs agreement required
DisclosureTier = Literal["none", "short_form", "full"]


# --- Entities ----------------------------------------------------------------


class Practitioner(BaseModel):
    practitioner_id: str = Field(description="Unique identifier for the practitioner")
    name: str = Field(description="Practitioner's full name")
    pc_status: PCStatus = Field(
        description="Practising certificate status: 'current', 'expired', or 'suspended'"
    )
    pc_expiry: str = Field(
        description="Practising certificate expiry date (ISO YYYY-MM-DD). NSW PCs run on a 1 July - 30 June cycle."
    )
    pc_type: PCType = Field(
        description="Practising certificate type: 'principal' or 'employee'"
    )
    cpd_units: float = Field(
        description="Continuing Professional Development units recorded for the current CPD year (10 required)."
    )
    practice_areas: List[str] = Field(
        default_factory=list, description="Areas of law the practitioner works in."
    )


class Client(BaseModel):
    client_id: str = Field(description="Unique identifier for the client")
    name: str = Field(description="Client's full name or company name")
    client_type: ClientType = Field(description="'individual' or 'company'")
    email: str = Field(description="Client's email address")
    phone: str = Field(description="Client's phone number")
    identity_verified: bool = Field(
        default=False,
        description="Whether the client's identity has been verified (ID documents sighted).",
    )
    date_of_birth: Optional[str] = Field(
        default=None, description="Date of birth (ISO YYYY-MM-DD) for individuals."
    )
    abn: Optional[str] = Field(
        default=None, description="Australian Business Number for company clients."
    )
    address: Optional[str] = Field(default=None, description="Client's address.")


class ConflictCheck(BaseModel):
    conflict_check_id: str = Field(
        description="Unique identifier for the conflict check"
    )
    prospective_client_name: str = Field(
        description="Name of the prospective client the check was run for."
    )
    opposing_parties: List[str] = Field(
        default_factory=list, description="Opposing parties searched against."
    )
    matches: List[str] = Field(
        default_factory=list,
        description="Names that matched an existing client or an existing opposing party.",
    )
    status: ConflictStatus = Field(
        description="'clear' if no matches were found, otherwise 'conflict_found'."
    )
    performed_date: str = Field(
        description="Date the check was performed (ISO YYYY-MM-DD)."
    )


class CostsAgreement(BaseModel):
    costs_agreement_id: str = Field(
        description="Unique identifier for the costs agreement"
    )
    client_id: str = Field(description="Client the costs agreement is for.")
    fee_type: FeeType = Field(description="'time_based', 'fixed', or 'conditional'.")
    estimated_total: float = Field(
        description="Estimated total legal costs (AUD, excluding GST and disbursements)."
    )
    uplift_percentage: Optional[float] = Field(
        default=None,
        description="Uplift fee percentage for conditional ('no win, no fee') agreements. Capped at 25%.",
    )
    disclosure_tier: DisclosureTier = Field(
        description="Costs-disclosure tier derived from the estimated total."
    )
    signed: bool = Field(
        default=True, description="Whether the client has signed the costs agreement."
    )
    created_date: str = Field(
        description="Date the agreement was created (ISO YYYY-MM-DD)."
    )


class Matter(BaseModel):
    matter_id: str = Field(description="Unique identifier for the matter")
    client_id: str = Field(description="The client the matter is for.")
    responsible_practitioner_id: str = Field(
        description="Practitioner with day-to-day responsibility for the matter."
    )
    matter_type: MatterType = Field(
        description="Area of law: 'commercial', 'family', 'conveyancing', 'estates', or 'employment'."
    )
    description: Optional[str] = Field(
        default=None,
        description="Short description of the matter (free text, optional).",
    )
    opposing_parties: List[str] = Field(
        default_factory=list, description="Opposing parties on the matter."
    )
    estimated_costs: float = Field(description="Estimated total legal costs (AUD).")
    status: MatterStatus = Field(description="Matter status.")
    conflict_check_id: Optional[str] = Field(
        default=None, description="The conflict check that cleared this matter."
    )
    costs_agreement_id: Optional[str] = Field(
        default=None, description="The costs agreement attached to this matter."
    )
    opened_date: Optional[str] = Field(
        default=None, description="Date the matter was opened (ISO YYYY-MM-DD)."
    )


class LegalDB(DB):
    """Boutique law firm intake database (NSW, Legal Profession Uniform Law)."""

    practitioners: Dict[str, Practitioner] = Field(
        description="Dictionary of practitioners indexed by practitioner ID."
    )
    clients: Dict[str, Client] = Field(
        description="Dictionary of clients indexed by client ID."
    )
    conflict_checks: Dict[str, ConflictCheck] = Field(
        default_factory=dict,
        description="Dictionary of conflict checks indexed by conflict check ID.",
    )
    costs_agreements: Dict[str, CostsAgreement] = Field(
        default_factory=dict,
        description="Dictionary of costs agreements indexed by costs agreement ID.",
    )
    matters: Dict[str, Matter] = Field(
        description="Dictionary of matters indexed by matter ID."
    )

    def get_statistics(self) -> dict[str, Any]:
        return {
            "num_practitioners": len(self.practitioners),
            "num_clients": len(self.clients),
            "num_conflict_checks": len(self.conflict_checks),
            "num_costs_agreements": len(self.costs_agreements),
            "num_matters": len(self.matters),
        }


def get_db():
    return LegalDB.load(LEGAL_DB_PATH)
