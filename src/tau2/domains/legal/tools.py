from typing import List, Optional

from tau2.domains.legal.data_model import (
    Client,
    ClientType,
    ConflictCheck,
    CostsAgreement,
    DisclosureTier,
    FeeType,
    LegalDB,
    Matter,
    MatterType,
    Practitioner,
)
from tau2.domains.legal.utils import (
    COSTS_DISCLOSURE_LOWER_THRESHOLD,
    COSTS_DISCLOSURE_UPPER_THRESHOLD,
    LEGAL_CURRENT_DATE,
    MAX_UPLIFT_PERCENTAGE,
)
from tau2.environment.toolkit import ToolKitBase, ToolType, is_tool


class LegalTools(ToolKitBase):
    """Client-intake tools for a boutique NSW law firm (Legal Profession Uniform Law)."""

    db: LegalDB

    def __init__(self, db: LegalDB) -> None:
        super().__init__(db)

    # --- Internal helpers (not tools) ---------------------------------------

    def _get_client(self, client_id: str) -> Client:
        if client_id not in self.db.clients:
            raise ValueError(f"Client {client_id} not found")
        return self.db.clients[client_id]

    def _get_practitioner(self, practitioner_id: str) -> Practitioner:
        if practitioner_id not in self.db.practitioners:
            raise ValueError(f"Practitioner {practitioner_id} not found")
        return self.db.practitioners[practitioner_id]

    def _get_conflict_check(self, conflict_check_id: str) -> ConflictCheck:
        if conflict_check_id not in self.db.conflict_checks:
            raise ValueError(f"Conflict check {conflict_check_id} not found")
        return self.db.conflict_checks[conflict_check_id]

    def _get_costs_agreement(self, costs_agreement_id: str) -> CostsAgreement:
        if costs_agreement_id not in self.db.costs_agreements:
            raise ValueError(f"Costs agreement {costs_agreement_id} not found")
        return self.db.costs_agreements[costs_agreement_id]

    @staticmethod
    def _disclosure_tier(estimated_total: float) -> DisclosureTier:
        if estimated_total > COSTS_DISCLOSURE_UPPER_THRESHOLD:
            return "full"
        if estimated_total >= COSTS_DISCLOSURE_LOWER_THRESHOLD:
            return "short_form"
        return "none"

    # --- READ tools ----------------------------------------------------------

    @is_tool(ToolType.READ)
    def list_practitioners(self) -> list[Practitioner]:
        """
        List all practitioners at the firm, including their practising certificate status.
        """
        return list(self.db.practitioners.values())

    @is_tool(ToolType.READ)
    def get_practitioner(self, practitioner_id: str) -> Practitioner:
        """
        Get the details of a practitioner, including practising certificate status and expiry.

        Args:
            practitioner_id: The practitioner ID, such as 'prac_johnson'.

        Returns:
            The practitioner details.

        Raises:
            ValueError: If the practitioner is not found.
        """
        return self._get_practitioner(practitioner_id)

    @is_tool(ToolType.READ)
    def get_client(self, client_id: str) -> Client:
        """
        Get the details of an existing client.

        Args:
            client_id: The client ID, such as 'client_smith'.

        Returns:
            The client details.

        Raises:
            ValueError: If the client is not found.
        """
        return self._get_client(client_id)

    @is_tool(ToolType.READ)
    def find_clients(self, name: str) -> list[Client]:
        """
        Find existing clients whose name contains the given text (case-insensitive).
        Use this before creating a new client to avoid duplicates.

        Args:
            name: Full or partial client name to search for.

        Returns:
            A list of matching clients (may be empty).
        """
        needle = name.strip().lower()
        return [
            client
            for client in self.db.clients.values()
            if needle in client.name.lower()
        ]

    @is_tool(ToolType.READ)
    def get_matter(self, matter_id: str) -> Matter:
        """
        Get the details of a matter.

        Args:
            matter_id: The matter ID, such as 'matter_001'.

        Returns:
            The matter details.

        Raises:
            ValueError: If the matter is not found.
        """
        if matter_id not in self.db.matters:
            raise ValueError(f"Matter {matter_id} not found")
        return self.db.matters[matter_id]

    @is_tool(ToolType.READ)
    def get_conflict_check(self, conflict_check_id: str) -> ConflictCheck:
        """
        Get the details of a previously run conflict check.

        Args:
            conflict_check_id: The conflict check ID, such as 'cc_1'.

        Returns:
            The conflict check details.

        Raises:
            ValueError: If the conflict check is not found.
        """
        return self._get_conflict_check(conflict_check_id)

    @is_tool(ToolType.READ)
    def get_costs_agreement(self, costs_agreement_id: str) -> CostsAgreement:
        """
        Get the details of a costs agreement.

        Args:
            costs_agreement_id: The costs agreement ID, such as 'ca_1'.

        Returns:
            The costs agreement details.

        Raises:
            ValueError: If the costs agreement is not found.
        """
        return self._get_costs_agreement(costs_agreement_id)

    # --- WRITE tools ---------------------------------------------------------

    @is_tool(ToolType.WRITE)
    def run_conflict_check(
        self,
        prospective_client_name: str,
        opposing_parties: Optional[List[str]] = None,
    ) -> ConflictCheck:
        """
        Run a conflict-of-interest check for a prospective client and record the result.
        This MUST be run and come back clear before a matter is opened.

        A conflict is flagged when:
        - the prospective client matches an existing opposing party (the firm acts against them), or
        - an opposing party matches an existing client (the firm would act against its own client), or
        - an opposing party matches an existing opposing party on another matter.

        Args:
            prospective_client_name: The prospective client's full name.
            opposing_parties: Names of the opposing parties for the proposed matter.

        Returns:
            The recorded conflict check, with status 'clear' or 'conflict_found'.
        """
        opposing_parties = opposing_parties or []

        existing_client_names = {c.name.lower() for c in self.db.clients.values()}
        existing_opposing = {
            p.lower() for m in self.db.matters.values() for p in m.opposing_parties
        }

        matches: list[str] = []
        # Prospective client adverse to an existing matter's opposing party? Fine.
        # Prospective client IS an existing opposing party -> conflict.
        if prospective_client_name.lower() in existing_opposing:
            matches.append(prospective_client_name)
        for party in opposing_parties:
            if party.lower() in existing_client_names:
                matches.append(party)
            elif party.lower() in existing_opposing:
                matches.append(party)

        # De-duplicate while preserving order.
        seen = set()
        matches = [m for m in matches if not (m.lower() in seen or seen.add(m.lower()))]

        conflict_check_id = f"cc_{len(self.db.conflict_checks) + 1}"
        check = ConflictCheck(
            conflict_check_id=conflict_check_id,
            prospective_client_name=prospective_client_name,
            opposing_parties=opposing_parties,
            matches=matches,
            status="conflict_found" if matches else "clear",
            performed_date=LEGAL_CURRENT_DATE,
        )
        self.db.conflict_checks[conflict_check_id] = check
        return check

    @is_tool(ToolType.WRITE)
    def create_client(
        self,
        name: str,
        client_type: ClientType,
        email: str,
        phone: str,
        date_of_birth: Optional[str] = None,
        abn: Optional[str] = None,
        address: Optional[str] = None,
    ) -> Client:
        """
        Create a new client record. The client's identity is NOT verified on creation —
        call verify_client_identity once ID documents have been sighted.

        Args:
            name: The client's full name (or company name).
            client_type: 'individual' or 'company'.
            email: The client's email address.
            phone: The client's phone number.
            date_of_birth: Date of birth (ISO YYYY-MM-DD) for individuals.
            abn: Australian Business Number for company clients.
            address: The client's address.

        Returns:
            The created client.
        """
        client_id = f"client_{len(self.db.clients) + 1:03d}"
        client = Client(
            client_id=client_id,
            name=name,
            client_type=client_type,
            email=email,
            phone=phone,
            identity_verified=False,
            date_of_birth=date_of_birth,
            abn=abn,
            address=address,
        )
        self.db.clients[client_id] = client
        return client

    @is_tool(ToolType.WRITE)
    def verify_client_identity(self, client_id: str) -> Client:
        """
        Mark a client's identity as verified (ID documents have been sighted).
        A matter cannot be opened for a client whose identity is not verified.

        Args:
            client_id: The client ID, such as 'client_005'.

        Returns:
            The updated client.

        Raises:
            ValueError: If the client is not found.
        """
        client = self._get_client(client_id)
        client.identity_verified = True
        return client

    @is_tool(ToolType.WRITE)
    def create_costs_agreement(
        self,
        client_id: str,
        fee_type: FeeType,
        estimated_total: float,
        uplift_percentage: Optional[float] = None,
        signed: bool = True,
    ) -> CostsAgreement:
        """
        Create a costs agreement for a client and provide costs disclosure.

        The disclosure tier is derived from the estimated total legal costs:
        - below $750: tier 'none' (no formal disclosure required),
        - $750-$3,000: tier 'short_form' (disclosure required),
        - above $3,000: tier 'full' (a written, signed costs agreement is required).

        Fee types: 'time_based', 'fixed', or 'conditional' ('no win, no fee').
        Contingency / percentage-of-recovery fees are PROHIBITED under the LPUL and
        cannot be created. A conditional agreement may include an uplift fee capped at 25%.

        Args:
            client_id: The client the agreement is for.
            fee_type: 'time_based', 'fixed', or 'conditional'.
            estimated_total: Estimated total legal costs (AUD, excl. GST & disbursements).
            uplift_percentage: Uplift fee percentage for conditional agreements (0 < x <= 25).
            signed: Whether the client has signed the agreement.

        Returns:
            The created costs agreement.

        Raises:
            ValueError: If the uplift fee is invalid for the chosen fee type or exceeds 25%.
        """
        if fee_type == "conditional":
            if uplift_percentage is None:
                raise ValueError(
                    "A conditional costs agreement requires an uplift_percentage."
                )
            if uplift_percentage <= 0 or uplift_percentage > MAX_UPLIFT_PERCENTAGE:
                raise ValueError(
                    f"Uplift fee of {uplift_percentage}% is invalid. The uplift fee on a "
                    f"conditional costs agreement must be greater than 0 and no more than "
                    f"{MAX_UPLIFT_PERCENTAGE}% under the LPUL."
                )
        elif uplift_percentage is not None:
            raise ValueError(
                "An uplift fee can only be set on a 'conditional' costs agreement."
            )

        self._get_client(client_id)  # validate the client exists

        costs_agreement_id = f"ca_{len(self.db.costs_agreements) + 1}"
        agreement = CostsAgreement(
            costs_agreement_id=costs_agreement_id,
            client_id=client_id,
            fee_type=fee_type,
            estimated_total=estimated_total,
            uplift_percentage=uplift_percentage,
            disclosure_tier=self._disclosure_tier(estimated_total),
            signed=signed,
            created_date=LEGAL_CURRENT_DATE,
        )
        self.db.costs_agreements[costs_agreement_id] = agreement
        return agreement

    @is_tool(ToolType.WRITE)
    def open_matter(
        self,
        client_id: str,
        responsible_practitioner_id: str,
        matter_type: MatterType,
        estimated_costs: float,
        conflict_check_id: str,
        opposing_parties: Optional[List[str]] = None,
        costs_agreement_id: Optional[str] = None,
    ) -> Matter:
        """
        Open a new matter for a client. This is the final intake step and enforces the
        firm's intake policy. It fails unless all of the following hold:
        - the client's identity has been verified,
        - the responsible practitioner holds a CURRENT practising certificate,
        - the supplied conflict check exists and came back 'clear',
        - if estimated costs are $750 or more, a costs agreement is attached,
        - if estimated costs exceed $3,000, the attached costs agreement is a signed,
          'full'-disclosure written agreement.

        Args:
            client_id: The client the matter is for.
            responsible_practitioner_id: Practitioner who will run the matter.
            matter_type: Area of law: 'commercial', 'family', 'conveyancing', 'estates', or 'employment'.
            estimated_costs: Estimated total legal costs (AUD).
            conflict_check_id: A cleared conflict check for this matter.
            opposing_parties: Opposing parties on the matter.
            costs_agreement_id: The costs agreement attached to the matter.

        Returns:
            The opened matter.

        Raises:
            ValueError: If any intake precondition is not met.
        """
        opposing_parties = opposing_parties or []

        client = self._get_client(client_id)
        if not client.identity_verified:
            raise ValueError(
                f"Cannot open a matter: client {client_id}'s identity has not been verified."
            )

        practitioner = self._get_practitioner(responsible_practitioner_id)
        if practitioner.pc_status != "current":
            raise ValueError(
                f"Cannot open a matter: practitioner {responsible_practitioner_id} does not "
                f"hold a current practising certificate (status: {practitioner.pc_status})."
            )

        check = self._get_conflict_check(conflict_check_id)
        if check.status != "clear":
            raise ValueError(
                f"Cannot open a matter: conflict check {conflict_check_id} returned "
                f"'{check.status}'. The matter cannot proceed until the conflict is resolved."
            )

        if estimated_costs >= COSTS_DISCLOSURE_LOWER_THRESHOLD:
            if costs_agreement_id is None:
                raise ValueError(
                    "Cannot open a matter: estimated costs are at or above the $750 disclosure "
                    "threshold, so a costs agreement must be provided."
                )
            agreement = self._get_costs_agreement(costs_agreement_id)
            if estimated_costs > COSTS_DISCLOSURE_UPPER_THRESHOLD:
                if agreement.disclosure_tier != "full" or not agreement.signed:
                    raise ValueError(
                        "Cannot open a matter: estimated costs exceed $3,000, which requires a "
                        "signed, full-disclosure written costs agreement."
                    )

        matter_id = f"matter_{len(self.db.matters) + 1:03d}"
        matter = Matter(
            matter_id=matter_id,
            client_id=client_id,
            responsible_practitioner_id=responsible_practitioner_id,
            matter_type=matter_type,
            opposing_parties=opposing_parties,
            estimated_costs=estimated_costs,
            status="open",
            conflict_check_id=conflict_check_id,
            costs_agreement_id=costs_agreement_id,
            opened_date=LEGAL_CURRENT_DATE,
        )
        self.db.matters[matter_id] = matter
        return matter

    # --- GENERIC tools -------------------------------------------------------

    @is_tool(ToolType.GENERIC)
    def transfer_to_human(self, summary: str) -> str:
        """
        Escalate the intake to a human (e.g. a principal) — for example when a conflict
        is found, a client insists on a prohibited fee arrangement, or supervision is required.

        Args:
            summary: A short summary of why the escalation is needed.

        Returns:
            Confirmation that the matter has been escalated.
        """
        return "Escalated to a principal for review."
