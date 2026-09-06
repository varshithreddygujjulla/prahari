"""
config.py — every tunable number the analytics stack uses, in one place.

Nothing here is a magic constant buried in an algorithm: thresholds, confidence
bases and score weights all live here so an investigator (or a judge) can ask
"why 85?" and get a documented answer. Production deployments would load this
from a signed policy file reviewed by the department, not from source.
"""

# ---------------------------------------------------------------- source taxonomy
# Every piece of evidence is tagged with one of these. The wording is deliberate:
# "COMMUNICATION_METADATA" is call-detail records (who called whom, when) — it is
# NOT call content and NOT interception.
SOURCE_TYPES = {
    "FIR":                    "First Information Report narrative (CCTNS)",
    "COMMUNICATION_METADATA": "Call Detail Records — metadata only, no content",
    "FINANCIAL":              "Bank transaction record (FIU-IND style report)",
    "SUBSCRIBER_REGISTRY":    "Telecom subscriber registry",
    "ACCOUNT_REGISTRY":       "Bank account holder registry",
    "VEHICLE_REGISTRY":       "Vehicle registration record (VAHAN style)",
    "TRAVEL":                 "Travel / passenger manifest",
    "CUSTODY":                "Prison custody roster (e-Prisons style)",
    "IDENTITY_ASSERTION":     "Alternate name spelling observed in a legacy record",
}

# ---------------------------------------------------------------- edge confidence
# Base confidence (0-100) that a relationship is REAL, by how it was observed.
# Direct documentary records outrank inferences. Co-location in a jail block is
# the weakest: sharing a cell block is proximity, not proven association.
EDGE_BASE_CONFIDENCE = {
    "co-accused":        85,   # both names in the same FIR narrative
    "money":             90,   # explicit account-to-account transfer, both mapped
    "calls":             80,   # both ends resolve to registered subscribers
    "calls-unresolved":  60,   # one end is an unattributed number — holder unknown
    "phone-linked":      75,   # subscriber registry ties a handset to a person
    "registered-to":     88,   # vehicle registry owner
    "co-travel":         50,   # same route, same date — could be coincidence
    "jailed-together":   55,   # overlapping custody in one cell block
}

# Corroboration: each *additional independent source type* supporting the same
# relationship adds this much. Two records from the same source are not
# independent confirmation, so we count distinct source types, not record count.
CORROBORATION_BONUS = 8
MAX_CORROBORATION_BONUS = 16

# Repeated observation adds confidence, but with diminishing returns — 50 calls
# is not 50x the evidence of one call.
REPEAT_OBSERVATION_BONUS_CAP = 6

# We never emit 100%. Absolute certainty is not something this system can earn
# from correlated records.
CONFIDENCE_CEILING = 97
CONFIDENCE_FLOOR = 5

# ---------------------------------------------------------------- case clock
# The synthetic case data spans Jan-Mar 2026. Relative time windows ("last 7
# days") are anchored to the latest observed event in the data — the "case
# clock" — not to the wall clock, which would return an empty graph. The UI
# states this explicitly so nobody mistakes it for live data.
TIME_WINDOWS = {
    "all":  None,
    "24h":  1,
    "7d":   7,
    "30d":  30,
    "90d":  90,
}
DEFAULT_TIME_WINDOW = "all"

# ---------------------------------------------------------------- anomaly engine
ANOMALY_CONFIG = {
    # A pair's daily call count is compared against that pair's own baseline
    # (median of its active days). Reporting a multiple of baseline is far more
    # useful to an investigator than a bare count.
    "comm_spike": {
        "enabled": True,
        "min_total_calls": 6,        # ignore pairs with too little history
        "min_peak_calls": 4,         # peak day must be at least this busy
        "min_ratio": 2.5,            # peak must exceed baseline by this multiple
        "severity_ratio_high": 5.0,
        "severity_ratio_critical": 8.0,
    },
    # Same idea, but for a single entity's total outbound+inbound volume.
    "entity_surge": {
        "enabled": True,
        "min_total_calls": 10,
        "min_ratio": 2.2,
        "severity_ratio_high": 4.0,
    },
    # A contact pair whose first-ever observed call falls late in the window.
    "new_relationship": {
        "enabled": True,
        "late_fraction": 0.70,       # first contact in last 30% of the window
        "min_calls_after": 3,        # and then became active
    },
    # Calls that bridge two detected communities are structurally interesting.
    "cross_community_comm": {
        "enabled": True,
        "min_calls": 3,
    },
    # Robust outlier detection on transfer amounts (median + MAD, not mean+sd:
    # a single 7-lakh transfer would drag a mean-based threshold with it).
    # Thresholds are in median-absolute-deviations. Calibrated against the
    # corpus, which has three tiers: routine transfers (₹1k-19k), a
    # consolidation tier (₹55k-85k) and large payouts (₹350k-700k). Detection
    # starts at the consolidation tier; only the payout tier reaches CRITICAL,
    # so severity stays meaningful instead of firing on a quarter of all rows.
    "transaction_amount": {
        "enabled": True,
        "min_records": 8,
        "mad_multiplier": 5.0,
        "severity_multiplier_high": 10.0,
        "severity_multiplier_critical": 30.0,
    },
    # Money in and back out through the same node inside a short window —
    # the classic layering shape.
    "rapid_money_movement": {
        "enabled": True,
        "window_days": 7,
        "min_pass_through_ratio": 0.60,   # >=60% of inflow moves back out
        "min_amount_inr": 100000,
    },
    # Several similar-sized transfers converging on one beneficiary (structuring).
    "structured_transactions": {
        "enabled": True,
        "min_senders": 3,
        "window_days": 21,
        "amount_similarity": 0.35,   # spread within +/-35% of the median
    },
    # International travel shortly after a large inflow.
    "travel_after_inflow": {
        "enabled": True,
        "window_days": 10,
        "min_amount_inr": 200000,
        "international_cities": {"Dubai", "Sharjah", "Bangkok", "Kathmandu",
                                 "Colombo", "Singapore", "Doha"},
    },
    # A node acquiring several new contacts late in the observation window.
    "connectivity_surge": {
        "enabled": True,
        "late_fraction": 0.70,
        "min_new_contacts": 2,
    },
    # Activity concentrated immediately before a reference event. Reference
    # events are dated FIRs — real records, not a narrative device.
    "pre_event_cluster": {
        "enabled": True,
        "lookback_hours": 72,
        "min_events": 4,
    },
}

SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

# ---------------------------------------------------------------- lead scoring
# Maximum points each signal can contribute to the INVESTIGATIVE LEAD SCORE.
# They sum to 100. A lead score is a triage aid — it ranks what an investigator
# should look at next. It is not a measure of guilt and carries no legal weight.
LEAD_SCORE_CAPS = {
    "financial_anomaly":      18,
    "cross_community":        16,
    "communication_anomaly":  14,
    "temporal_correlation":   12,
    "location_correlation":   12,
    "multi_source":           12,
    "network_centrality":     10,
    "entity_resolution":       6,
}

# Bands used for display only.
LEAD_SCORE_BANDS = [
    (75, "PRIORITY REVIEW"),
    (50, "REVIEW"),
    (25, "MONITOR"),
    (0,  "LOW SIGNAL"),
]

# ---------------------------------------------------------------- entity resolution
ER_CONFIG = {
    # Positive evidence that two name strings denote the same person.
    "points": {
        "exact_normalized_name": 50,
        "abbreviated_given_name": 30,   # "R. Yadav" vs "Ramesh Yadav"
        "high_string_similarity": 28,   # scaled by the actual ratio
        "phonetic_match": 20,           # "Yadhav" vs "Yadav"
        "shared_phone": 30,
        "shared_account": 30,
        "shared_vehicle": 25,
        "shared_record": 10,
    },
    # Negative evidence. Without these, any two people sharing a surname would
    # merge — the single most dangerous failure mode in this whole system.
    "penalties": {
        "conflicting_identifiers": -35,  # each side has ids, none shared
        "no_shared_identifiers": -12,    # name-only evidence
        # A shared identifier with no supporting name evidence is the signature
        # of an identifier changing hands (a reassigned phone number), not of
        # one person under two names. Treat it as a warning, not a match.
        "identifier_without_name_support": -18,
    },
    # Names are only grouped into one candidate identity when the pairwise
    # score reaches this band, so clusters inherit the scorer's caution rather
    # than merging on a raw shared identifier.
    "cluster_link_threshold": 55,
    "string_similarity_floor": 0.86,
    # Decision bands. Nothing is ever merged automatically.
    "bands": [
        (80, "LIKELY_SAME_ENTITY",   "Present to investigator for confirmation"),
        (55, "POSSIBLE_SAME_ENTITY", "Requires investigator review before use"),
        (0,  "UNLIKELY_SAME_ENTITY", "Keep separate — insufficient evidence"),
    ],
    "min_report_confidence": 25,   # below this we do not surface the pair at all
}

# ---------------------------------------------------------------- terminology
# Section 25 of the specification: the UI must not overclaim. These are the
# approved labels; the codebase should not contain the left-hand column.
APPROVED_TERMS = {
    "hidden kingpin":     "Potential Network Controller",
    "kingpin":            "Potential Network Controller",
    "prime suspect":      "Investigative Lead",
    "criminal":           "Investigative Lead",
    "burner phone":       "Unresolved Number",
    "phone surveillance": "Communication Metadata",
    "criminal connection": "Potential Association",
}

# Mandatory disclaimer attached to every algorithmic finding.
HUMAN_VERIFICATION_NOTICE = "Investigative lead — requires human verification."

# AI brief disclaimer.
AI_BRIEF_NOTICE = ("AI-generated analytical summary. Requires investigator "
                   "verification.")
