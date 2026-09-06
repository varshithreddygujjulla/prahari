"""
provenance.py — evidence-backed assertions and the confidence model.

Two ideas carry this module:

1. `Assertion` is the only way to state that a relationship exists. Constructing
   one without at least one supporting Record raises. That is what makes
   "never allow the AI to generate an unsupported relationship" a property of
   the code rather than a promise in a README.

2. Confidence is *derived*, never hand-written. It is a documented function of
   how the relationship was observed (base), how many independent source types
   corroborate it (bonus), and how often it was observed (bonus, log-scaled).
   Every assertion can therefore explain its own number.
"""
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend import config
from backend.ingestion import Record


class UnsupportedAssertionError(ValueError):
    """Raised when something tries to assert a relationship with no evidence."""


# ---------------------------------------------------------------- confidence
def score_confidence(rel: str, records: List[Record],
                     observation_count: Optional[int] = None) -> Dict[str, Any]:
    """Derive a confidence score and the arithmetic that produced it.

    Returns the score plus a breakdown, so the UI can show *why* a link is
    87% rather than asking the investigator to trust the number.
    """
    if not records:
        raise UnsupportedAssertionError(
            f"cannot score relationship '{rel}' with zero supporting records")

    base = config.EDGE_BASE_CONFIDENCE.get(rel, 50)
    source_types = sorted({r.source_type for r in records})

    # Independent corroboration: distinct source *types*, not record count.
    # Two CDR rows for the same pair are one kind of evidence seen twice.
    extra_types = max(0, len(source_types) - 1)
    corrob = min(extra_types * config.CORROBORATION_BONUS,
                 config.MAX_CORROBORATION_BONUS)

    # Repeat observation, with diminishing returns.
    n = observation_count if observation_count is not None else len(records)
    repeat = 0
    if n > 1:
        repeat = min(round(math.log(n, 3) * 2, 1),
                     config.REPEAT_OBSERVATION_BONUS_CAP)

    raw = base + corrob + repeat
    score = int(max(config.CONFIDENCE_FLOOR, min(config.CONFIDENCE_CEILING, raw)))

    breakdown = [{"factor": "observation method",
                  "detail": f"{rel} — base confidence for this evidence type",
                  "points": base}]
    if corrob:
        breakdown.append({"factor": "independent corroboration",
                          "detail": f"supported by {len(source_types)} source types: "
                                    f"{', '.join(source_types)}",
                          "points": corrob})
    if repeat:
        breakdown.append({"factor": "repeat observation",
                          "detail": f"{n} observations (log-scaled, capped)",
                          "points": repeat})
    if raw > config.CONFIDENCE_CEILING:
        breakdown.append({"factor": "ceiling applied",
                          "detail": f"capped at {config.CONFIDENCE_CEILING}% — "
                                    f"correlated records cannot establish certainty",
                          "points": config.CONFIDENCE_CEILING - raw})

    return {"confidence": score, "breakdown": breakdown,
            "source_types": source_types, "source_count": len(source_types)}


# ---------------------------------------------------------------- assertions
@dataclass
class Assertion:
    """An evidence-backed claim about a relationship between two entities."""
    subject: str
    obj: str
    rel: str
    records: List[Record]
    algorithm: str                                  # how it was derived
    observation_count: Optional[int] = None
    uncertainty: List[str] = field(default_factory=list)
    attrs: Dict[str, Any] = field(default_factory=dict)
    # Lets an edge display as one relation but score as a weaker variant. A call
    # involving an unresolved number is still a "calls" edge on the board, but
    # we cannot attribute the handset, so it must not score like a call between
    # two registered subscribers.
    confidence_key: Optional[str] = None

    def __post_init__(self):
        if not self.records:
            raise UnsupportedAssertionError(
                f"assertion {self.subject} --{self.rel}--> {self.obj} "
                f"has no supporting records")
        self._scored = score_confidence(self.confidence_key or self.rel,
                                        self.records, self.observation_count)

    # -- temporal envelope ------------------------------------------------
    @property
    def timestamps(self) -> List[str]:
        return sorted(r.timestamp for r in self.records if r.timestamp)

    @property
    def start_time(self) -> Optional[str]:
        ts = self.timestamps
        return ts[0] if ts else None

    @property
    def end_time(self) -> Optional[str]:
        ends = [r.end_timestamp for r in self.records if r.end_timestamp]
        ts = self.timestamps
        candidates = ends + ([ts[-1]] if ts else [])
        return max(candidates) if candidates else None

    @property
    def last_observed(self) -> Optional[str]:
        return self.end_time or self.start_time

    @property
    def timeless(self) -> bool:
        """True when no supporting record carries an event time at all."""
        return not self.timestamps and all(r.timeless for r in self.records)

    @property
    def confidence(self) -> int:
        return self._scored["confidence"]

    # -- serialisation ----------------------------------------------------
    def to_edge(self) -> Dict[str, Any]:
        """The API shape for a graph edge, provenance included."""
        return {
            "from": self.subject,
            "to": self.obj,
            "rel": self.rel,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "last_observed": self.last_observed,
            "timeless": self.timeless,
            "observation_count": self.observation_count or len(self.records),
            "confidence": self.confidence,
            "confidence_breakdown": self._scored["breakdown"],
            "source_types": self._scored["source_types"],
            "source_count": self._scored["source_count"],
            "source_records": [r.record_id for r in self.records],
            "evidence": [r.cite() for r in self.records[:12]],
            "evidence_truncated": max(0, len(self.records) - 12),
            "algorithm": self.algorithm,
            "uncertainty": self.uncertainty,
            "verification_notice": config.HUMAN_VERIFICATION_NOTICE,
            **self.attrs,
        }


# ---------------------------------------------------------------- ledger
class EvidenceLedger:
    """Collects assertions and indexes them for provenance lookups.

    Multiple assertions about the same pair+relation are merged so that, for
    example, 40 CDR rows become one edge citing 40 records with a single
    derived confidence.
    """

    def __init__(self):
        self._pending: Dict[tuple, Assertion] = {}
        self._insights: List[Dict[str, Any]] = []

    # -- relationships ----------------------------------------------------
    def assert_link(self, subject: str, obj: str, rel: str,
                    records: List[Record], algorithm: str,
                    observation_count: Optional[int] = None,
                    uncertainty: Optional[List[str]] = None,
                    confidence_key: Optional[str] = None,
                    **attrs) -> Assertion:
        """Record a relationship. Raises if `records` is empty."""
        key = (subject, obj, rel) if subject <= obj else (obj, subject, rel)
        existing = self._pending.get(key)
        if existing:
            seen = {r.record_id for r in existing.records}
            existing.records.extend(r for r in records if r.record_id not in seen)
            if observation_count:
                existing.observation_count = (existing.observation_count or 0) + observation_count
            for u in (uncertainty or []):
                if u not in existing.uncertainty:
                    existing.uncertainty.append(u)
            existing.attrs.update({k: v for k, v in attrs.items() if v is not None})
            existing.__post_init__()          # re-derive confidence
            return existing

        a = Assertion(subject=key[0], obj=key[1], rel=rel, records=list(records),
                      algorithm=algorithm, observation_count=observation_count,
                      uncertainty=list(uncertainty or []), attrs=dict(attrs),
                      confidence_key=confidence_key)
        self._pending[key] = a
        return a

    def assertions(self) -> List[Assertion]:
        return list(self._pending.values())

    def edges(self) -> List[Dict[str, Any]]:
        return [a.to_edge() for a in self._pending.values()]

    def merged_edges(self) -> List[Dict[str, Any]]:
        """One edge per entity pair, carrying every relation observed on it.

        A pair can be connected several ways at once — a transfer *and* forty
        calls *and* a shared FIR — and that is the interesting case, not an edge
        case. A simple undirected graph holds one edge per pair, so those
        relations are merged here rather than overwriting one another:

          * `rel` / `weight` keep the original board's semantics (first relation
            observed wins the label; weights sum) so the visual stays stable;
          * `relations[]` carries each relation separately with its own
            evidence, for the evidence drawer;
          * confidence is re-derived across the union of all records, using the
            strongest relation as the base — a link corroborated by financial
            *and* communication evidence deserves more confidence than either
            on its own.
        """
        by_pair: Dict[tuple, List[Assertion]] = {}
        for (s, o, _rel), a in self._pending.items():
            by_pair.setdefault((s, o), []).append(a)

        out: List[Dict[str, Any]] = []
        for (s, o), group in by_pair.items():
            parts = [a.to_edge() for a in group]
            all_records: List[Record] = []
            seen = set()
            for a in group:
                for r in a.records:
                    if r.record_id not in seen:
                        seen.add(r.record_id)
                        all_records.append(r)

            strongest = max(group, key=lambda a: config.EDGE_BASE_CONFIDENCE.get(
                a.confidence_key or a.rel, 50))
            obs = sum(a.observation_count or len(a.records) for a in group)
            scored = score_confidence(strongest.confidence_key or strongest.rel,
                                      all_records, obs)

            merged: Dict[str, Any] = {"from": s, "to": o}
            for part in parts:
                for k, v in part.items():
                    if k in ("from", "to", "weight"):
                        continue
                    if k not in merged or merged[k] in (None, [], ""):
                        merged[k] = v
            # Weight sums across relations: a pair tied by a transfer *and* a
            # call history is more strongly connected than one tied by either.
            merged["weight"] = sum(p.get("weight", 1) or 1 for p in parts)
            # The displayed relation is the best-evidenced one. Consumers that
            # care about all of them read `rel_types` / `relations`.
            merged["rel"] = strongest.rel
            merged["relations"] = [
                {"rel": p["rel"], "confidence": p["confidence"],
                 "algorithm": p["algorithm"], "start_time": p["start_time"],
                 "end_time": p["end_time"], "timeless": p["timeless"],
                 "observation_count": p["observation_count"],
                 "source_types": p["source_types"],
                 "source_records": p["source_records"],
                 "evidence": p["evidence"],
                 "uncertainty": p["uncertainty"]}
                for p in parts]
            merged["rel_types"] = [p["rel"] for p in parts]
            merged["confidence"] = scored["confidence"]
            merged["confidence_breakdown"] = scored["breakdown"]
            merged["source_types"] = scored["source_types"]
            merged["source_count"] = scored["source_count"]
            merged["source_records"] = [r.record_id for r in all_records]
            merged["evidence"] = [r.cite() for r in all_records[:12]]
            merged["evidence_truncated"] = max(0, len(all_records) - 12)
            merged["observation_count"] = obs
            starts = [p["start_time"] for p in parts if p["start_time"]]
            ends = [p["end_time"] for p in parts if p["end_time"]]
            merged["start_time"] = min(starts) if starts else None
            merged["end_time"] = max(ends) if ends else None
            merged["last_observed"] = merged["end_time"] or merged["start_time"]
            merged["timeless"] = all(p["timeless"] for p in parts)
            unc: List[str] = []
            for p in parts:
                for u in p["uncertainty"]:
                    if u not in unc:
                        unc.append(u)
            merged["uncertainty"] = unc
            merged["algorithm"] = " + ".join(
                dict.fromkeys(p["algorithm"] for p in parts))
            out.append(merged)
        return out

    def for_pair(self, a: str, b: str) -> List[Assertion]:
        return [x for k, x in self._pending.items()
                if {k[0], k[1]} == {a, b}]

    # -- insights ---------------------------------------------------------
    def assert_insight(self, kind: str, headline: str, detail: str,
                       records: List[Record], algorithm: str,
                       entities: Optional[List[str]] = None,
                       confidence: Optional[int] = None,
                       uncertainty: Optional[List[str]] = None,
                       **extra) -> Dict[str, Any]:
        """Record an analytical finding. Also refuses to run without evidence."""
        if not records:
            raise UnsupportedAssertionError(
                f"insight '{kind}' has no supporting records")
        ts = sorted(r.timestamp for r in records if r.timestamp)
        item = {
            "kind": kind,
            "headline": headline,
            "detail": detail,
            "entities": entities or [],
            "algorithm": algorithm,
            # Never borrow an edge formula for a structural finding: a link
            # prediction is not a co-accusation. No explicit confidence means
            # "observation, not a probability" — and the payload says so.
            "confidence": confidence,
            "confidence_basis": ("stated by the producing algorithm" if confidence is not None
                                 else "structural observation — not a probability"),
            "source_records": [r.record_id for r in records],
            "source_types": sorted({r.source_type for r in records}),
            "evidence": [r.cite() for r in records[:12]],
            "evidence_truncated": max(0, len(records) - 12),
            "first_observed": ts[0] if ts else None,
            "last_observed": ts[-1] if ts else None,
            "uncertainty": uncertainty or [],
            "verification_notice": config.HUMAN_VERIFICATION_NOTICE,
            **extra,
        }
        self._insights.append(item)
        return item

    def insights(self) -> List[Dict[str, Any]]:
        return list(self._insights)

    # -- provenance index -------------------------------------------------
    def record_index(self) -> Dict[str, List[Dict[str, str]]]:
        """record_id -> the assertions that cite it (reverse provenance)."""
        idx: Dict[str, List[Dict[str, str]]] = {}
        for a in self._pending.values():
            for r in a.records:
                idx.setdefault(r.record_id, []).append(
                    {"type": "edge", "subject": a.subject,
                     "object": a.obj, "rel": a.rel})
        for ins in self._insights:
            for rid in ins["source_records"]:
                idx.setdefault(rid, []).append(
                    {"type": "insight", "kind": ins["kind"],
                     "headline": ins["headline"]})
        return idx
