"""
Undo for ADD DATA: batches, tombstones, stable ids, audit, and the HTTP surface.
Runs on the isolated data copy from conftest.py.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

from backend.api import routes
from backend.ingestion import intake, loaders, retraction
from backend.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _commit_cdr(client, rows, officer="Officer-404"):
    r = client.post("/api/intake/commit", json={
        "source_type": "cdr", "format": "json", "payload": json.dumps(rows), "officer": officer})
    assert r.status_code == 200, r.text
    return r.json()


def _cdr_ids():
    return [r.record_id for r in loaders.load_all()["cdr"]]


def test_commit_registers_a_batch(client):
    res = _commit_cdr(client, [{"caller": "9811000001", "receiver": "9811000002",
                                "timestamp": "2026-03-28T09:00:00", "duration_sec": 30, "tower_id": "T9"}])
    assert res["written"] == 1 and res["batch_id"].startswith("ING-")
    batches = client.get("/api/intake/batches").json()["batches"]
    b = next(x for x in batches if x["batch_id"] == res["batch_id"])
    assert b["record_ids"] == res["written_ids"] and b["retracted"] is False
    assert b["officer"] == "Officer-404" and b["source_type"] == "cdr"


def test_retract_hides_records_but_keeps_ids_and_rows(client):
    before = _cdr_ids()
    first = _commit_cdr(client, [{"caller": "9811000003", "receiver": "9811000004",
                                  "timestamp": "2026-03-28T10:00:00", "duration_sec": 10, "tower_id": "T1"}])
    second = _commit_cdr(client, [{"caller": "9811000005", "receiver": "9811000006",
                                   "timestamp": "2026-03-28T11:00:00", "duration_sec": 20, "tower_id": "T2"}])
    wrong, later = first["written_ids"][0], second["written_ids"][0]
    assert wrong in _cdr_ids() and later in _cdr_ids()
    rows_before = len(intake._read_store("cdr.csv"))

    # reason is mandatory
    r = client.post("/api/intake/retract", json={"batch_id": first["batch_id"], "reason": ""})
    assert r.status_code == 400 and "reason" in r.json()["detail"]

    r = client.post("/api/intake/retract", json={
        "batch_id": first["batch_id"], "reason": "pasted from a different case", "officer": "Officer-404"})
    assert r.status_code == 200, r.text
    assert r.json()["retracted_ids"] == [wrong]
    ids = _cdr_ids()
    assert wrong not in ids                      # gone from the board
    assert later in ids                          # the LATER batch keeps its id
    assert all(i in ids for i in before)         # the corpus is untouched
    assert len(intake._read_store("cdr.csv")) == rows_before   # rows stay on file

    # audited with the reason, and the batch list shows it
    audit = client.get("/api/audit", params={"action_type": "ADMIN_ACTION"}).json()
    assert any("DATA_RETRACTED" in b["action"] and "different case" in b["action"] for b in audit["blocks"])
    b = next(x for x in client.get("/api/intake/batches").json()["batches"] if x["batch_id"] == first["batch_id"])
    assert b["retracted"] is True and b["retraction"]["reason"] == "pasted from a different case"

    # retracting twice is refused; restore brings it back with the same id
    assert client.post("/api/intake/retract", json={"batch_id": first["batch_id"], "reason": "again"}).status_code == 400
    r = client.post("/api/intake/restore", json={"batch_id": first["batch_id"]})
    assert r.status_code == 200 and r.json()["restored_ids"] == [wrong]
    assert wrong in _cdr_ids()
    assert client.post("/api/intake/restore", json={"batch_id": first["batch_id"]}).status_code == 400


def test_the_shipped_corpus_cannot_be_retracted(client):
    r = client.post("/api/intake/retract", json={"batch_id": "ING-20260101-000000-abcdef", "reason": "nope"})
    assert r.status_code == 400 and "reset_demo_data" in r.json()["detail"]
    r = client.post("/api/intake/retract", json={"batch_id": "CDR-0001", "reason": "nope"})
    assert r.status_code == 422                  # not even a batch id shape


def test_a_retracted_row_no_longer_counts_as_a_duplicate(client):
    row = {"caller": "9811000007", "receiver": "9811000008",
           "timestamp": "2026-03-28T12:00:00", "duration_sec": 5, "tower_id": "T3"}
    res = _commit_cdr(client, [row])
    dup = client.post("/api/intake/preview", json={"source_type": "cdr", "format": "json", "payload": json.dumps([row])}).json()
    assert dup["records"][0]["duplicate"] is True
    client.post("/api/intake/retract", json={"batch_id": res["batch_id"], "reason": "wrong case"})
    again = client.post("/api/intake/preview", json={"source_type": "cdr", "format": "json", "payload": json.dumps([row])}).json()
    assert again["records"][0]["duplicate"] is False, "re-adding a retracted record is legitimate"


def test_retracted_fir_disappears_and_its_file_remains(client):
    text = ("FIRST INFORMATION REPORT\nFIR No: 077/2026\nPolice Station: Delhi\nDate: 20-04-2026\n"
            "Sections: IPC 420\nNARRATIVE:\nAccused Zed Alpha named associate Yash Beta. Number 9811000010 used.")
    r = client.post("/api/intake/commit", json={"source_type": "fir", "format": "text", "payload": text})
    assert r.status_code == 200, r.text
    fid, batch = r.json()["written_ids"][0], r.json()["batch_id"]
    assert client.get(f"/api/entity/Zed Alpha").status_code == 200
    client.post("/api/intake/retract", json={"batch_id": batch, "reason": "not this case"})
    assert client.get(f"/api/entity/Zed Alpha").status_code == 404
    assert os.path.exists(os.path.join(loaders.FIRS, f"{fid}.txt"))
    assert fid not in [x.record_id for x in loaders.load_all()["fir"]]


def test_reset_script_removes_retraction_state():
    assert "retracted.json" in __import__("backend.reset_demo_data", fromlist=["x"]).DERIVED_FILES
    assert "ingestions.json" in __import__("backend.reset_demo_data", fromlist=["x"]).DERIVED_FILES
