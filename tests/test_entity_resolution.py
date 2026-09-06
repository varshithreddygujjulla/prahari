"""
Entity resolution, including the adversarial cases from specification §26.

The governing requirement is that the system flags uncertainty rather than
confidently merging incorrect entities. These tests therefore assert as much
about what the resolver REFUSES to conclude as about what it concludes.
"""
import pytest

from backend import config
from backend.entity_resolution.resolver import (
    build_profiles, is_abbreviation, name_similarity, normalize_name,
    score_pair, soundex,
)


# ---------------------------------------------------------------- primitives
def test_normalisation_strips_case_punctuation_and_honorifics():
    assert normalize_name("  Mr. Ramesh  Yadav ") == "RAMESH YADAV"
    assert normalize_name("RAMESH YADAV") == normalize_name("Ramesh Yadav")


def test_soundex_groups_transcription_variants():
    assert soundex("YADAV") == soundex("YADHAV")
    assert soundex("QURESHI") == soundex("QURESHI")


def test_soundex_separates_genuinely_different_surnames():
    assert soundex("YADAV") != soundex("SHARMA")


def test_abbreviation_detection():
    assert is_abbreviation("R. Yadav", "Ramesh Yadav")
    assert is_abbreviation("Ramesh Yadav", "R. Yadav")
    # Same given name is not an abbreviation of itself.
    assert not is_abbreviation("Ramesh Yadav", "Ramesh Yadav")
    # Surnames must agree exactly.
    assert not is_abbreviation("R. Yadav", "Ramesh Sharma")


def test_similarity_is_symmetric_and_order_insensitive():
    assert name_similarity("Ramesh Yadav", "Yadav Ramesh") == pytest.approx(1.0)
    assert name_similarity("A B", "B A") == name_similarity("B A", "A B")


# ---------------------------------------------------------------- Case A
def test_case_a_same_person_different_spellings_are_grouped(resolution):
    """Case A: one person recorded under several spellings."""
    clusters = {c["anchor_entity"]: c["members"] for c in resolution["clusters"]}
    assert "Ramesh Yadav" in clusters
    members = clusters["Ramesh Yadav"]
    for variant in ("R. Yadav", "RAMESH YADAV", "Ramesh Yadhav"):
        assert variant in members, f"{variant} should group with Ramesh Yadav"


def test_case_a_variants_score_above_review_threshold(bundle):
    profiles = build_profiles(bundle)
    for variant in ("Ramesh Yadhav", "RAMESH YADAV", "R. Yadav"):
        r = score_pair(profiles["Ramesh Yadav"], profiles[variant])
        assert r["confidence"] >= 55, f"{variant} scored only {r['confidence']}"
        assert r["decision"] in ("LIKELY_SAME_ENTITY", "POSSIBLE_SAME_ENTITY")


# ---------------------------------------------------------------- Case B
@pytest.mark.parametrize("real,decoy", [
    ("Ramesh Yadav", "Ramesh Yadava"),
    ("Amit Patel", "Amit Patil"),
    ("Vikram Rathore", "Vikram Rathod"),
])
def test_case_b_similar_names_different_people_are_not_merged(bundle, real, decoy):
    """Case B: two unrelated people with similar names must stay separate.

    This is the most dangerous failure mode in the system, so the assertion is
    strict: the pair must land in the UNLIKELY band, and the conflicting
    identifiers must be stated as the reason.
    """
    profiles = build_profiles(bundle)
    r = score_pair(profiles[real], profiles[decoy])
    assert r["decision"] == "UNLIKELY_SAME_ENTITY", \
        f"{real} ~ {decoy} scored {r['confidence']}"
    assert r["confidence"] < 55
    assert any("Conflicting identifiers" in x["reason"] for x in r["reasons"])


def test_case_b_decoys_never_enter_a_cluster(resolution):
    decoys = {"Ramesh Yadava", "Amit Patil", "Vikram Rathod", "Pooja Mehra"}
    for cluster in resolution["clusters"]:
        assert not (decoys & set(cluster["members"])), \
            f"decoy leaked into cluster {cluster['members']}"


def test_case_b_high_name_similarity_alone_cannot_merge(bundle):
    """Name evidence must not be sufficient on its own."""
    profiles = build_profiles(bundle)
    r = score_pair(profiles["Ramesh Yadav"], profiles["Ramesh Yadava"])
    name_points = sum(x["points"] for x in r["reasons"] if x["points"] > 0)
    assert name_points >= 40, "the decoy really is name-similar"
    assert r["confidence"] < 55, "yet it must not be treated as the same person"


# ---------------------------------------------------------------- Case C
def test_case_c_reassigned_phone_does_not_merge_identities(bundle):
    """Case C: a phone number that changed owner."""
    profiles = build_profiles(bundle)
    r = score_pair(profiles["Naveen Kaul"], profiles["Pooja Mehra"])
    assert r["decision"] == "UNLIKELY_SAME_ENTITY"
    assert any("without name support" in x["reason"].lower() for x in r["reasons"])
    assert any("reassigned" in u.lower() for u in r["uncertainty"]), \
        "the reassignment possibility must be stated, not hidden"


# ---------------------------------------------------------------- Case D
def test_case_d_vehicle_used_by_non_owner_does_not_merge(bundle):
    """Case D: a vehicle registered to one person but appearing with another."""
    profiles = build_profiles(bundle)
    r = score_pair(profiles["Ramesh Yadav"], profiles["Deepak Singh"])
    assert r["decision"] == "UNLIKELY_SAME_ENTITY"
    assert r["uncertainty"], "shared vehicle with unrelated names needs a caveat"


# ---------------------------------------------------------------- policy
def test_nothing_is_ever_auto_merged(resolution):
    assert resolution["stats"]["auto_merged"] == 0
    for m in resolution["matches"]:
        assert m["auto_merged"] is False
        assert m["verification_notice"] == config.HUMAN_VERIFICATION_NOTICE


def test_every_match_carries_reasons_and_source_records(resolution):
    for m in resolution["matches"]:
        assert m["reasons"], f"{m['entity']} ~ {m['candidate']} has no reasons"
        assert m["match_reasons"]
        assert m["source_records"]
        assert 0 <= m["confidence"] <= config.CONFIDENCE_CEILING


def test_clusters_are_unconfirmed_and_require_review(resolution):
    for c in resolution["clusters"]:
        assert c["status"] == "UNCONFIRMED"
        assert "confirm" in c["recommended_action"].lower()


def test_identity_variants_do_not_reach_the_graph(bundle):
    """The variant corpus must not create graph nodes."""
    for name in ("R. Yadav", "RAMESH YADAV", "Ramesh Yadhav", "Pooja Mehra",
                 "Ramesh Yadava", "Amit Patil"):
        assert name not in bundle.G, f"{name} leaked into the graph"
