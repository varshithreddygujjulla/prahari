"""
Evidence provenance (§8) and the confidence model (§19).

The central property: the system must be structurally incapable of asserting a
relationship it cannot cite. That is tested directly — not by inspecting output
for citations, but by trying to create an unsupported assertion and requiring
it to raise.
"""
import pytest

from backend import config
from backend.evidence import (
    Assertion, EvidenceLedger, UnsupportedAssertionError, score_confidence,
)
from backend.ingestion import Record


def _rec(rid="X-1", stype="FIR", ts="2026-03-01T00:00:00"):
    return Record(record_id=rid, source="fir", source_file="data/x",
                  source_type=stype, fields={}, timestamp=ts, summary="test")


# ---------------------------------------------------------------- the guarantee
def test_assertion_without_evidence_is_impossible():
    with pytest.raises(UnsupportedAssertionError):
        Assertion(subject="A", obj="B", rel="calls", records=[],
                  algorithm="fabricated")


def test_ledger_refuses_unsupported_link():
    ledger = EvidenceLedger()
    with pytest.raises(UnsupportedAssertionError):
        ledger.assert_link("A", "B", "calls", [], algorithm="fabricated")


def test_ledger_refuses_unsupported_insight():
    ledger = EvidenceLedger()
    with pytest.raises(UnsupportedAssertionError):
        ledger.assert_insight("KIND", "headline", "detail", [],
                              algorithm="fabricated")


def test_scoring_refuses_zero_records():
    with pytest.raises(UnsupportedAssertionError):
        score_confidence("calls", [])


# ---------------------------------------------------------------- graph output
def test_every_edge_cites_source_records(bundle):
    for a, b, d in bundle.G.edges(data=True):
        assert d.get("source_records"), f"edge {a}-{b} cites nothing"
        assert d.get("evidence"), f"edge {a}-{b} has no evidence payload"
        assert d.get("algorithm"), f"edge {a}-{b} does not say how it was derived"


def test_every_edge_has_bounded_confidence(bundle):
    for a, b, d in bundle.G.edges(data=True):
        c = d["confidence"]
        assert config.CONFIDENCE_FLOOR <= c <= config.CONFIDENCE_CEILING, \
            f"edge {a}-{b} confidence {c} out of bounds"


def test_confidence_never_reaches_certainty(bundle):
    """Correlated records cannot establish 100% confidence."""
    for _a, _b, d in bundle.G.edges(data=True):
        assert d["confidence"] < 100


def test_confidence_breakdown_explains_the_number(bundle):
    for a, b, d in bundle.G.edges(data=True):
        assert d.get("confidence_breakdown"), f"edge {a}-{b} has no breakdown"
        for row in d["confidence_breakdown"]:
            assert "factor" in row and "points" in row and "detail" in row


def test_cited_record_ids_all_exist(bundle):
    known = {r.record_id for rs in bundle.records.values() for r in rs}
    for a, b, d in bundle.G.edges(data=True):
        for rid in d["source_records"]:
            assert rid in known, f"edge {a}-{b} cites unknown record {rid}"


def test_every_edge_carries_the_verification_notice(bundle):
    for _a, _b, d in bundle.G.edges(data=True):
        assert d["verification_notice"] == config.HUMAN_VERIFICATION_NOTICE


# ---------------------------------------------------------------- model shape
def test_corroboration_raises_confidence():
    one = score_confidence("calls", [_rec("A", "COMMUNICATION_METADATA")])
    two = score_confidence("calls", [_rec("A", "COMMUNICATION_METADATA"),
                                     _rec("B", "FINANCIAL")])
    assert two["confidence"] > one["confidence"]
    assert two["source_count"] == 2


def test_same_source_type_twice_is_not_independent_corroboration():
    once = score_confidence("calls", [_rec("A", "COMMUNICATION_METADATA")])
    twice = score_confidence("calls", [_rec("A", "COMMUNICATION_METADATA"),
                                       _rec("B", "COMMUNICATION_METADATA")],
                             observation_count=1)
    assert twice["source_count"] == once["source_count"] == 1


def test_unresolved_endpoint_scores_below_registered_endpoints():
    recs = [_rec("A", "COMMUNICATION_METADATA")]
    assert (score_confidence("calls-unresolved", recs)["confidence"]
            < score_confidence("calls", recs)["confidence"])


def test_custody_is_the_weakest_relationship_type():
    """Sharing a cell block is proximity, not association."""
    assert config.EDGE_BASE_CONFIDENCE["jailed-together"] < \
        config.EDGE_BASE_CONFIDENCE["co-accused"]
    assert config.EDGE_BASE_CONFIDENCE["jailed-together"] < \
        config.EDGE_BASE_CONFIDENCE["money"]


# ---------------------------------------------------------------- merging
def test_multi_relation_pair_keeps_every_relation(bundle):
    """A pair tied by a transfer AND calls must not lose either."""
    multi = [d for _a, _b, d in bundle.G.edges(data=True)
             if len(d.get("rel_types", [])) > 1]
    assert multi, "expected at least one pair with several relations"
    for d in multi:
        assert len(d["relations"]) == len(d["rel_types"])
        for r in d["relations"]:
            assert r["source_records"]


def test_merged_confidence_is_at_least_the_strongest_part(bundle):
    for _a, _b, d in bundle.G.edges(data=True):
        if len(d.get("relations", [])) > 1:
            assert d["confidence"] >= max(r["confidence"] for r in d["relations"])


def test_reverse_provenance_index_resolves(bundle):
    index = bundle.ledger.record_index()
    assert index
    for rid, uses in index.items():
        for u in uses:
            assert u["type"] in ("edge", "insight")


# ---------------------------------------------------------------- uncertainty
def test_unresolved_number_edges_state_the_attribution_gap(bundle):
    found = False
    for a, b, d in bundle.G.edges(data=True):
        kinds = {bundle.G.nodes[a].get("kind"), bundle.G.nodes[b].get("kind")}
        if "unresolved_number" in kinds and "calls" in d.get("rel_types", []):
            found = True
            assert any("unresolved" in u.lower() for u in d["uncertainty"]), \
                f"edge {a}-{b} does not disclose the attribution gap"
    assert found, "expected at least one unresolved-number call edge"


def test_custody_edges_disclose_that_proximity_is_not_association(bundle):
    for _a, _b, d in bundle.G.edges(data=True):
        if "jailed-together" in d.get("rel_types", []):
            joined = " ".join(d["uncertainty"]).lower()
            assert "proximity" in joined
