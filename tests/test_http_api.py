"""
The HTTP contract, exercised through FastAPI's TestClient (needs httpx).

Everything here runs against the isolated data copy from conftest.py, so the
commits, decisions and audit blocks these tests create never touch data/.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.api import routes
from backend.ingestion import intake, loaders
from backend.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------- shell
def test_root_serves_the_dashboard_uncached(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "PRAHARI" in r.text
    assert "no-store" in r.headers.get("cache-control", "")


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_cors_allows_only_named_origins(client):
    ok = client.options("/api/graph", headers={
        "Origin": "http://localhost:8000",
        "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:8000"
    bad = client.options("/api/graph", headers={
        "Origin": "http://evil.example",
        "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


# ---------------------------------------------------------------- graph & findings
def test_graph_payload_and_window_validation(client):
    r = client.get("/api/graph")
    assert r.status_code == 200
    stats = r.json()["stats"]
    assert stats["people"] == 28 and stats["communities"] == 3
    assert client.get("/api/graph", params={"window": "eternity"}).status_code == 400
    assert client.get("/api/graph", params={"window": "7d"}).status_code == 200


def test_rebuild_accepts_get_and_post(client):
    for method in (client.get, client.post):
        r = method("/api/rebuild")
        assert r.status_code == 200
        assert r.json()["status"] == "rebuilt"
        assert r.json()["stats"]["people"] == 28


def test_leads_carry_the_verification_notice(client):
    r = client.get("/api/leads")
    body = r.json()
    assert body["leads"] and body["notice"] == config.HUMAN_VERIFICATION_NOTICE
    assert all(l["lead_score"] < 100 for l in body["leads"])
    assert client.get("/api/leads", params={"min_score": 101}).status_code == 422


def test_anomaly_filters(client):
    assert client.get("/api/anomalies", params={"severity": "bogus"}).status_code == 400
    crit = client.get("/api/anomalies", params={"severity": "critical"}).json()
    assert crit["count"] == len(crit["anomalies"])
    assert all(a["severity"] == "CRITICAL" for a in crit["anomalies"])


def test_entity_resolution_never_auto_merges(client):
    body = client.get("/api/entity-resolution").json()
    assert body["matches"] and body["policy"]
    assert all(m["confidence"] < 100 for m in body["matches"])


def test_config_exposes_notices(client):
    body = client.get("/api/config").json()
    assert body["notices"]["verification"] == config.HUMAN_VERIFICATION_NOTICE
    assert body["confidence_model"]["ceiling"] < 100


# ---------------------------------------------------------------- entities & provenance
def test_entity_dossier_and_404(client):
    r = client.get("/api/entity/Ramesh Yadav")
    assert r.status_code == 200
    d = r.json()
    assert d["in_fir"] and d["relationships"]
    assert d["verification_notice"] == config.HUMAN_VERIFICATION_NOTICE
    assert client.get("/api/entity/Nobody Here").status_code == 404


def test_casefile_over_http(client):
    d = client.get("/api/entity/Ramesh Yadav/casefile").json()
    assert d["firs"] and d["firs"][0]["fir_id"].startswith("FIR_")
    assert d["firs"][0]["co_accused"], "FIR narrates a co-accused"


def test_casefile_call_days_name_the_contacts(client):
    """'19 calls across 11 pairs' is the corpus-wide day; the case file must
    say who THIS person spoke to, how often, and in which direction."""
    d = client.get("/api/entity/Salim Qureshi/casefile").json()
    days = [m for m in d["recent_moves"] if m["type"] == "CALL_ACTIVITY"]
    assert days, "Salim Qureshi has call activity"
    for m in days:
        assert m["contacts"], m
        total = sum(c["calls"] for c in m["contacts"])
        assert m["summary"].startswith(f"{total} call")
        assert m["contacts"][0]["with"] in m["summary"]
        for c in m["contacts"]:
            assert c["outgoing"] + c["incoming"] == c["calls"] == len(c["records"])
            assert c["with"] != "Salim Qureshi"
            assert all(rid.startswith("CDR-") for rid in c["records"])
        # every cited row is one of the contacts' rows, not the whole corpus day
        assert sorted(m["records"]) == sorted(r for c in m["contacts"] for r in c["records"])
    # the unresolved number appears by its bare number, never a guessed name
    assert any(c["with"] == "9990001111" for m in days for c in m["contacts"])


def test_evidence_resolves_identifiers_to_holders(client):
    cdr = client.get("/api/evidence/CDR-0001").json()["record"]
    res = cdr["resolved"]
    assert set(res) >= {"caller", "receiver"}
    for k in ("caller", "receiver"):
        assert res[k] is None or res[k] != cdr["fields"][k]     # a name, or stated unknown
    # the broker's number has no subscriber on file → explicitly None
    row = next(r for r in loaders.load_cdr() if r.fields["caller"] == "9990001111")
    assert client.get(f"/api/evidence/{row.record_id}").json()["record"]["resolved"]["caller"] is None
    txn = client.get("/api/evidence/TXN-0009").json()["record"]
    assert txn["resolved"] == {"from_account": "OM TRADERS PVT LTD", "to_account": "Vikram Rathore"}


def test_evidence_lookup_and_404(client):
    r = client.get("/api/evidence/FIR_001")
    assert r.status_code == 200
    assert r.json()["supports"], "FIR_001 supports at least one relationship"
    assert client.get("/api/evidence/NOPE-0001").status_code == 404
    assert client.get("/api/evidence/bad id!").status_code == 422


def test_relationship_drawer(client):
    r = client.get("/api/relationship", params={"a": "Ramesh Yadav", "b": "Sunil Kumar"})
    assert r.status_code == 200
    assert r.json()["source_records"]
    r = client.get("/api/relationship", params={"a": "Ramesh Yadav", "b": "Nobody Here"})
    assert r.status_code == 404


# ---------------------------------------------------------------- ask
def test_ask_answers_from_records_only(client):
    r = client.get("/api/ask", params={"q": "Who is the network controller"})
    assert r.status_code == 200
    body = r.json()
    assert body["bullets"] and body["examples"]
    assert client.get("/api/ask").status_code == 422        # q is required


# ---------------------------------------------------------------- intake
def test_intake_schema_lists_fir_as_text_only(client):
    s = client.get("/api/intake/schema").json()["sources"]
    assert s["fir"]["text_only"] is True
    assert "cdr" in s and "caller" in s["cdr"]["columns"]


def test_intake_preview_validates_without_writing(client):
    rows = [{"caller": "9811000001", "receiver": "9811000002",
             "timestamp": "2026-03-30T10:00:00", "duration_sec": 5, "tower_id": "T1"}]
    before = sum(1 for _ in open(os.path.join(loaders.BASE, "cdr.csv"), encoding="utf-8"))
    r = client.post("/api/intake/preview", json={
        "source_type": "cdr", "format": "json", "payload": json.dumps(rows)})
    assert r.status_code == 200
    rec = r.json()["records"][0]
    assert rec["quality"]["validation_status"] == "VALID" and rec["committable"]
    after = sum(1 for _ in open(os.path.join(loaders.BASE, "cdr.csv"), encoding="utf-8"))
    assert before == after


def test_intake_rejects_malformed_fir_json_with_400(client):
    r = client.post("/api/intake/preview", json={
        "source_type": "fir", "format": "json", "payload": "{not json"})
    assert r.status_code == 400
    assert "malformed JSON" in r.json()["detail"]
    r = client.post("/api/intake/preview", json={
        "source_type": "astrology", "format": "json", "payload": "[]"})
    assert r.status_code == 400
    r = client.post("/api/intake/preview", json={
        "source_type": "cdr", "format": "xml", "payload": "[]"})
    assert r.status_code == 422


def test_intake_commit_of_staged_source_lands_in_isolated_store(client):
    payload = json.dumps([{"camera_id": "CAM-1", "plate": "DL01AB4455",
                           "timestamp": "2026-03-30T10:00:00", "location": "Gate 1"}])
    r = client.post("/api/intake/commit", json={
        "source_type": "cctv", "format": "json", "payload": payload})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["written"] >= 1 and body.get("staged") is True
    assert os.path.exists(os.path.join(intake.BASE, "cctv.csv"))
    # proof of isolation: the shipped corpus did not gain a staged file
    shipped = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    assert not os.path.exists(os.path.join(shipped, "cctv.csv"))


# ---------------------------------------------------------------- decisions & audit
def test_decision_roundtrip_and_validation(client):
    r = client.post("/api/decision", json={
        "kind": "lead", "target": "Ramesh Yadav", "action": "BOGUS"})
    assert r.status_code == 400
    r = client.post("/api/decision", json={
        "kind": "lead", "target": "Ramesh Yadav", "action": "NEEDS_REVIEW",
        "note": "cross-check with FIR_007", "officer": "Officer-202"})
    assert r.status_code == 200
    assert r.json()["status"] == "recorded"
    store = client.get("/api/decisions").json()
    assert "lead" in store["actions"]
    assert any("Ramesh Yadav" in k for k in store["decisions"])
    assert os.path.exists(os.path.join(loaders.BASE, "decisions.json"))


def test_audit_chain_records_requests_and_verifies(client):
    before = client.get("/api/audit").json()
    client.get("/api/leads", params={"officer": "Officer-303"})
    after = client.get("/api/audit").json()
    assert after["chain_valid"] is True and after["tampered_block"] is None
    assert after["total_blocks"] == before["total_blocks"] + 1
    assert "LEAD_GENERATED" in after["actions"]
    mine = client.get("/api/audit", params={"officer": "Officer-303"}).json()
    assert mine["blocks"] and all(b["officer"] == "Officer-303" for b in mine["blocks"])
    # the chain being written is the isolated one, not data/audit_chain.json
    assert os.path.normpath(routes.audit.path).startswith(os.path.normpath(loaders.BASE))


def test_tamper_demo_leaves_live_chain_intact(client):
    d = client.get("/api/audit/tamper-demo").json()
    assert d["chain_valid_after_tampering"] is False
    assert d["first_broken_block"] == 1
    assert d["chain_valid_after_restore"] is True
