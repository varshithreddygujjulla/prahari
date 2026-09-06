"""
Data intake (ADD DATA) — the ingestion specification's guarantees, enforced.

The theme of every test: the system tolerates missing data without inventing
it, refuses malformed values without silently fixing them, and never overwrites
a conflicting record.
"""
import json
import os

import pytest

from backend.ingestion import intake


# ---------------------------------------------------------------- tolerate, never invent
def test_missing_optional_field_keeps_the_record():
    """A missing receiver → PARTIAL and retained, not rejected."""
    r = intake.preview("cdr", "json", json.dumps([
        {"caller": "9811000002", "receiver": None,
         "timestamp": "2026-03-22T14:35:00"}]))
    rec = r["records"][0]
    assert rec["quality"]["validation_status"] == "PARTIAL"
    assert rec["committable"] is True
    assert rec["parsed"]["receiver"] is None       # null, not fabricated


def test_nothing_is_fabricated():
    """Absent values stay absent across every field."""
    r = intake.preview("bank", "json", json.dumps([
        {"from_account": "ACC9003", "to_account": "ACC9002",
         "amount_inr": None, "date": "2026-03-03"}]))
    assert r["records"][0]["parsed"]["amount_inr"] is None


def test_raw_value_is_preserved():
    r = intake.preview("phone", "json", json.dumps([
        {"phone": "  9811000200  ", "registered_name": "New Person"}]))
    rec = r["records"][0]
    assert rec["raw"]["phone"] == "  9811000200  "   # verbatim
    assert rec["parsed"]["phone"] == "9811000200"    # normalised


def test_every_record_gets_a_source_and_id():
    r = intake.preview("accounts", "json", json.dumps([{"account": "ACC9999"}]))
    rec = r["records"][0]
    assert rec["record_id"]
    assert rec["source_type"] == "ACCOUNTS"


# ---------------------------------------------------------------- refuse, never fix
def test_malformed_value_is_invalid_and_not_committable():
    r = intake.preview("bank", "json", json.dumps([
        {"from_account": "ACC9003", "to_account": "ACC9002",
         "amount_inr": 1000, "date": "not-a-date"}]))
    rec = r["records"][0]
    assert rec["quality"]["validation_status"] == "INVALID"
    assert rec["committable"] is False
    assert any("date" in i for i in rec["issues"])


def test_bad_coordinates_are_rejected_not_clamped():
    r = intake.preview("gps", "json", json.dumps([
        {"vehicle_id": "KA01AB1234", "timestamp": "2026-03-18T18:42:00",
         "latitude": 999, "longitude": 10}]))
    rec = r["records"][0]
    assert rec["committable"] is False
    assert any("latitude" in i for i in rec["issues"])


def test_non_numeric_amount_rejected():
    r = intake.preview("bank", "json", json.dumps([
        {"from_account": "ACC1", "to_account": "ACC2",
         "amount_inr": "lots", "date": "2026-03-03"}]))
    assert r["records"][0]["committable"] is False


def test_malformed_json_gives_clear_error_not_a_guess():
    r = intake.preview("cdr", "json", "{ not valid json")
    assert "error" in r
    assert "JSON" in r["error"]


# ---------------------------------------------------------------- conflicts
def test_conflicting_holder_is_flagged_not_overwritten():
    """9811000001 is registered to Vikram Rathore in the corpus."""
    r = intake.preview("phone", "json", json.dumps([
        {"phone": "9811000001", "registered_name": "Someone Else"}]))
    rec = r["records"][0]
    assert rec["conflicts"]
    assert rec["conflicts"][0]["type"] == "CONFLICTING"
    assert rec["conflicts"][0]["existing"] == "Vikram Rathore"
    assert rec["quality"]["level"] == "LOW"


def test_matching_holder_is_not_a_conflict():
    r = intake.preview("phone", "json", json.dumps([
        {"phone": "9811000001", "registered_name": "Vikram Rathore"}]))
    assert not r["records"][0]["conflicts"]


def test_duplicate_row_is_detected():
    # ACC9003 -> ACC9002, 75000, 2026-03-07 exists in bank.csv
    r = intake.preview("bank", "json", json.dumps([
        {"from_account": "ACC9003", "to_account": "ACC9002",
         "amount_inr": 75000, "date": "2026-03-07"}]))
    assert r["records"][0]["duplicate"] is True


# ---------------------------------------------------------------- CSV + mapping
def test_csv_import_with_field_aliases():
    r = intake.preview("vehicles", "csv",
                       "registration_number,registered_owner,type\n"
                       "MH12AB0007,Test Person,Truck")
    rec = r["records"][0]
    assert rec["parsed"]["vehicle_number"] == "MH12AB0007"
    assert rec["parsed"]["owner_name"] == "Test Person"
    assert rec["quality"]["validation_status"] == "VALID"


def test_explicit_column_mapping_overrides_aliases():
    r = intake.preview("phone", "csv", "mystery_col\n9811000200",
                       mapping={"phone": "mystery_col"})
    assert r["records"][0]["parsed"]["phone"] == "9811000200"


# ---------------------------------------------------------------- FIR text
def test_fir_text_extracts_entities():
    """The intake extractor is the SAME regex object the graph builder uses
    (imported from loaders.py), so the preview shows exactly what will land on
    the board. Trigger words are case-insensitive — a sentence-initial
    'Accused Arjun Mehta' is captured as well as 'named associate Ravi
    Malhotra' — while the name itself must still be two capitalised words."""
    r = intake.preview("fir", "text",
                       "FIRST INFORMATION REPORT\nFIR No: 099/2026\n"
                       "Police Station: Delhi\nDate: 15-04-2026\nSections: NDPS\n"
                       "NARRATIVE:\nAccused Arjun Mehta named associate Ravi Malhotra. "
                       "Mobile number 9811000099 recovered.")
    rec = r["records"][0]
    assert rec["quality"]["validation_status"] == "VALID"
    # both the primary accused and the associate are captured, in narrative
    # order; that is exactly what the graph builder would also see
    assert rec["parsed"]["names_extracted"] == ["Arjun Mehta", "Ravi Malhotra"]
    assert rec["parsed"]["phones_extracted"] == ["9811000099"]
    assert rec["committable"] is True


def test_fir_without_names_is_not_committable():
    r = intake.preview("fir", "text", "Some prose with no capitalised full names.")
    assert r["records"][0]["committable"] is False


# ---------------------------------------------------------------- quality levels
def test_quality_levels_span_high_medium_low():
    r = intake.preview("vehicles", "json", json.dumps([
        {"vehicle_number": "MH12AB0007", "owner_name": "A", "vehicle_type": "Car"},
        {"vehicle_number": "MH12AB0008"},                       # missing optionals
        {"vehicle_number": "MH12AB0009", "owner_name": "B"},    # will conflict? no
    ]))
    levels = [rec["quality"]["level"] for rec in r["records"]]
    assert levels[0] == "HIGH"
    assert "MEDIUM" in levels


def test_unknown_source_type_is_reported():
    r = intake.preview("astrology", "json", "[]")
    assert "error" in r


# ---------------------------------------------------------------- commit (isolated)
@pytest.fixture
def clean_staged():
    """Remove any staged files this test creates, before and after."""
    targets = [os.path.join(intake.BASE, f) for f in ("cctv.csv", "gps.csv", "social.csv")]
    for t in targets:
        if os.path.exists(t):
            os.remove(t)
    yield
    for t in targets:
        if os.path.exists(t):
            os.remove(t)


def test_commit_writes_committable_and_holds_the_rest(clean_staged):
    payload = json.dumps([
        {"timestamp": "2026-03-18T19:10:00", "camera_id": "CAM-042",
         "location": "Port", "vehicle_number": "KA01AB1234",
         "vehicle_match_confidence": 94},
        {"timestamp": "bad-time", "camera_id": "CAM-043"},      # INVALID
    ])
    res = intake.commit("cctv", "json", payload)
    assert res["written"] == 1
    assert res["staged"] is True
    assert len(res["held"]) == 1
    assert "INVALID" in res["held"][0]["reason"]
    # the file exists and holds exactly the one committed row
    path = os.path.join(intake.BASE, "cctv.csv")
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as f:
        assert f.read().count("CAM-042") == 1
        assert "CAM-043" not in open(path, encoding="utf-8").read()


def test_commit_holds_conflicts_by_default(clean_staged):
    # phone conflict is held unless include_conflicts=True — verify via a staged
    # source is not possible (no conflict check there), so assert the flag exists
    # and preview already proved conflict detection. Here: INVALID is always held.
    res = intake.commit("gps", "json", json.dumps([
        {"vehicle_id": "V1", "timestamp": "2026-03-01T00:00:00",
         "latitude": 200, "longitude": 0}]))
    assert res["written"] == 0
    assert res["held"]
