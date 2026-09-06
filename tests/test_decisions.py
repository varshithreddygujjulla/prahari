"""
Investigator decisions — the human-verdict store (§14, §23).

The point of these: a decision is a person's judgement, recorded and auditable.
"Verified" is never something the system concludes on its own.
"""
import os

import pytest

from backend.cases import decisions as dec


@pytest.fixture
def clean_store():
    if os.path.exists(dec.PATH):
        os.remove(dec.PATH)
    yield
    if os.path.exists(dec.PATH):
        os.remove(dec.PATH)


def test_records_and_persists_a_verdict(clean_store):
    e = dec.record_decision("lead", "Ramesh Yadav", "VERIFIED", "Officer-101", "checked CDR")
    assert e["action"] == "VERIFIED"
    assert e["officer"] == "Officer-101"
    assert e["note"] == "checked CDR"
    assert e["timestamp"]
    # persisted and reloadable
    assert dec.get_decisions()["lead:Ramesh Yadav"]["action"] == "VERIFIED"


def test_latest_verdict_wins(clean_store):
    dec.record_decision("lead", "X", "VERIFIED", "Officer-1")
    dec.record_decision("lead", "X", "DISMISSED", "Officer-2")
    assert dec.get_decisions()["lead:X"]["action"] == "DISMISSED"


def test_identity_and_lead_have_distinct_actions(clean_store):
    assert "CONFIRMED" in dec.ACTIONS["identity"]
    assert "VERIFIED" in dec.ACTIONS["lead"]
    # a lead cannot be "CONFIRMED", an identity cannot be "VERIFIED"
    with pytest.raises(ValueError):
        dec.record_decision("lead", "X", "CONFIRMED", "Officer-1")
    with pytest.raises(ValueError):
        dec.record_decision("identity", "A ↔ B", "VERIFIED", "Officer-1")


def test_unknown_kind_rejected(clean_store):
    with pytest.raises(ValueError):
        dec.record_decision("astrology", "X", "VERIFIED", "Officer-1")


def test_decision_maps_to_audit_action():
    assert dec.DECISION_TO_AUDIT["VERIFIED"] == "LEAD_VERIFIED"
    assert dec.DECISION_TO_AUDIT["REJECTED"] == "LEAD_DISMISSED"


def test_empty_note_becomes_null(clean_store):
    e = dec.record_decision("lead", "Y", "NEEDS_REVIEW", "Officer-1", "   ")
    assert e["note"] is None
