"""
Corpus integrity: the shipped data/ must load cleanly, the FIR extractor must
be ONE regex shared by loader and intake, malformed registry rows must never
resolve a handset, and the demo reset script must see data/ == data/seed/.
"""
import os
import shutil

import pytest

from backend import reset_demo_data
from backend.entity_resolution.resolver import build_profiles
from backend.graph import build
from backend.ingestion import intake, loaders


# ---------------------------------------------------------------- FIR extraction
def test_intake_and_loader_share_one_fir_regex():
    """Not merely equal patterns — the same compiled object, so they cannot drift."""
    assert intake.FIR_NAME_RE is loaders.FIR_NAME_RE
    assert intake.FIR_PHONE_RE is loaders.FIR_PHONE_RE


def test_trigger_words_are_case_insensitive_but_names_are_not():
    text = ("NARRATIVE:\nAccused Sunil Kumar was apprehended. During interrogation "
            "accused named associate Deepak Singh. CO-ACCUSED Anwar Khan absconding.")
    assert loaders.FIR_NAME_RE.findall(text) == ["Sunil Kumar", "Deepak Singh", "Anwar Khan"]
    # lowercase prose after a trigger is not a person
    assert loaders.FIR_NAME_RE.findall("accused named associate of the complainant") == []


def test_every_seeded_fir_names_both_parties(records):
    """Each demo FIR narrates a primary accused AND an associate/co-accused.
    Before the trigger words were case-insensitive the sentence-initial
    'Accused X' was silently dropped, so this guards the fix."""
    for r in records["fir"]:
        assert len(r.fields["names"]) >= 2, f"{r.record_id} extracted {r.fields['names']}"


def test_recovered_handset_belongs_to_the_primary_accused(records):
    """The builder attributes a recovered phone to names[0]. With the corpus
    as shipped that number is registered to that very person, so no spurious
    'phone-linked' edge is asserted between the accused and the associate."""
    owner = {r.fields["phone"]: r.fields["registered_name"] for r in records["phone_directory"]}
    for r in records["fir"]:
        primary = r.fields["names"][0]
        for ph in r.fields["phones"]:
            if ph in owner:
                assert owner[ph] == primary, f"{r.record_id}: {ph} is {owner[ph]}, not {primary}"


def test_seed_graph_has_no_phone_linked_edges(bundle):
    for a, b, d in bundle.G.edges(data=True):
        rels = {rel.get("relation") for rel in d.get("relations", [])} | {d.get("relation")}
        assert "phone-linked" not in rels, f"{a}-{b}"


# ---------------------------------------------------------------- subscriber registry
def test_shipped_phone_directory_is_all_valid_mobiles(records):
    assert all(not r.issues for r in records["phone_directory"]), \
        [(r.record_id, r.issues) for r in records["phone_directory"] if r.issues]
    assert all(loaders.MOBILE_RE.match(r.fields["phone"]) for r in records["phone_directory"])


def test_malformed_registry_row_is_flagged_and_never_resolves(records, tmp_path, monkeypatch):
    """An account id in the phone column (the old ACC7777 row) is kept for
    listing, flagged, and ignored by both the graph builder and the resolver."""
    (tmp_path / "phone_directory.csv").write_text(
        "phone,registered_name\n9811000001,Vikram Rathore\nACC7777,OM TRADERS PVT LTD\n"
        "011-2345678,Landline Holder\n", encoding="utf-8")
    monkeypatch.setattr(loaders, "BASE", str(tmp_path))
    rows = loaders.load_phone_directory()
    assert [bool(r.issues) for r in rows] == [False, True, True]
    assert "not a 10-digit Indian mobile number" in rows[1].issues[0]

    recs = dict(records, phone_directory=rows)
    bundle = build(recs)
    assert bundle.entity_identifiers.get("OM TRADERS PVT LTD", {}).get("phones", []) == []
    assert "Landline Holder" not in bundle.G     # never entered via the registry
    profiles = build_profiles(bundle)
    assert "ACC7777" not in profiles["OM TRADERS PVT LTD"].phones
    assert profiles["OM TRADERS PVT LTD"].records      # the row is still cited


# ---------------------------------------------------------------- identity variants
def test_identity_variants_honour_their_record_id_column(records):
    ids = [r.record_id for r in records["identity_variants"]]
    assert ids[:3] == ["IDV-A1", "IDV-A2", "IDV-A3"]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("IDV-") for i in ids)


def test_identity_variant_without_record_id_gets_positional_id(tmp_path, monkeypatch):
    (tmp_path / "identity_variants.csv").write_text(
        "record_id,observed_name,source_hint,phone,account,vehicle,note\n"
        "IDV-Z9,R. Yadav,x,,,,\n"
        ",Ramesh Yadhav,y,,,,\n", encoding="utf-8")
    monkeypatch.setattr(loaders, "BASE", str(tmp_path))
    ids = [r.record_id for r in loaders.load_identity_variants()]
    assert ids == ["IDV-Z9", "IDV-0002"]


# ---------------------------------------------------------------- demo reset
def test_seed_snapshot_exists_and_matches_the_corpus():
    """data/seed/ is what the reset script restores. If this fails the seed is
    stale (or data/ has uncommitted demo changes): run
    `python backend/reset_demo_data.py --dry-run` to see which."""
    assert os.path.isdir(reset_demo_data.SEED)
    for fn in reset_demo_data.CORPUS_FILES:
        seed = open(os.path.join(reset_demo_data.SEED, fn), "rb").read()
        live = open(os.path.join(loaders.BASE, fn), "rb").read()
        assert seed == live, f"{fn} differs from data/seed/"
    assert reset_demo_data._fir_files(reset_demo_data.SEED_FIRS) == \
        reset_demo_data._fir_files(loaders.FIRS)


def test_reset_restores_a_modified_corpus(tmp_path, monkeypatch):
    """End-to-end on a scratch copy: append rows, add a FIR and staged files,
    then restore and check every managed file equals the seed."""
    scratch = tmp_path / "data"
    shutil.copytree(loaders.BASE, scratch, ignore=shutil.ignore_patterns("audit_chain.json"))
    monkeypatch.setattr(reset_demo_data, "BASE", str(scratch))
    monkeypatch.setattr(reset_demo_data, "FIRS", str(scratch / "firs"))
    monkeypatch.setattr(reset_demo_data, "SEED", str(scratch / "seed"))
    monkeypatch.setattr(reset_demo_data, "SEED_FIRS", str(scratch / "seed" / "firs"))

    with open(scratch / "cdr.csv", "a", encoding="utf-8") as f:
        f.write("9811000001,9811000002,2026-03-30 10:00,10,TWR1\n")
    (scratch / "firs" / "FIR_099.txt").write_text("FIRST INFORMATION REPORT\n", encoding="utf-8")
    (scratch / "cctv.csv").write_text("a,b\n", encoding="utf-8")
    (scratch / "decisions.json").write_text("{}", encoding="utf-8")
    (scratch / "audit_chain.json").write_text("[]", encoding="utf-8")

    assert reset_demo_data.restore(keep_audit=False, dry_run=True) == 0
    assert (scratch / "cctv.csv").exists()            # dry run wrote nothing
    assert reset_demo_data.restore(keep_audit=False, dry_run=False) == 0

    for fn in reset_demo_data.CORPUS_FILES:
        assert (scratch / "seed" / fn).read_bytes() == (scratch / fn).read_bytes(), fn
    assert not (scratch / "firs" / "FIR_099.txt").exists()
    for fn in ("cctv.csv", "decisions.json", "audit_chain.json"):
        assert not (scratch / fn).exists(), fn
    # a second restore is a no-op
    assert reset_demo_data.restore(keep_audit=False, dry_run=False) == 0


def test_snapshot_refuses_to_overwrite_seed(tmp_path, monkeypatch):
    seed = tmp_path / "seed"
    seed.mkdir()
    monkeypatch.setattr(reset_demo_data, "SEED", str(seed))
    assert reset_demo_data.snapshot(force=False, dry_run=True) == 1
