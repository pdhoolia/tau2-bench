from tau2.utils.utils import DATA_DIR

LEGAL_DATA_DIR = DATA_DIR / "tau2" / "domains" / "legal"
LEGAL_DB_PATH = LEGAL_DATA_DIR / "db.json"
LEGAL_POLICY_PATH = LEGAL_DATA_DIR / "policy.md"
LEGAL_TASK_SET_PATH = LEGAL_DATA_DIR / "tasks.json"

# Fixed "current date" for the domain so limitation periods, PC expiry, and
# costs-agreement dates are deterministic across simulations.
LEGAL_CURRENT_DATE = "2026-06-15"

# Costs-disclosure thresholds under the LPUL (AUD, excl. GST & disbursements).
COSTS_DISCLOSURE_LOWER_THRESHOLD = 750.0
COSTS_DISCLOSURE_UPPER_THRESHOLD = 3000.0

# Maximum uplift fee for a conditional ("no win, no fee") costs agreement.
MAX_UPLIFT_PERCENTAGE = 25.0
