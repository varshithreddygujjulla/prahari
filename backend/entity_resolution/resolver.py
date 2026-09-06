"""
resolver.py — candidate identity matching.

Method
------
1. Build an identity profile for every observed name string across every
   source: which phones, accounts and vehicles it appears with, and which
   records it came from.
2. Block candidate pairs by phonetic surname or shared identifier, so we never
   compare all-against-all.
3. Score each pair from positive evidence (name forms, shared identifiers) and
   negative evidence (identifiers that disagree).
4. Band the result and recommend an action. Never merge.

Why identifiers outrank names
-----------------------------
"Ramesh Yadav" and "Ramesh Yadava" are one character apart. So are two
unrelated people in any Indian city of ten million. A shared phone number or
bank account is evidence about the world; a shared surname is evidence about
the language. The scorer reflects that: name signals alone cannot clear the
LIKELY band, and conflicting identifiers push a pair down hard.
"""
import hashlib
import itertools
import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set

from backend import config
from backend.ingestion import Record

HONORIFICS = {"MR", "MRS", "MS", "SHRI", "SMT", "DR", "SH", "KM"}
_PUNCT = re.compile(r"[^A-Z\s]")
_WS = re.compile(r"\s+")


# ---------------------------------------------------------------- name tools
def normalize_name(name: str) -> str:
    """Upper-case, strip punctuation and honorifics, collapse whitespace."""
    s = _PUNCT.sub(" ", (name or "").upper())
    tokens = [t for t in _WS.sub(" ", s).strip().split(" ")
              if t and t not in HONORIFICS]
    return " ".join(tokens)


def tokens_of(name: str) -> List[str]:
    return [t for t in normalize_name(name).split(" ") if t]


def soundex(token: str) -> str:
    """Classic Soundex. Catches transcription variants: YADAV/YADHAV."""
    token = re.sub(r"[^A-Z]", "", (token or "").upper())
    if not token:
        return ""
    codes = {**dict.fromkeys("BFPV", "1"), **dict.fromkeys("CGJKQSXZ", "2"),
             **dict.fromkeys("DT", "3"), **dict.fromkeys("L", "4"),
             **dict.fromkeys("MN", "5"), **dict.fromkeys("R", "6")}
    first, out, prev = token[0], "", codes.get(token[0], "")
    for ch in token[1:]:
        code = codes.get(ch, "")
        if code and code != prev:
            out += code
        if ch not in "HW":
            prev = code
    return (first + out + "000")[:4]


def name_similarity(a: str, b: str) -> float:
    """Token-sorted similarity ratio in 0..1."""
    na = " ".join(sorted(tokens_of(a)))
    nb = " ".join(sorted(tokens_of(b)))
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def is_abbreviation(a: str, b: str) -> bool:
    """True when one name abbreviates the other's given name: R. Yadav."""
    ta, tb = tokens_of(a), tokens_of(b)
    if len(ta) < 2 or len(tb) < 2:
        return False
    if ta[-1] != tb[-1]:                       # surnames must agree exactly
        return False
    ga, gb = ta[0], tb[0]
    if ga == gb:
        return False                           # identical, not an abbreviation
    short, long_ = (ga, gb) if len(ga) < len(gb) else (gb, ga)
    return len(short) == 1 and long_.startswith(short)


# ---------------------------------------------------------------- profiles
class IdentityProfile:
    """Everything observed about one name string."""

    def __init__(self, name: str):
        self.name = name
        self.normalized = normalize_name(name)
        self.phones: Set[str] = set()
        self.accounts: Set[str] = set()
        self.vehicles: Set[str] = set()
        self.records: List[Record] = []
        self.sources: Set[str] = set()
        self.in_graph = False
        self.notes: List[str] = []

    def add(self, rec: Optional[Record] = None, phone: str = "",
            account: str = "", vehicle: str = "", note: str = ""):
        if rec is not None and rec not in self.records:
            self.records.append(rec)
            self.sources.add(rec.source_type)
        if phone:
            self.phones.add(phone)
        if account:
            self.accounts.add(account)
        if vehicle:
            self.vehicles.add(vehicle)
        if note and note not in self.notes:
            self.notes.append(note)

    @property
    def identifiers(self) -> Set[str]:
        return ({f"phone:{p}" for p in self.phones}
                | {f"account:{a}" for a in self.accounts}
                | {f"vehicle:{v}" for v in self.vehicles})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "normalized": self.normalized,
            "in_graph": self.in_graph,
            "phones": sorted(self.phones),
            "accounts": sorted(self.accounts),
            "vehicles": sorted(self.vehicles),
            "source_types": sorted(self.sources),
            "source_records": [r.record_id for r in self.records],
            "notes": self.notes,
        }


def build_profiles(bundle) -> Dict[str, IdentityProfile]:
    recs = bundle.records
    profiles: Dict[str, IdentityProfile] = {}

    def prof(name: str) -> IdentityProfile:
        name = (name or "").strip()
        if name not in profiles:
            profiles[name] = IdentityProfile(name)
        return profiles[name]

    for r in recs.get("phone_directory", []):
        nm, ph = r.fields.get("registered_name", ""), r.fields.get("phone", "")
        if nm:
            # a flagged row still cites the record, but its malformed number
            # is not an identifier anyone can be matched on
            prof(nm).add(r, phone="" if r.issues else ph)
    for r in recs.get("accounts", []):
        nm, ac = r.fields.get("holder_name", ""), r.fields.get("account", "")
        if nm:
            prof(nm).add(r, account=ac)
    for r in recs.get("vehicles", []):
        nm, vn = r.fields.get("owner_name", ""), r.fields.get("vehicle_number", "")
        if nm:
            prof(nm).add(r, vehicle=vn)
    for r in recs.get("travel", []):
        nm = r.fields.get("passenger_name", "")
        if nm:
            prof(nm).add(r)
    for r in recs.get("prison", []):
        nm = r.fields.get("prisoner_name", "")
        if nm:
            prof(nm).add(r)
    for r in recs.get("fir", []):
        for nm in r.fields.get("names", []):
            prof(nm).add(r)

    # Alternate spellings from legacy records. These are the messy inputs a
    # real deployment would face; the live graph never consumes them.
    for r in recs.get("identity_variants", []):
        nm = r.fields.get("observed_name", "")
        if not nm:
            continue
        p = prof(nm)
        p.add(r, phone=r.fields.get("phone", "").strip(),
              account=r.fields.get("account", "").strip(),
              vehicle=r.fields.get("vehicle", "").strip(),
              note=r.fields.get("note", "").strip())

    for name, p in profiles.items():
        p.in_graph = name in bundle.G
    return profiles


# ---------------------------------------------------------------- scoring
def score_pair(a: IdentityProfile, b: IdentityProfile) -> Dict[str, Any]:
    pts = config.ER_CONFIG["points"]
    pen = config.ER_CONFIG["penalties"]
    reasons: List[Dict[str, Any]] = []
    score = 0

    # -- name evidence ----------------------------------------------------
    name_points = 0
    if a.normalized == b.normalized:
        name_points = pts["exact_normalized_name"]
        reasons.append({"reason": "Name match after normalisation",
                        "detail": f'"{a.name}" and "{b.name}" normalise to '
                                  f'"{a.normalized}"',
                        "points": name_points})
    elif is_abbreviation(a.name, b.name):
        name_points = pts["abbreviated_given_name"]
        reasons.append({"reason": "Abbreviated given name",
                        "detail": f'"{a.name}" is consistent with an '
                                  f'abbreviation of "{b.name}"',
                        "points": name_points})
    else:
        ratio = name_similarity(a.name, b.name)
        if ratio >= config.ER_CONFIG["string_similarity_floor"]:
            name_points = int(round(pts["high_string_similarity"] * ratio))
            reasons.append({"reason": "High name similarity",
                            "detail": f"token-sorted similarity {ratio:.0%}",
                            "points": name_points})
    score += name_points

    ta, tb = tokens_of(a.name), tokens_of(b.name)
    if ta and tb and len(ta) == len(tb) and a.normalized != b.normalized:
        if all(soundex(x) == soundex(y) for x, y in zip(ta, tb)):
            score += pts["phonetic_match"]
            reasons.append({"reason": "Phonetic match",
                            "detail": f"Soundex codes agree on every name part "
                                      f"({', '.join(soundex(x) for x in ta)})",
                            "points": pts["phonetic_match"]})

    # -- identifier evidence ---------------------------------------------
    shared_phone = a.phones & b.phones
    shared_acct = a.accounts & b.accounts
    shared_veh = a.vehicles & b.vehicles

    if shared_phone:
        score += pts["shared_phone"]
        reasons.append({"reason": "Shared phone number",
                        "detail": f"both appear with {', '.join(sorted(shared_phone))}",
                        "points": pts["shared_phone"]})
    if shared_acct:
        score += pts["shared_account"]
        reasons.append({"reason": "Shared bank account",
                        "detail": f"both appear with {', '.join(sorted(shared_acct))}",
                        "points": pts["shared_account"]})
    if shared_veh:
        score += pts["shared_vehicle"]
        reasons.append({"reason": "Shared vehicle",
                        "detail": f"both appear with {', '.join(sorted(shared_veh))}",
                        "points": pts["shared_vehicle"]})

    shared_records = {r.record_id for r in a.records} & {r.record_id for r in b.records}
    if shared_records:
        score += pts["shared_record"]
        reasons.append({"reason": "Co-occurrence in the same record",
                        "detail": f"{len(shared_records)} shared record(s)",
                        "points": pts["shared_record"]})

    # -- negative evidence ------------------------------------------------
    uncertainty: List[str] = []
    ids_a, ids_b = a.identifiers, b.identifiers
    has_shared = bool(shared_phone or shared_acct or shared_veh)

    if ids_a and ids_b and not has_shared:
        score += pen["conflicting_identifiers"]
        reasons.append({
            "reason": "Conflicting identifiers",
            "detail": f'"{a.name}" is associated with {sorted(ids_a)} while '
                      f'"{b.name}" is associated with {sorted(ids_b)} — no '
                      f'identifier is shared',
            "points": pen["conflicting_identifiers"]})
        uncertainty.append("Both identities carry identifiers and none match. "
                           "Similar names alone do not indicate one person.")
    elif not has_shared:
        score += pen["no_shared_identifiers"]
        reasons.append({"reason": "No shared identifiers",
                        "detail": "match rests on name evidence only",
                        "points": pen["no_shared_identifiers"]})
        uncertainty.append("No phone, account or vehicle links these records. "
                           "Name-only matches require manual confirmation.")

    if has_shared and name_points == 0:
        # Same handset, unrelated names: far more likely the number changed
        # hands than that one person uses two unrelated identities.
        score += pen["identifier_without_name_support"]
        shared_ids = sorted(shared_phone | shared_acct | shared_veh)
        reasons.append({
            "reason": "Shared identifier without name support",
            "detail": f'"{a.name}" and "{b.name}" share {", ".join(shared_ids)} '
                      f"but the names do not correspond",
            "points": pen["identifier_without_name_support"]})
        uncertainty.append(
            f"These records share {', '.join(shared_ids)} but carry unrelated "
            f"names. This is consistent with the identifier being reassigned "
            f"to a different holder, and should not be read as one identity.")

    score = int(max(0, min(config.CONFIDENCE_CEILING, score)))

    decision, action = config.ER_CONFIG["bands"][-1][1], config.ER_CONFIG["bands"][-1][2]
    for threshold, label, rec_action in config.ER_CONFIG["bands"]:
        if score >= threshold:
            decision, action = label, rec_action
            break

    return {"confidence": score, "reasons": reasons, "decision": decision,
            "recommended_action": action, "uncertainty": uncertainty}


# ---------------------------------------------------------------- clustering
def build_clusters(matches: List[Dict[str, Any]],
                   profiles: Dict[str, IdentityProfile]) -> List[Dict[str, Any]]:
    """Group name variants into candidate identities.

    Pairwise scoring alone leaves gaps: "R. Yadav" and "Ramesh Yadhav" both
    resolve strongly to "Ramesh Yadav" but weakly to each other, because
    neither the abbreviation rule nor the similarity floor bridges them
    directly. Grouping over links that reached the review band closes that gap
    without lowering the bar for any individual comparison.

    Links below the threshold are deliberately not used, so a reassigned phone
    number cannot drag an unrelated person into someone's identity cluster.
    """
    threshold = config.ER_CONFIG["cluster_link_threshold"]
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    linking = [m for m in matches if m["confidence"] >= threshold]
    for m in linking:
        union(m["entity"], m["candidate"])

    groups: Dict[str, List[str]] = defaultdict(list)
    for name in parent:
        groups[find(name)].append(name)

    out: List[Dict[str, Any]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members = sorted(members)
        anchor = next((m for m in members if profiles[m].in_graph), members[0])
        phones, accounts, vehicles, records = set(), set(), set(), set()
        for m in members:
            p = profiles[m]
            phones |= p.phones
            accounts |= p.accounts
            vehicles |= p.vehicles
            records |= {r.record_id for r in p.records}
        links = [m for m in linking
                 if m["entity"] in members and m["candidate"] in members]
        weakest = min((m["confidence"] for m in links), default=0)
        out.append({
            "cluster_id": "ER-" + hashlib.sha1("|".join(members).encode("utf-8")).hexdigest()[:8],
            "anchor_entity": anchor,
            "members": members,
            "member_count": len(members),
            "linking_confidence_min": weakest,
            "shared_phones": sorted(phones),
            "shared_accounts": sorted(accounts),
            "shared_vehicles": sorted(vehicles),
            "source_records": sorted(records),
            "links": [{"entity": m["entity"], "candidate": m["candidate"],
                       "confidence": m["confidence"],
                       "reasons": m["match_reasons"]} for m in links],
            "status": "UNCONFIRMED",
            "recommended_action": ("Investigator must confirm or reject each "
                                   "member before these records are treated as "
                                   "one entity."),
            "verification_notice": config.HUMAN_VERIFICATION_NOTICE,
        })
    out.sort(key=lambda c: -c["member_count"])
    return out


# ---------------------------------------------------------------- driver
def resolve(bundle) -> Dict[str, Any]:
    profiles = build_profiles(bundle)
    names = list(profiles)

    # Blocking: only compare pairs that share a phonetic surname or an
    # identifier. Full pairwise comparison is O(n^2) and pointless.
    blocks: Dict[str, Set[str]] = defaultdict(set)
    for name, p in profiles.items():
        toks = tokens_of(name)
        if toks:
            blocks[f"sdx:{soundex(toks[-1])}"].add(name)
        for ident in p.identifiers:
            blocks[ident].add(name)

    candidates: Set[tuple] = set()
    for members in blocks.values():
        for a, b in itertools.combinations(sorted(members), 2):
            candidates.add((a, b))

    matches: List[Dict[str, Any]] = []
    for a, b in sorted(candidates):
        pa, pb = profiles[a], profiles[b]
        if pa.normalized == pb.normalized and pa.name == pb.name:
            continue
        result = score_pair(pa, pb)
        if result["confidence"] < config.ER_CONFIG["min_report_confidence"]:
            continue
        # Present the graph-resident name as the anchor where there is one.
        entity, candidate = (a, b) if pa.in_graph or not pb.in_graph else (b, a)
        pe, pc = profiles[entity], profiles[candidate]
        matches.append({
            "entity": entity,
            "candidate": candidate,
            "confidence": result["confidence"],
            "decision": result["decision"],
            "recommended_action": result["recommended_action"],
            "reasons": result["reasons"],
            "match_reasons": [r["reason"] for r in result["reasons"]],
            "uncertainty": result["uncertainty"],
            "entity_profile": pe.to_dict(),
            "candidate_profile": pc.to_dict(),
            "source_records": sorted({r.record_id for r in pe.records}
                                     | {r.record_id for r in pc.records}),
            "algorithm": "normalisation + Soundex + token similarity, weighted "
                         "against shared and conflicting identifiers",
            "auto_merged": False,
            "verification_notice": config.HUMAN_VERIFICATION_NOTICE,
        })

    matches.sort(key=lambda m: -m["confidence"])

    # Cross-source identifier correlation for graph entities: Person <-> Phone,
    # Account, Vehicle, Travel, Custody.
    correlations: Dict[str, Dict[str, Any]] = {}
    for name, p in profiles.items():
        if not p.in_graph:
            continue
        by_type: Dict[str, List[str]] = defaultdict(list)
        for r in p.records:
            by_type[r.source_type].append(r.record_id)
        correlations[name] = {
            "entity": name,
            "phones": sorted(p.phones),
            "accounts": sorted(p.accounts),
            "vehicles": sorted(p.vehicles),
            "records_by_source": {k: v for k, v in sorted(by_type.items())},
            "source_type_count": len(by_type),
            "candidate_identities": [m["candidate"] for m in matches
                                     if m["entity"] == name],
        }

    clusters = build_clusters(matches, profiles)

    counts: Dict[str, int] = defaultdict(int)
    for m in matches:
        counts[m["decision"]] += 1

    return {
        "matches": matches,
        "clusters": clusters,
        "correlations": correlations,
        "profiles": {k: v.to_dict() for k, v in profiles.items()},
        "stats": {
            "names_observed": len(profiles),
            "pairs_compared": len(candidates),
            "matches_reported": len(matches),
            "likely_same": counts.get("LIKELY_SAME_ENTITY", 0),
            "possible_same": counts.get("POSSIBLE_SAME_ENTITY", 0),
            "unlikely_same": counts.get("UNLIKELY_SAME_ENTITY", 0),
            "candidate_clusters": len(clusters),
            "auto_merged": 0,
        },
        "policy": ("No identities are merged automatically. Every candidate is "
                   "presented to an investigator with its evidence and must be "
                   "confirmed or rejected by a person."),
    }
