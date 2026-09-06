"""
Anomaly detection (§6), lead scoring (§7) and false-positive safety (§14).

The recurring theme: findings must describe an observation against a baseline
and must never characterise a person.
"""
import re

import pytest

from backend import config
from backend.anomaly.detectors import DETECTORS


# ---------------------------------------------------------------- coverage
def test_multiple_detector_families_are_active(anomalies):
    kinds = {a["anomaly_type"] for a in anomalies}
    assert len(kinds) >= 6, f"only {kinds} fired"
    assert "COMMUNICATION_VOLUME_SPIKE" in kinds
    assert "UNUSUAL_TRANSACTION_AMOUNT" in kinds
    assert "RAPID_MONEY_MOVEMENT" in kinds


def test_no_detector_crashed(anomalies):
    errors = [a for a in anomalies if a["anomaly_type"] == "DETECTOR_ERROR"]
    assert not errors, f"detector failures: {[e['explanation'] for e in errors]}"


def test_all_registered_detectors_are_reachable():
    assert len(DETECTORS) >= 10


# ---------------------------------------------------------------- shape
def test_every_finding_has_the_required_fields(anomalies):
    required = ("anomaly_type", "severity", "confidence", "timestamp",
                "entities_involved", "evidence", "explanation", "baseline",
                "algorithm")
    for a in anomalies:
        for field in required:
            assert field in a, f"{a['anomaly_type']} missing {field}"


def test_every_finding_cites_records(anomalies):
    for a in anomalies:
        assert a["source_records"], f"{a['anomaly_type']} cites nothing"


def test_severity_and_confidence_are_valid(anomalies):
    for a in anomalies:
        assert a["severity"] in config.SEVERITY_ORDER
        assert 0 <= a["confidence"] <= 100


def test_findings_are_ranked_by_severity(anomalies):
    ranks = [config.SEVERITY_ORDER[a["severity"]] for a in anomalies]
    assert ranks == sorted(ranks, reverse=True)


# ---------------------------------------------------------------- explanations
def test_explanations_quantify_against_a_baseline(anomalies):
    """"8.2x above baseline", not "suspicious"."""
    for a in anomalies:
        assert a["baseline"], f"{a['anomaly_type']} states no baseline"
        assert re.search(r"\d", a["explanation"]), \
            f"{a['anomaly_type']} explanation has no numbers"


BANNED = ["criminal", "guilty", "kingpin", "gangster", "offender",
          "perpetrator", "culprit"]


def test_no_finding_labels_a_person(anomalies):
    for a in anomalies:
        low = a["explanation"].lower()
        for word in BANNED:
            assert word not in low, \
                f"{a['anomaly_type']} uses banned term '{word}'"


def test_every_finding_carries_the_verification_notice(anomalies):
    for a in anomalies:
        assert a["verification_notice"] == config.HUMAN_VERIFICATION_NOTICE


# ---------------------------------------------------------------- calibration
def test_critical_severity_is_reserved_for_extremes(anomalies):
    """Severity must discriminate, not fire on everything."""
    crit = [a for a in anomalies if a["severity"] == "CRITICAL"]
    assert crit, "expected some critical findings"
    assert len(crit) <= len(anomalies) * 0.30, \
        "too many findings rated CRITICAL for the rating to mean anything"


def test_transaction_outliers_use_robust_statistics(anomalies):
    """Median + MAD, so one huge transfer cannot hide behind its own effect."""
    txn = [a for a in anomalies if a["anomaly_type"] == "UNUSUAL_TRANSACTION_AMOUNT"]
    assert txn
    for a in txn:
        assert "mad" in a["baseline"]
        assert a["baseline"]["deviations"] >= \
            config.ANOMALY_CONFIG["transaction_amount"]["mad_multiplier"]


def test_communication_baseline_uses_the_cdr_window_not_the_corpus(anomalies):
    """The custody roster reaches back to 2021; anchoring comms to that would
    make every call in March look like a brand-new relationship."""
    new_rels = [a for a in anomalies
                if a["anomaly_type"] == "NEW_COMMUNICATION_RELATIONSHIP"]
    surges = [a for a in anomalies if a["anomaly_type"] == "CONNECTIVITY_SURGE"]
    assert len(new_rels) + len(surges) < 25, \
        "communication window looks mis-anchored — far too many findings"


def test_detectors_are_configurable():
    for name, cfg in config.ANOMALY_CONFIG.items():
        assert "enabled" in cfg, f"{name} cannot be switched off"


# ---------------------------------------------------------------- lead scoring
def test_leads_are_bounded_and_ranked(leads):
    assert leads
    scores = [l["lead_score"] for l in leads]
    assert scores == sorted(scores, reverse=True)
    for l in leads:
        assert 0 <= l["lead_score"] <= 100


def test_every_lead_is_fully_explained(leads):
    for l in leads:
        assert l["factors"], f"{l['entity']} has a score but no factors"
        assert sum(f["points"] for f in l["factors"]) == l["lead_score"]
        for f in l["factors"]:
            assert f["reason"], f"{l['entity']}/{f['factor']} has no reason"
            assert f["points"] <= f["max_points"]


def test_no_single_factor_can_carry_a_lead(leads):
    for l in leads:
        for f in l["factors"]:
            assert f["max_points"] <= 20, \
                f"{f['factor']} cap {f['max_points']} is too dominant"


def test_factor_caps_sum_to_one_hundred():
    assert sum(config.LEAD_SCORE_CAPS.values()) == 100


def test_leads_carry_disclaimers(leads):
    for l in leads:
        assert l["verification_notice"] == config.HUMAN_VERIFICATION_NOTICE
        assert "not a measure of guilt" in l["disclaimer"].lower()


def test_lead_bands_never_assert_criminality(leads):
    for l in leads:
        assert l["band"] in [b[1] for b in config.LEAD_SCORE_BANDS]
        for word in BANNED:
            assert word not in l["band"].lower()


def test_entities_absent_from_firs_are_flagged_as_uncertain(leads):
    for l in leads:
        if not l["in_fir"]:
            assert any("not named in any FIR" in u for u in l["uncertainty"])


# ---------------------------------------------------------------- controllers
def test_network_controller_is_evidence_based_not_asserted(payload):
    ctrl = payload["network_controllers"]
    assert ctrl
    top = ctrl[0]
    assert top["entity"] == "Vikram Rathore"
    assert top["fir_mentions"] == 0
    assert top["net_inflow_inr"] == 700000
    assert top["label"] == "Potential Network Controller"
    assert top["uncertainty"], "must disclose what this does not establish"
    assert top["source_records"]


def test_controller_terminology_avoids_overclaiming(payload):
    for c in payload["network_controllers"]:
        blob = (c["label"] + " " + c["basis"]).lower()
        for word in BANNED:
            assert word not in blob
