"""
Audit-chain integrity (§16), API contract, and the payload's terminology (§25).
"""
import json
import os
import re
import tempfile

import pytest

from backend import config
from backend.audit import AuditChain


# ---------------------------------------------------------------- audit chain
@pytest.fixture
def chain():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)
    c = AuditChain(path=path)
    yield c
    if os.path.exists(path):
        os.unlink(path)


def test_fresh_chain_verifies(chain):
    ok, bad = chain.verify()
    assert ok and bad is None


def test_chain_verifies_after_appends(chain):
    for i in range(5):
        chain.record(f"Officer-{i}", f"QUERY: test {i}", action_type="GRAPH_QUERY")
    ok, bad = chain.verify()
    assert ok, f"chain broke at block {bad}"


def test_editing_a_past_block_is_detected(chain):
    for i in range(4):
        chain.record("Officer-1", f"QUERY: {i}", action_type="GRAPH_QUERY")
    chain.chain[2]["action"] = "TAMPERED"
    ok, bad = chain.verify()
    assert not ok
    assert bad == 2


def test_deleting_a_block_is_detected(chain):
    for i in range(4):
        chain.record("Officer-1", f"QUERY: {i}")
    del chain.chain[2]
    ok, _ = chain.verify()
    assert not ok


def test_reordering_blocks_is_detected(chain):
    for i in range(4):
        chain.record("Officer-1", f"QUERY: {i}")
    chain.chain[1], chain.chain[2] = chain.chain[2], chain.chain[1]
    ok, _ = chain.verify()
    assert not ok


def test_each_block_commits_to_its_predecessor(chain):
    chain.record("Officer-1", "one")
    chain.record("Officer-2", "two")
    assert chain.chain[2]["prev_hash"] == chain.chain[1]["hash"]


def test_structured_fields_are_recorded_and_filterable(chain):
    chain.record("Officer-7", "opened case", action_type="CASE_CREATED",
                 role="SENIOR_OFFICER", case_id="OP-SANGAM", target="case")
    chain.record("Officer-8", "searched", action_type="ENTITY_SEARCHED")
    assert chain.verify()[0]
    by_officer = chain.filter(officer="Officer-7")
    assert len(by_officer) == 1
    assert by_officer[0]["case_id"] == "OP-SANGAM"
    assert chain.filter(action_type="ENTITY_SEARCHED")[0]["officer"] == "Officer-8"


def test_legacy_blocks_without_new_fields_still_verify(chain):
    """Blocks written by the original build carry no role/case_id."""
    chain.record("Officer-1", "legacy style")
    assert "role" not in chain.chain[-1]
    assert chain.verify()[0]


def test_chain_survives_a_reload(chain):
    chain.record("Officer-1", "persisted", action_type="GRAPH_QUERY")
    reloaded = AuditChain(path=chain.path)
    assert reloaded.verify()[0]
    assert reloaded.chain[-1]["action"] == "persisted"


# ---------------------------------------------------------------- payload
def test_payload_preserves_the_original_contract(payload):
    for key in ("nodes", "edges", "insights", "anomalies", "link_predictions",
                "stats"):
        assert key in payload
    for key in ("people", "edges", "communities", "firs_parsed"):
        assert key in payload["stats"]


def test_payload_exposes_the_phase1_structures(payload):
    for key in ("leads", "entity_resolution", "timeline", "insight_records",
                "network_controllers", "provenance", "notices"):
        assert key in payload


def test_nodes_carry_identity_and_financial_fields(payload):
    person = next(n for n in payload["nodes"] if n["kind"] == "person")
    for key in ("in_fir", "money_in", "money_out", "phones", "accounts",
                "lead_score"):
        assert key in person


def test_insights_are_evidence_backed(payload):
    assert payload["insight_records"]
    for i in payload["insight_records"]:
        assert i["source_records"], f"insight {i['kind']} cites nothing"
        assert i["algorithm"]
        assert i["verification_notice"] == config.HUMAN_VERIFICATION_NOTICE


def test_timeline_states_its_anchor(payload):
    clock = payload["timeline"]["clock"]
    assert clock["anchor"].startswith("2026-03-31")
    assert "not to" in payload["notices"]["clock"]


# ---------------------------------------------------------------- terminology
BANNED_UI_TERMS = ["hidden kingpin", "prime suspect", "burner phone",
                   "criminal connection", "phone surveillance"]


def test_payload_text_avoids_banned_terminology(payload):
    blob = json.dumps(payload, default=str).lower()
    for term in BANNED_UI_TERMS:
        assert term not in blob, f"payload still contains '{term}'"


def test_node_kinds_use_approved_names(payload):
    kinds = {n["kind"] for n in payload["nodes"]}
    assert "burner_phone" not in kinds
    assert "unresolved_number" in kinds


def _frontend_source(name):
    """Frontend file with comments stripped.

    Code comments legitimately name the terms and claims that were removed, in
    order to explain why they were removed. What must be clean is the text that
    ships to the investigator and the live code — not the commentary.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "frontend", name)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)   # HTML comments
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)    # block comments
    return text


# The dashboard shell must be clean of every replaced term, single words
# included. The classic board's SCRIPT still uses `roles.kingpin` as an internal
# variable name (nothing rendered says it), so it is held to the phrases only.
PHASE1_SHELL = ("app.html", "dashboard.js")
CLASSIC_BOARD = ("index.html", "phase1.js", "phase1.css")
BANNED_PHRASES = [t for t in config.APPROVED_TERMS if " " in t]


def test_frontend_does_not_ship_banned_terminology():
    for name in PHASE1_SHELL:
        text = _frontend_source(name).lower()
        for term in config.APPROVED_TERMS:
            assert term not in text, f"{name} still says '{term}'"
    for name in CLASSIC_BOARD:
        text = _frontend_source(name).lower()
        for term in BANNED_PHRASES:
            assert term not in text, f"{name} still says '{term}'"


def test_frontend_makes_no_unsupported_seizure_claim():
    """The old copy asserted a spike fell 48h before a seizure; the records
    place it nine days after the only FIR that mentions the port."""
    text = _frontend_source("index.html")
    assert "48 hours before" not in text
    assert "Mundra seizure" not in text


# ---------------------------------------------------------------- case file
# Called directly (no HTTP layer / httpx dependency), like the other tests here.
from fastapi import HTTPException                                  # noqa: E402
from backend.api.routes import entity_casefile                    # noqa: E402


def test_casefile_returns_fir_bullets_and_moves():
    d = entity_casefile(name="Ramesh Yadav", officer="Officer-101")
    assert d["in_fir"] is True
    assert d["firs"], "Ramesh Yadav should have FIRs on file"
    f = d["firs"][0]
    assert f["fir_id"].startswith("FIR_")
    assert f["narrative_points"], "narrative should be split into bullet points"
    assert "NDPS Act 8/20" in f["sections"], "a citation must not be split on '/'"
    assert d["recent_moves"], "should surface dated moves"
    assert d["verification_notice"]


def test_casefile_for_entity_with_no_fir_explains_why():
    d = entity_casefile(name="Vikram Rathore", officer="Officer-101")
    assert d["in_fir"] is False
    assert d["firs"] == []
    assert d["no_fir_note"] and "not named in any fir" in d["no_fir_note"].lower()


def test_casefile_unknown_entity_404():
    with pytest.raises(HTTPException) as ei:
        entity_casefile(name="Nobody Here")
    assert ei.value.status_code == 404
